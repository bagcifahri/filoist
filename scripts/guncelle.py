"""Günlük tarama: kaynakları yeniden indirir, veriyi birleştirir, eskisiyle karşılaştırır.

GitHub Actions her gün çalıştırır (.github/workflows/filoist.yml). Adımlar:
1. ÖHO listesi (emreunel159), İETT canlı filo listesi (İBB SOAP) ve busphoto.eu garaj listeleri indirilir.
   İBB ve busphoto.eu, GitHub sunucularından gelen istekleri engelliyor. Bu iki kaynak için son başarılı indirme
   veri/ klasöründe saklanır (yedek kayıt) ve ulaşılamazsa o kullanılır. Yedek kayıtlar bilgisayardan yayın
   yapılırken (iphone/yayinla.py) Türkiye bağlantısıyla tazelenir.
2. birlestir.py ile veri/filo.json yeniden üretilir.
3. Güvenlik kontrolü: bir kaynak bozuk ya da eksik döndüyse (araç sayısı birden düştüyse) eski veri ve eski
   yedek kayıtlar korunur.
4. Değişiklik varsa uygulama/filo.js yeni tarihle yazılır. veri/durum.json her çalışmada güncellenir.
5. Değişikliklerin dökümü rapor dosyasına yazılır (bildirim olarak GitHub'da yorum atılır).

Çıkış kodu: 0 = tarama tamamlandı (değişiklik olsun ya da olmasın), 1 = kaynak indirilemedi ya da kontrol geçmedi.
"""
import collections, datetime, html as H, json, os, re, sys, time, urllib.request

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
BURA = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURA)
HAM = os.path.join(KOK, 'veri', 'ham')
FILO = os.path.join(KOK, 'veri', 'filo.json')
DURUM = os.path.join(KOK, 'veri', 'durum.json')
RAPOR = os.environ.get('RAPOR') or os.path.join(KOK, 'veri', 'rapor.md')
sys.path.insert(0, BURA)
import birlestir, uygulama_verisi  # noqa: E402

ISTANBUL = datetime.timezone(datetime.timedelta(hours=3))
BASLIKLAR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    # busphoto.eu sütun adlarını dile göre çeviriyor; birleştirme İngilizce adlara göre yazıldı
    'Accept-Language': 'en-US,en;q=0.9',
}
OHO_ADRES = ('https://emreunel159.com.tr/?kod=all&kapikod_search=&kapikod=&marka=&model=&yil=&sirket=&owners='
             '&perPage=5000')
IETT_ADRES = 'https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx'
BUSPHOTO_GARAJLAR = [47390, 47391, 47392, 47393, 47394, 47395, 47396, 47397, 47398, 47399, 47400, 47401, 14326]
# Bir sayı öncekinin bu oranının altına düşerse kaynak bozuk sayılır ve yayınlanmaz
ESIK = 0.95


def indir(adres, veri=None, basliklar=None, deneme_sayisi=3, sure=120):
    istek = urllib.request.Request(adres, data=veri, headers={**BASLIKLAR, **(basliklar or {})})
    for deneme in range(deneme_sayisi):
        try:
            return urllib.request.urlopen(istek, timeout=sure).read().decode('utf-8')
        except Exception as e:
            # 403: site bu bağlantıyı engelliyor, yeniden denemek anlamsız
            if deneme == deneme_sayisi - 1 or getattr(e, 'code', None) == 403:
                raise RuntimeError(f'{adres.split("?")[0]} indirilemedi: {e}') from e
            time.sleep(10)


def oho_indir():
    sayfa = indir(OHO_ADRES)
    m = re.search(r'allImages:\s*(\[.*?\]),\s*\n', sayfa, re.S)
    if not m:
        raise RuntimeError('ÖHO sayfasında araç listesi bulunamadı (site yapısı değişmiş olabilir)')
    alanlar = ['KapiKodu', 'Plaka', 'exPlaka', 'MarkaAdi', 'ModelAdi', 'Yil', 'BolgeAdi', 'IsletmeAdi']
    return [{k: d.get(k) for k in alanlar} for d in json.loads(m.group(1))]


