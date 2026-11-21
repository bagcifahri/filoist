"""Günlük tarama: kaynakları yeniden indirir, veriyi birleştirir, eskisiyle karşılaştırır.

GitHub Actions her gece çalıştırır (.github/workflows/filoist.yml), iki parça halinde:
- `--yalniz-oho` (GitHub'da): yalnız ÖHO sitesi (emreunel159) yavaşça okunur, denetimden geçerse veri/oho.json'a yazılır.
- `--oho-depodan` (Türkiye'deki sunucuda): ÖHO sitesine bağlanılmaz, liste depodan alınır; aşağıdaki adımlar yapılır.
Seçeneksiz çalıştırılırsa ÖHO sitesi de burada okunur (elle tam tarama).

Adımlar:
1. ÖHO listesi, İETT canlı filo listesi (İBB SOAP) ve busphoto.eu garaj listeleri alınır.
   Her kaynağın son başarılı indirmesi veri/ klasöründe saklanır (yedek kayıt) ve ulaşılamazsa o kullanılır.
   İBB ve busphoto.eu GitHub sunucularını engellediği için bunlar Türkiye'deki sunucudan okunur.
2. birlestir.py ile veri/filo.json yeniden üretilir.
3. Güvenlik kontrolü: bir kaynak bozuk ya da eksik döndüyse (araç sayısı birden düştüyse) eski veri ve eski
   yedek kayıtlar korunur.
4. Değişiklik varsa uygulama/filo.js yeni tarihle yazılır. veri/durum.json her çalışmada güncellenir.
5. Değişikliklerin dökümü rapor dosyasına yazılır (bildirim olarak GitHub'da yorum atılır).

Çıkış kodu: 0 = tarama tamamlandı (değişiklik olsun ya da olmasın), 1 = kaynak indirilemedi ya da kontrol geçmedi.
"""
import collections, datetime, html as H, json, os, random, re, sys, time, urllib.parse, urllib.request

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
BURA = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURA)
HAM = os.path.join(KOK, 'veri', 'ham')
FILO = os.path.join(KOK, 'veri', 'filo.json')
DURUM = os.path.join(KOK, 'veri', 'durum.json')
RAPOR = os.environ.get('RAPOR') or os.path.join(KOK, 'veri', 'rapor.md')
sys.path.insert(0, BURA)
import birlestir, uygulama_verisi, yazim  # noqa: E402

ISTANBUL = datetime.timezone(datetime.timedelta(hours=3))
BASLIKLAR = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    # busphoto.eu sütun adlarını dile göre çeviriyor; birleştirme İngilizce adlara göre yazıldı
    'Accept-Language': 'en-US,en;q=0.9',
}
# ÖHO sitesi (emreunel159.com.tr), 16.11.2026'dan beri sayfaları yalnızca kendi sayfa geçişiyle veriyor:
# oturum çerezi + sayfadaki güvenlik anahtarı + "X-Requested-With" başlığı. Site sahibi Emre, Filoist'in siteyi bu yolla
# okumasına izin verdi (kullanıcı 16.11.2026'da ÖHO forumlarında görüştü). Sayfa başına en çok 9 araç verilir.
# Site araçları bölümlere ayırıyor; bizim ÖHO filomuz sitedeki "ÖHO" + "OAŞ" bölümleridir (İETT bölümü okunmaz).
# 21.11.2026: Emre GitHub engelini kaldırdı. ÖHO artık GitHub'da ayrı bir işte okunur (--yalniz-oho, veri/oho.json'a
# yazılır); Türkiye'deki sunucu ÖHO sitesine bağlanmaz, listeyi depodan alır (--oho-depodan).
OHO_SITE = 'https://emreunel159.com.tr/'
# ÖHO sitesine kendimizi açıkça tanıtırız: Emre kayıtlarında isteklerin Filoist'ten geldiğini görür
OHO_TANITIM = 'Mozilla/5.0 (compatible; Filoist/1.0; +https://bagcifahri.github.io/filoist/)'
OHO_BOLUMLER = ['oho', 'oas']
# Sayfalar arasında saniye. Site sahibi Emre (21.11.2026): "1-2 saniye ara verebilirsiniz; sayfa başına sunucuda
# yaklaşık 15 veritabanı sorgusu çalışıyor." Üst sınır seçildi, üstüne küçük rastgele pay eklenir. 342 sayfa ~15-20 dk
OHO_BEKLEME = 2
OHO_BEKLEME_PAYI = 0.5
# Bir taramada siteye gidebilecek en çok istek (342 sayfa + oturum açılışları + birkaç yeniden deneme).
# Kodda ya da sitede bir sorun olursa tarama döngüye girip siteyi yormasın diye kesin sınır
OHO_ISTEK_TAVANI = 450
# Bir taramada izin verilen en çok bağlantı/sunucu hatası; aşılırsa tarama durur, son kayıt kullanılır
OHO_HATA_SINIRI = 5
OHO_SINIR_BEKLEME = 60  # 429 gelince site süre bildirmezse beklenecek saniye
# Site sahibinin Cloudflare'de Filoist'e tanımladığı geçiş anahtarı (engel ve hız sınırından muaf tutulur).
# GitHub'da "OHO_ANAHTAR" gizli değişkeninden, bilgisayarda oho_anahtar.txt dosyasından okunur; depoya girmez.
OHO_ANAHTAR_BASLIGI = 'X-Filoist-Anahtar'


