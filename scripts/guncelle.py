"""Günlük tarama: kaynakları yeniden indirir, veriyi birleştirir, eskisiyle karşılaştırır.

GitHub Actions her gün çalıştırır (.github/workflows/filoist.yml). Adımlar:
1. ÖHO listesi (emreunel159), İETT canlı filo listesi (İBB SOAP) ve busphoto.eu garaj listeleri indirilir.
2. birlestir.py ile veri/filo.json yeniden üretilir.
3. Güvenlik kontrolü: bir kaynak bozuk ya da eksik döndüyse (araç sayısı birden düştüyse) eski veri korunur.
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
TARAYICI = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Filoist'
OHO_ADRES = ('https://emreunel159.com.tr/?kod=all&kapikod_search=&kapikod=&marka=&model=&yil=&sirket=&owners='
             '&perPage=5000')
IETT_ADRES = 'https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx'
BUSPHOTO_GARAJLAR = [47390, 47391, 47392, 47393, 47394, 47395, 47396, 47397, 47398, 47399, 47400, 47401, 14326]
# Bir sayı öncekinin bu oranının altına düşerse kaynak bozuk sayılır ve yayınlanmaz
ESIK = 0.95


def indir(adres, veri=None, basliklar=None):
    istek = urllib.request.Request(adres, data=veri, headers={'User-Agent': TARAYICI, **(basliklar or {})})
    for deneme in range(3):
        try:
            return urllib.request.urlopen(istek, timeout=120).read().decode('utf-8')
        except Exception as e:
            if deneme == 2:
                raise RuntimeError(f'{adres.split("?")[0]} indirilemedi: {e}') from e
            time.sleep(10)


def oho_indir():
    sayfa = indir(OHO_ADRES)
    m = re.search(r'allImages:\s*(\[.*?\]),\s*\n', sayfa, re.S)
    if not m:
        raise RuntimeError('ÖHO sayfasında araç listesi bulunamadı (site yapısı değişmiş olabilir)')
    alanlar = ['KapiKodu', 'Plaka', 'exPlaka', 'MarkaAdi', 'ModelAdi', 'Yil', 'BolgeAdi', 'IsletmeAdi']
    return [{k: d.get(k) for k in alanlar} for d in json.loads(m.group(1))]


def iett_indir():
    govde = ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
             '<soap:Body><GetFiloAracKonum_json xmlns="http://tempuri.org/" /></soap:Body></soap:Envelope>').encode()
    yanit = indir(IETT_ADRES, govde, {'Content-Type': 'text/xml; charset=utf-8',
                                     'SOAPAction': '"http://tempuri.org/GetFiloAracKonum_json"'})
    m = re.search(r'<GetFiloAracKonum_jsonResult>(.*)</GetFiloAracKonum_jsonResult>', yanit, re.S)
    if not m:
        raise RuntimeError('İETT canlı filo yanıtı beklenen biçimde değil')
    return json.loads(H.unescape(m.group(1)))


def metin(s):
    return H.unescape(re.sub(r'<[^>]+>', '', s)).strip()


def busphoto_indir():
    cikti = []
    for did in BUSPHOTO_GARAJLAR:
        h = indir(f'https://busphoto.eu/list.php?did={did}')
        baslik = re.search(r'<h2[^>]*>(.*?)</h2>', h, re.S)
        garaj = metin(baslik.group(1)).replace('Istanbul, ', '') if baslik else ''
        w = h.find('<h4>Withdrawn')
        for parca, durum in ((h[:w] if w > 0 else h, 'active'), (h[w:] if w > 0 else '', 'withdrawn')):
            for tablo in re.findall(r'<table>(.*?)</table>', parca, re.S):
                if '/vehicle/' not in tablo:
                    continue
                basliklar = [metin(x) for x in re.findall(r'<th[^>]*>(.*?)</th>', tablo, re.S)]
                for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', tablo, re.S):
                    if '/vehicle/' not in tr:
                        continue
                    d = dict(zip(basliklar, [metin(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]))
                    d.update(did=str(did), garage=garaj, status=durum, vid=re.search(r'/vehicle/(\d+)/', tr).group(1))
                    cikti.append(d)
        time.sleep(2)  # siteyi yormamak için
    return cikti


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
    return {'ÖHO': c['ÖHO'], 'İETT': c['İETT'], 'İETT aktif': aktif}


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


def main():
    simdi = datetime.datetime.now(ISTANBUL).replace(microsecond=0)
    eski = yukle(FILO, [])
    durum = yukle(DURUM, {'veriGuncelleme': '2026-11-01'})
    durum['sonKontrol'] = simdi.isoformat()
    rapor = [f'### Tarama: {uygulama_verisi.tarih_yazi(simdi.isoformat())}', '']

    try:
        print('ÖHO listesi indiriliyor…')
        oho = oho_indir()
        print(' ', len(oho), 'araç')
        print('İETT canlı filo listesi indiriliyor…')
        iett = iett_indir()
        print(' ', len(iett), 'kayıt')
        print('busphoto.eu garaj listeleri indiriliyor…')
        bp = busphoto_indir()
        print(' ', len(bp), 'kayıt')
    except Exception as e:
        durum['sonuc'] = 'Kaynak indirilemedi'
        kaydet(DURUM, durum)
        rapor += [f'❌ **Kaynak indirilemedi, veri değiştirilmedi.**', '', f'`{e}`']
        open(RAPOR, 'w', encoding='utf-8').write('\n'.join(rapor) + '\n')
        print(e)
        return 1

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
        durum['sonuc'] = 'Şüpheli düşüş, yayınlanmadı'
        kaydet(DURUM, durum)
        rapor += ['⚠️ **Araç sayısı beklenmedik biçimde düştü; kaynak bozuk olabilir. Eski veri korundu, yayınlanmadı.**',
                  ''] + [f'- {s}' for s in sorunlar]
        open(RAPOR, 'w', encoding='utf-8').write('\n'.join(rapor) + '\n')
        print('Güvenlik kontrolü geçmedi:', sorunlar)
        return 1

    eklenen, cikan, degisen, y = karsilastir(eski, yeni)
    durum['sayilar'] = s_yeni
    if eklenen or cikan or degisen:
        durum['veriGuncelleme'] = simdi.isoformat()
        durum['sonuc'] = 'Güncellendi'
        kaydet(DURUM, durum)
        uygulama_verisi.yaz()
        rapor += [f'✅ **Veriler güncellendi.** {len(eklenen)} yeni, {len(cikan)} çıkan, '
                  f'{len(degisen)} değişen araç.', '']
        rapor += liste('Yeni araçlar', [f'{k} · {y[k]["filo"]} · {" ".join(filter(None, [y[k]["marka"], y[k]["model"]])) or "model bilinmiyor"}'
                                        for k in eklenen])
        rapor += liste('Listeden çıkan araçlar', cikan)
        rapor += liste('Değişen araçlar', [f'{k}: ' + '; '.join(f) for k, f in degisen])
    else:
        durum['sonuc'] = 'Değişiklik yok'
        kaydet(DURUM, durum)
        rapor += ['☑️ **Değişiklik yok.** Kaynaklar tarandı, veriler aynı.', '']
    rapor += [f'Toplam: {sayi(len(yeni))} araç (ÖHO {sayi(s_yeni["ÖHO"])}, İETT {sayi(s_yeni["İETT"])})']
    open(RAPOR, 'w', encoding='utf-8').write('\n'.join(rapor) + '\n')
    print('\n'.join(rapor))
    return 0


def kaydet_kompakt(yol, veri):
    with open(yol, 'w', encoding='utf-8') as f:
        json.dump(veri, f, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    sys.exit(main())