def iett_indir(deneme_sayisi=2, sure=45):
    govde = ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
             '<soap:Body><GetFiloAracKonum_json xmlns="http://tempuri.org/" /></soap:Body></soap:Envelope>').encode()
    yanit = indir(IETT_ADRES, govde, {'Content-Type': 'text/xml; charset=utf-8',
                                     'SOAPAction': '"http://tempuri.org/GetFiloAracKonum_json"'},
                  deneme_sayisi, sure)
    m = re.search(r'<GetFiloAracKonum_jsonResult>(.*)</GetFiloAracKonum_jsonResult>', yanit, re.S)
    if not m:
        raise RuntimeError('İETT canlı filo yanıtı beklenen biçimde değil')
    # Yalnız İETT araçları ve birleştirmede kullanılan alanlar saklanır (ÖHO verisi emreunel159'dan gelir)
    return [{'KapiNo': r['KapiNo'], 'Plaka': r['Plaka'], 'Garaj': r['Garaj']}
            for r in json.loads(H.unescape(m.group(1))) if '-' not in r['KapiNo']]


def metin(s):
    return H.unescape(re.sub(r'<[^>]+>', '', s)).strip()


BP_ALANLAR = ['#', 'Plate', 'Model', 'Built', 'Remarks', 'To...', 'status']


def busphoto_indir():
    cikti = []
    for did in BUSPHOTO_GARAJLAR:
        h = indir(f'https://busphoto.eu/list.php?did={did}')
        w = h.find('<h4>Withdrawn')
        for parca, durum in ((h[:w] if w > 0 else h, 'active'), (h[w:] if w > 0 else '', 'withdrawn')):
            for tablo in re.findall(r'<table>(.*?)</table>', parca, re.S):
                if '/vehicle/' not in tablo:
                    continue
                basliklar = [metin(x) for x in re.findall(r'<th[^>]*>(.*?)</th>', tablo, re.S)]
                if not {'#', 'Model', 'Built'} <= set(basliklar):
                    raise RuntimeError(f'busphoto.eu sütun adları değişmiş: {basliklar}')
                for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tablo, re.S):
                    if '/vehicle/' not in tr:
                        continue
                    d = dict(zip(basliklar, [metin(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]))
                    d['status'] = durum
                    # Yalnız birleştirmede kullanılan alanlar saklanır
                    cikti.append({k: d.get(k, '') for k in BP_ALANLAR})
        time.sleep(2)  # siteyi yormamak için
    return cikti


# GitHub'dan erişilemeyen kaynaklar: (rapordaki adı, indirme işlevi, yedek kayıt dosyası)
YEDEKLI = {
    'iett': ('İETT canlı listesi', iett_indir, os.path.join(KOK, 'veri', 'iett_canli.json')),
    'busphoto': ('busphoto.eu listeleri', busphoto_indir, os.path.join(KOK, 'veri', 'busphoto.json')),
}


def yedek_yaz(yol, kayitlar, zaman):
    with open(yol, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'tarih': zaman.isoformat(), 'araclar': kayitlar}, f, ensure_ascii=False, separators=(',', ':'))


def yedekli_indir(anahtar, notlar, tazeler):
    """Kaynağı indirir; ulaşılamazsa son yedek kaydı döndürür ve rapora not düşer.

    Taze indirilen kayıt hemen yedeğe yazılmaz, tazeler listesine eklenir: güvenlik kontrolü geçerse yazılır.
    Böylece bozuk bir indirme sağlam yedeğin üstüne yazılmaz.
    """
    ad, islev, yol = YEDEKLI[anahtar]
    try:
        kayitlar = islev()
        if not kayitlar:
            raise RuntimeError(f'{ad} boş döndü')
        tazeler.append((yol, kayitlar))
        return kayitlar
    except Exception as e:
        if not os.path.exists(yol):
            raise
        kayit = yukle(yol, {})
        print(' ', e, '→ son kayıt kullanılıyor:', kayit['tarih'])
        notlar.append(f'{ad} ({uygulama_verisi.tarih_yazi(kayit["tarih"])})')
        return kayit['araclar']