def oho_anahtari():
    anahtar = os.environ.get('OHO_ANAHTAR', '').strip()
    yol = os.path.join(KOK, 'oho_anahtar.txt')
    if not anahtar and os.path.exists(yol):
        anahtar = open(yol, encoding='utf-8').read().strip()
    return anahtar
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


def _alan(kart, ad):
    """Karttaki '<b>Ad:</b> değer' satırının düz metni."""
    m = re.search(rf'<b>{ad}:</b>(.*?)</p>', kart, re.S)
    return ' '.join(metin(m.group(1)).split()) if m else ''


def oho_karti(kart):
    m = re.search(r'aracdetails\.php\?kod=([^"&]+)"', kart)
    if not m:
        return None
    # Plaka satırı: "34 HO 1000 (ex. 34 NKR 840)"; satır kapanış etiketi olmadan bitebiliyor
    p = re.search(r'<b>Plaka:</b>([^<]*)', kart)
    plaka = ' '.join(H.unescape(p.group(1)).split()) if p else ''
    ex = re.search(r'\(\s*ex\.?\s*([^)]*)\)', plaka, re.I)
    if ex:
        plaka = plaka[:ex.start()].strip()
    # Hatların tam listesi düğmenin data-hatlar özniteliğinde. Düğme yoksa satırın düz metni okunur:
    # hatlar " - " ile ayrılır, "Yandığı için Çalışmıyor" gibi açıklamalar bağlantısız düz metin olarak yazılır
    d = re.search(r'data-hatlar="([^"]*)"', kart)
    hatlar = json.loads(H.unescape(d.group(1))) if d else re.split(r'\s+-\s+', _alan(kart, r'Hat\(lar\)'))
    return {'KapiKodu': H.unescape(m.group(1)).strip(), 'Plaka': plaka, 'exPlaka': ex.group(1).strip() if ex else '',
            'MarkaAdi': _alan(kart, 'Marka'), 'ModelAdi': _alan(kart, 'Model'), 'Yil': _alan(kart, 'Yıl'),
            'BolgeAdi': ' - '.join(h.strip() for h in hatlar if h and h.strip()), 'IsletmeAdi': _alan(kart, 'Operatör')}


class HizSiniri(RuntimeError):
    """ÖHO sitesi taramayı durdurmamızı istiyor (hız sınırı, istek ya da hata tavanı); ısrar edilmez, son kayıt kullanılır."""


def oho_bekle():
    time.sleep(OHO_BEKLEME + random.uniform(0, OHO_BEKLEME_PAYI))


