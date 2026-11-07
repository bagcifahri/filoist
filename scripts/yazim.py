"""Yalnızca büyük/küçük harfi farklı olan adları tek yazıma indirir (OTOKAR ve Otokar aynı markadır).

Kaynaklar aynı adı farklı yazabiliyor; uygulamada her ad ayrı kategori sayıldığı ve teknik özellikler
"Marka|Model" anahtarıyla bulunduğu için marka, model, operatör, garaj ve hatlar tek yazıma indirilir.

Hangi yazımın kalacağı:
1. Marka ve model veri/teknik.json'da varsa oradaki yazım (BMC|Procity, Tezeller|AutoBus LF1200).
2. Yoksa karışık harfli yazım, sonra tamamı büyük, en son tamamı küçük olan; aynı türde en çok kullanılanı.
3. Tek yazım varsa olduğu gibi kalır (yeni bir model raporda teknik eksiği olarak görünür).
"""
import collections, json, os

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def anahtar(s):
    """Karşılaştırma anahtarı: büyük harf ve fazla boşluk yok sayılır. Türkçede I/İ/ı farkı da
    harf büyüklüğünden doğar (CITARO, Citaro; SAFİR, Safir), hepsi aynı sayılır."""
    for harf in 'Iİı':
        s = s.replace(harf, 'i')
    return ' '.join(s.split()).casefold()


def _secim(cesitler):
    """En iyi yazım: karışık harfli (Otokar), sonra tamamı büyük (500T), en son tamamı küçük (500t).
    Aynı türde en çok kullanılan kalır; eşitlikte sonuç hep aynı olsun."""
    return min(cesitler, key=lambda y: (y.islower() * 2 or y.isupper() * 1, -cesitler[y], y))


def _teknik_yazimlar():
    yol = os.path.join(KOK, 'veri', 'teknik.json')
    if not os.path.exists(yol):
        return {}, {}
    markalar, modeller = {}, {}
    for ad in json.load(open(yol, encoding='utf-8'))['modeller']:
        marka, model = ad.split('|', 1)
        markalar[anahtar(marka)] = marka
        modeller[anahtar(marka), anahtar(model)] = model
    return markalar, modeller


def duzelt(araclar):
    """Aynı adın tüm yazımlarını birleştirir. Araçları yerinde değiştirir ve listeyi döndürür."""
    t_marka, t_model = _teknik_yazimlar()

    def harita(gruplar, bilinen):
        return {k: bilinen.get(k) or _secim(c) for k, c in gruplar.items()}

    gruplar = {alan: collections.defaultdict(collections.Counter) for alan in ('marka', 'model', 'operator', 'garaj', 'hat')}
    for a in araclar:
        for alan in ('marka', 'operator', 'garaj'):
            if a[alan]:
                gruplar[alan][anahtar(a[alan])][a[alan]] += 1
        if a['model']:
            gruplar['model'][anahtar(a['marka']), anahtar(a['model'])][a['model']] += 1
        for hat in a['hatlar']:
            gruplar['hat'][anahtar(hat)][hat] += 1

    markalar = harita(gruplar['marka'], t_marka)
    modeller = harita(gruplar['model'], t_model)
    operatorler = harita(gruplar['operator'], {})
    garajlar = harita(gruplar['garaj'], {})
    hatlar = harita(gruplar['hat'], {})

    for a in araclar:
        if a['model']:
            a['model'] = modeller[anahtar(a['marka']), anahtar(a['model'])]
        if a['marka']:
            a['marka'] = markalar[anahtar(a['marka'])]
        if a['operator']:
            a['operator'] = operatorler[anahtar(a['operator'])]
        if a['garaj']:
            a['garaj'] = garajlar[anahtar(a['garaj'])]
        a['hatlar'] = list(dict.fromkeys(hatlar[anahtar(h)] for h in a['hatlar']))  # sıra korunur, tekrar gider
    return araclar