def yedekleri_tazele():
    """Bilgisayardan yayın yapılırken çağrılır: GitHub'ın ulaşamadığı kaynakları indirip yedek kayıtları tazeler."""
    zaman = datetime.datetime.now(ISTANBUL).replace(microsecond=0)
    for ad, islev, yol in YEDEKLI.values():
        try:
            kayitlar = islev()
            onceki = len(yukle(yol, {}).get('araclar', []))
            if len(kayitlar) < onceki * ESIK:
                raise RuntimeError(f'kayıt sayısı düştü ({onceki} → {len(kayitlar)}), kaynak bozuk olabilir')
            yedek_yaz(yol, kayitlar, zaman)
            print(f'{ad} tazelendi: {len(kayitlar)} kayıt')
        except Exception as e:
            print(f'UYARI: {ad} tazelenemedi, eldeki kayıt kullanılacak.', e)


def yukle(yol, varsayilan):
    return json.load(open(yol, encoding='utf-8')) if os.path.exists(yol) else varsayilan


def kaydet(yol, veri):
    with open(yol, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)


def sayi(n):
    return f'{n:,}'.replace(',', '.')


def sayilar(araclar):
    c = collections.Counter(a['filo'] for a in araclar)
    aktif = sum(1 for a in araclar if a['filo'] == 'İETT' and a['durum'] == 'Aktif')
    modelli = sum(1 for a in araclar if a['model'])
    return {'ÖHO': c['ÖHO'], 'İETT': c['İETT'], 'İETT aktif': aktif, 'modeli bilinen': modelli}


ADLAR = {'plaka': 'plaka', 'eskiPlaka': 'eski plaka', 'marka': 'marka', 'model': 'model', 'yil': 'yıl',
         'operator': 'operatör', 'hatlar': 'hatlar', 'garaj': 'garaj', 'durum': 'durum', 'not': 'not'}


def karsilastir(eski, yeni):
    e = {a['kapi']: a for a in eski}
    y = {a['kapi']: a for a in yeni}
    eklenen = sorted(set(y) - set(e))
    cikan = sorted(set(e) - set(y))
    degisen = []
    for k in sorted(set(e) & set(y)):
        farklar = []
        for alan, ad in ADLAR.items():
            a, b = e[k][alan], y[k][alan]
            if a != b:
                if alan == 'hatlar':
                    a, b = ' '.join(a) or '—', ' '.join(b) or '—'
                farklar.append(f'{ad}: {a or "—"} → {b or "—"}')
        if farklar:
            degisen.append((k, farklar))
    return eklenen, cikan, degisen, y


def liste(baslik, satirlar, sinir=40):
    if not satirlar:
        return []
    cikti = [f'**{baslik} ({len(satirlar)})**', '']
    cikti += [f'- {s}' for s in satirlar[:sinir]]
    if len(satirlar) > sinir:
        cikti.append(f'- … ve {len(satirlar) - sinir} tane daha')
    return cikti + ['']


def rapor_yaz(satirlar):
    with open(RAPOR, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(satirlar) + '\n')


def basarisiz(durum, simdi, sonuc, rapor, satirlar):
    """Başarısız taramayı kaydeder. sonKontrol değişmez: uygulama son *başarılı* kontrolü gösterir."""
    durum['sonuc'] = sonuc
    durum['sonHata'] = simdi.isoformat()
    kaydet(DURUM, durum)
    rapor_yaz(rapor + satirlar)
    return 1


def main():
    simdi = datetime.datetime.now(ISTANBUL).replace(microsecond=0)
    eski = yukle(FILO, [])
    durum = yukle(DURUM, {'veriGuncelleme': '2026-11-01'})
    rapor = [f'### Tarama: {uygulama_verisi.tarih_yazi(simdi.isoformat())}', '']
    try:
        return tara(simdi, eski, durum, rapor)
    except Exception as e:
        # Beklenmedik hata (ör. birleştirme): eski veri yerinde kalsın, rapor yine yazılsın
        if eski:
            kaydet_kompakt(FILO, eski)
        print('Beklenmedik hata:', repr(e))
        return basarisiz(durum, simdi, 'Beklenmedik hata', rapor,
                         ['❌ **Tarama beklenmedik bir hatayla durdu, veri değiştirilmedi.**', '', f'`{e!r}`'])