class OhoOturumu:
    """Sitenin kendi sayfa geçişi gibi okur: ana sayfadan oturum çerezi ve güvenlik anahtarı alınır,
    sayfalar aynı oturumla, sitenin JavaScript'inin gönderdiği başlıklarla istenir.

    Siteyi korumak için: istekler tek tek gider, sayılır (OHO_ISTEK_TAVANI), hatalar sayılır (OHO_HATA_SINIRI),
    ikinci hız sınırı (429) ya da uzun bekleme isteğinde tarama hemen bırakılır."""

    def __init__(self):
        self.acici = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        self.anahtar = ''
        self.gecis = oho_anahtari()
        self.istek = 0
        self.hata = 0
        self.sinir = 0
        self.yenile()

    def _al(self, adres, basliklar=None, deneme_sayisi=3):
        gecis = {OHO_ANAHTAR_BASLIGI: self.gecis} if self.gecis else {}
        istek = urllib.request.Request(adres, headers={**BASLIKLAR, 'User-Agent': OHO_TANITIM, **gecis,
                                                       **(basliklar or {})})
        # Döngü her durumda biter: 429 taramada en çok bir kez beklenir, hatalar deneme_sayisi ve OHO_HATA_SINIRI ile,
        # toplam istek OHO_ISTEK_TAVANI ile sınırlı
        deneme = 0
        while True:
            if self.istek >= OHO_ISTEK_TAVANI:
                raise HizSiniri(f'ÖHO taraması istek tavanına ulaştı ({OHO_ISTEK_TAVANI}), siteyi yormamak için durduruldu')
            self.istek += 1
            try:
                return self.acici.open(istek, timeout=90).read().decode('utf-8')
            except Exception as e:
                kod = getattr(e, 'code', None)
                if kod == 429:
                    istenen = e.headers.get('Retry-After')
                    try:
                        sure = max(0, int(istenen or OHO_SINIR_BEKLEME))
                    except ValueError:  # süre tarih olarak da yazılabilir
                        sure = OHO_SINIR_BEKLEME
                    self.sinir += 1
                    # Uzun bekleme isteği ya da ikinci 429: site yük altında demektir, ısrar edilmez.
                    # (20.11.2026'da site bu engeli saatlerce sürdürdü.) Tarama ÖHO'nun son kaydıyla devam eder
                    if sure > OHO_SINIR_BEKLEME or self.sinir > 1:
                        raise HizSiniri(f'ÖHO sitesi hız sınırı uyguladı ({istenen or "?"} sn bekleme istedi), tarama durduruldu') from e
                    print(f'  ÖHO sitesi hız sınırı: {sure} sn bekleniyor')
                    time.sleep(sure)
                    continue  # tek 429 deneme hakkından düşmez
                # 403: oturum düşmüş olabilir (çağıran bir kez yeniler) ya da site bu bağlantıyı engelliyor
                if kod == 403:
                    raise RuntimeError(f'{OHO_SITE} erişim reddedildi (403)') from e
                self.hata += 1
                if self.hata > OHO_HATA_SINIRI:
                    raise HizSiniri(f'ÖHO sitesinden {self.hata} hata alındı, siteyi yormamak için tarama durduruldu: {e}') from e
                deneme += 1
                if deneme >= deneme_sayisi:
                    raise RuntimeError(f'{OHO_SITE} indirilemedi: {e}') from e
                time.sleep(15 * deneme)  # sunucu zorlanıyorsa giderek daha uzun beklenir

    def yenile(self):
        ana = self._al(OHO_SITE)
        m = re.search(r'csrfToken:\s*"([^"]+)"', ana)
        if not m:
            raise RuntimeError('ÖHO sitesinde güvenlik anahtarı bulunamadı (site yapısı değişmiş olabilir)')
        self.anahtar = m.group(1)

    def sayfa(self, bolum, no):
        adres = OHO_SITE + '?' + urllib.parse.urlencode(
            {'kod': 'all', 'kapikod_search': '', 'seg': bolum, 'perPage': 9, 'page': no})
        basliklar = lambda: {'X-Requested-With': 'XMLHttpRequest', 'X-CSRF-Token': self.anahtar, 'Referer': OHO_SITE}
        try:
            return self._al(adres, basliklar())
        except HizSiniri:
            raise
        except RuntimeError:
            # Sitenin kendi kodu da 403'te sayfayı yeniler: oturum bir kez tazelenip tekrar denenir
            oho_bekle()
            self.yenile()
            oho_bekle()
            return self._al(adres, basliklar())


def oho_indir(istatistik=None):
    """ÖHO ve OAŞ bölümlerini sayfa sayfa okur. istatistik sözlüğü verilirse sayfa ve istek sayısı yazılır."""
    oturum = OhoOturumu()
    araclar = {}
    sayfalar = planlanan = 0
    try:
        for bolum in OHO_BOLUMLER:
            oho_bekle()
            ilk = oturum.sayfa(bolum, 1)
            sayfalar += 1
            sayfa_sayisi = re.search(r'Sayfa\s*\d+\s*/\s*(\d+)', ilk)
            toplam = re.search(r'Araçlar\s*\((\d+)\)', ilk)
            if not sayfa_sayisi or not toplam:
                raise RuntimeError(f'ÖHO sitesinin "{bolum}" bölümünde araç listesi bulunamadı (site yapısı değişmiş olabilir)')
            son = int(sayfa_sayisi.group(1))
            planlanan += son
            # Site beklenenden çok sayfa bildiriyorsa (16.11.2026'da bölüm ayrımını yok sayıp İETT araçlarını da
            # listelemişti) hiç başlanmaz: yüzlerce sayfa okunup sonra tavanda durulmasın
            if planlanan > OHO_ISTEK_TAVANI - 30:
                raise RuntimeError(f'ÖHO sitesi beklenenden çok sayfa bildiriyor ({planlanan}); site yapısı değişmiş olabilir, okunmadı')
            bolumde = {}
            def oku(sayfa):
                for kart in re.split(r'<div class="card">', sayfa)[1:]:
                    arac = oho_karti(kart)
                    if arac:
                        bolumde.setdefault(arac['KapiKodu'], arac)  # okuma sırasında kayma olursa aynı araç bir kez sayılır

            oku(ilk)
            for no in range(2, son + 1):
                oho_bekle()
                onceki = len(bolumde)
                oku(oturum.sayfa(bolum, no))
                sayfalar += 1
                if len(bolumde) == onceki:
                    # Oturum düşerse site sayfa numarasını yok sayıp ilk sayfayı verir:
                    # oturum bir kez yenilenip aynı sayfa yeniden istenir
                    print(f'  {bolum}: {no}. sayfa yeni araç getirmedi, oturum yenileniyor')
                    oho_bekle()
                    oturum.yenile()
                    oho_bekle()
                    oku(oturum.sayfa(bolum, no))
                if len(bolumde) == onceki:
                    # Son sayfa: okuma sırasında araç çıktıysa sayfa sayısı azalmış olabilir; eksik varsa aşağıdaki
                    # sayı denetimi yakalar
                    if no == son:
                        print(f'  {bolum}: son sayfa ({no}) yeni araç getirmedi, okuma sırasında araç çıkmış olabilir')
                        break
                    # Ortadaki sayfada yine olmuyorsa sayfalama gerçekten bozuk: hemen durulur, yüzlerce sayfa boşuna istenmesin
                    raise RuntimeError(f'ÖHO sayfaları okunamıyor: "{bolum}" bölümünde {no}. sayfa yeni araç getirmedi')
                if no % 50 == 0:
                    print(f'  {bolum}: {no} / {son} sayfa')
            beklenen = int(toplam.group(1))
            # Okuma sırasında araç eklenip çıkabilir; küçük fark normal, büyük fark eksik okuma demektir
            if len(bolumde) < beklenen * 0.99:
                raise RuntimeError(f'ÖHO listesi eksik okundu ("{bolum}"): {len(bolumde)} / {beklenen} araç')
            araclar.update(bolumde)
    finally:
        if istatistik is not None:
            istatistik.update(sayfa=sayfalar, istek=oturum.istek)
    # Güvence: ÖHO kapı numaralarında tire var (A-001), İETT'de yok (M4510)
    return [a for a in araclar.values() if '-' in a['KapiKodu']]


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
    # ÖHO: gece taramasında GitHub'daki ayrı iş okur (oho_tazele); bu satır elle tam tarama içindir
    'oho': ('ÖHO listesi', oho_indir, os.path.join(KOK, 'veri', 'oho.json')),
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


OHO_YOL = YEDEKLI['oho'][2]
# Depodaki ÖHO listesi bundan eskiyse bu gece tazelenememiş demektir (rapora "son kayıt" notu düşülür)
OHO_TAZE_SAAT = 12


def oho_depodan(notlar):
    """Sunucudaki tarama: ÖHO sitesine bağlanmadan, GitHub'ın az önce depoya yazdığı listeyi kullanır."""
    kayit = yukle(OHO_YOL, {})
    if not kayit.get('araclar'):
        raise RuntimeError('Depoda ÖHO listesi (veri/oho.json) yok')
    yas = datetime.datetime.now(ISTANBUL) - datetime.datetime.fromisoformat(kayit['tarih'])
    if yas > datetime.timedelta(hours=OHO_TAZE_SAAT):
        print('  ÖHO listesi bu gece tazelenemedi → son kayıt kullanılıyor:', kayit['tarih'])
        notlar.append(f'ÖHO listesi ({uygulama_verisi.tarih_yazi(kayit["tarih"])})')
    return kayit['araclar']