def tara(simdi, eski, durum, rapor):
    yedekten, tazeler = [], []

    try:
        print('ÖHO listesi indiriliyor…')
        oho = oho_indir()
        print(' ', len(oho), 'araç')
        print('İETT canlı filo listesi indiriliyor…')
        iett = yedekli_indir('iett', yedekten, tazeler)
        print(' ', len(iett), 'kayıt')
        print('busphoto.eu garaj listeleri indiriliyor…')
        bp = yedekli_indir('busphoto', yedekten, tazeler)
        print(' ', len(bp), 'kayıt')
    except Exception as e:
        print(e)
        return basarisiz(durum, simdi, 'Kaynak indirilemedi', rapor,
                         ['❌ **Kaynak indirilemedi, veri değiştirilmedi.**', '', f'`{e}`'])

    os.makedirs(HAM, exist_ok=True)
    for ad, veri in (('ohm.json', oho), ('filo_konum.json', iett), ('bp_iett.json', bp)):
        with open(os.path.join(HAM, ad), 'w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False)
    birlestir.main()
    yeni = yukle(FILO, [])

    # Güvenlik kontrolü: kaynak yarım ya da bozuk döndüyse eski veri yerinde kalır
    s_eski, s_yeni = sayilar(eski), sayilar(yeni)
    sorunlar = [f'{ad}: {sayi(s_eski[ad])} → {sayi(s_yeni[ad])}'
                for ad in s_eski if s_eski[ad] and s_yeni[ad] < s_eski[ad] * ESIK]
    if not bp or not oho or not iett:
        sorunlar.append('bir kaynak boş döndü')
    if sorunlar:
        if eski:
            kaydet_kompakt(FILO, eski)
        print('Güvenlik kontrolü geçmedi:', sorunlar)
        return basarisiz(durum, simdi, 'Şüpheli düşüş, yayınlanmadı', rapor,
                         ['⚠️ **Sayılar beklenmedik biçimde düştü; kaynak bozuk olabilir. Eski veri korundu, yayınlanmadı.**',
                          ''] + [f'- {s}' for s in sorunlar])

    # Kontrol geçti: taze indirilen kaynaklar artık güvenle yedeğe yazılabilir
    for yol, kayitlar in tazeler:
        yedek_yaz(yol, kayitlar, simdi)

    eklenen, cikan, degisen, y = karsilastir(eski, yeni)
    durum['sayilar'] = s_yeni
    durum['sonKontrol'] = simdi.isoformat()
    durum.pop('sonHata', None)
    # Karar araç bazında tüm alanlarla verilir; yalnızca sıra değiştiyse değişiklik sayılmaz
    if {a['kapi']: a for a in eski} != y:
        durum['veriGuncelleme'] = simdi.isoformat()
        durum['sonuc'] = 'Güncellendi'
        kaydet(DURUM, durum)
        uygulama_verisi.yaz()
        ozet = (f'{len(eklenen)} yeni, {len(cikan)} çıkan, {len(degisen)} değişen araç.' if eklenen or cikan or degisen
                else 'Yalnızca araçların bilgi kaynağı kaydı değişti.')
        rapor += [f'✅ **Veriler güncellendi.** {ozet}', '']
        rapor += liste('Yeni araçlar', [f'{k} · {y[k]["filo"]} · {" ".join(filter(None, [y[k]["marka"], y[k]["model"]])) or "model bilinmiyor"}'
                                        for k in eklenen])
        rapor += liste('Listeden çıkan araçlar', cikan)
        rapor += liste('Değişen araçlar', [f'{k}: ' + '; '.join(f) for k, f in degisen])
    else:
        # Dosya eski haliyle kalsın; yoksa sırası farklı ama içeriği aynı bir dosya kaydedilir
        if eski:
            kaydet_kompakt(FILO, eski)
        durum['sonuc'] = 'Değişiklik yok'
        kaydet(DURUM, durum)
        rapor += ['☑️ **Değişiklik yok.** Kaynaklar tarandı, veriler aynı.', '']
    if yedekten:
        rapor += ['ℹ️ GitHub’dan ulaşılamadığı için son kayıt kullanıldı: ' + ', '.join(yedekten)
                  + '. Bu kayıtlar bilgisayardan yayın yapınca tazelenir.', '']
    rapor += [f'Toplam: {sayi(len(yeni))} araç (ÖHO {sayi(s_yeni["ÖHO"])}, İETT {sayi(s_yeni["İETT"])})']
    rapor_yaz(rapor)
    print('\n'.join(rapor))
    return 0


def kaydet_kompakt(yol, veri):
    with open(yol, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(veri, f, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    sys.exit(main())