def oho_ozeti(metin_):
    """GitHub'daki ÖHO işinin tek satırlık sonucu: iş çıktısına (rapora eklenir) ve ekrana yazılır."""
    metin_ = ' '.join(str(metin_).split())
    print(metin_)
    cikti = os.environ.get('GITHUB_OUTPUT')
    if cikti:
        with open(cikti, 'a', encoding='utf-8') as f:
            f.write(f'ozet={metin_}\n')


def oho_tazele():
    """GitHub'daki ÖHO işi (--yalniz-oho): yalnız ÖHO sitesini okur, denetimden geçerse veri/oho.json'a yazar.

    Okuma başarısız olursa dosyaya dokunulmaz; sunucudaki tarama son kaydı kullanır. Çıkış kodu yine 0'dır,
    sonuç rapora tek satır olarak geçer. 1 yalnız beklenmedik hatada döner."""
    simdi = datetime.datetime.now(ISTANBUL).replace(microsecond=0)
    onceki = yukle(OHO_YOL, {})
    son = uygulama_verisi.tarih_yazi(onceki['tarih']) if onceki.get('tarih') else 'yok'
    istatistik = {}
    baslangic = time.monotonic()
    print('ÖHO listesi Emre’nin sitesinden okunuyor…')
    try:
        kayitlar = oho_indir(istatistik)
        if not kayitlar:
            raise RuntimeError('ÖHO listesi boş döndü')
        if len(kayitlar) < len(onceki.get('araclar', [])) * ESIK:
            raise RuntimeError(f'araç sayısı düştü ({len(onceki["araclar"])} → {len(kayitlar)}), site bozuk dönmüş olabilir')
    except Exception as e:
        dk = (time.monotonic() - baslangic) / 60
        oho_ozeti(f'⚠️ ÖHO listesi okunamadı, son kayıt ({son}) kullanılacak. {istatistik.get("istek", 0)} istek, '
                  f'{dk:.0f} dk. Sebep: {e}')
        return 0
    yedek_yaz(OHO_YOL, kayitlar, simdi)
    dk = (time.monotonic() - baslangic) / 60
    oho_ozeti(f'🚌 ÖHO listesi Emre’nin sitesinden tazelendi: {sayi(len(kayitlar))} araç, {istatistik["sayfa"]} sayfa, '
              f'{istatistik["istek"]} istek, {dk:.0f} dk.')
    return 0


def yedekleri_tazele():
    """Bilgisayardan yayın yapılırken çağrılır: GitHub'ın ulaşamadığı kaynakları indirip yedek kayıtları tazeler."""
    zaman = datetime.datetime.now(ISTANBUL).replace(microsecond=0)
    for anahtar, (ad, islev, yol) in YEDEKLI.items():
        # ÖHO'yu gece taramasında GitHub okuyor; bilgisayardan ayrıca 342 sayfa okumak siteyi boşuna yorar
        if anahtar == 'oho':
            continue
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
    # Yalnızca harf büyüklüğü farkı değişiklik sayılmasın; eski kayıt da aynı kurallarla okunur
    eski = yazim.duzelt(yukle(FILO, []))
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
        if '--oho-depodan' in sys.argv:
            print('ÖHO listesi depodan alınıyor (GitHub bu gece okudu)…')
            oho = oho_depodan(yedekten)
        else:
            print('ÖHO listesi indiriliyor…')
            oho = yedekli_indir('oho', yedekten, tazeler)
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
        rapor += ['ℹ️ Kaynağa ulaşılamadığı için son kayıt kullanıldı: ' + ', '.join(yedekten) + '.', '']
    # Yeni bir model çıktıysa teknik özelliklerinin eklenmesi gerekir (veri/teknik.json)
    teknik = yukle(os.path.join(KOK, 'veri', 'teknik.json'), {}).get('modeller', {})
    eksik = collections.Counter(f'{a["marka"]} {a["model"]}' for a in yeni
                                if a['model'] and f'{a["marka"]}|{a["model"]}' not in teknik)
    if teknik and eksik:
        rapor += liste('Teknik özelliği eklenmemiş modeller', [f'{m} ({n} araç)' for m, n in eksik.most_common()])
    rapor += [f'Toplam: {sayi(len(yeni))} araç (ÖHO {sayi(s_yeni["ÖHO"])}, İETT {sayi(s_yeni["İETT"])})']
    rapor_yaz(rapor)
    print('\n'.join(rapor))
    return 0


def kaydet_kompakt(yol, veri):
    with open(yol, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(veri, f, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    sys.exit(oho_tazele() if '--yalniz-oho' in sys.argv else main())
