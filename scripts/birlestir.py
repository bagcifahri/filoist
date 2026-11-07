"""ÖHO (emreunel159), İETT canlı filo listesi ve busphoto.eu verilerini tek veri setinde birleştirir.

Çıktı: veri/filo.json
"""
import json, os, re, sys, io, collections

import yazim

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAM = os.path.join(KOK, 'veri', 'ham')


def oku(ad):
    return json.load(open(os.path.join(HAM, ad), encoding='utf-8'))


def plaka_duzelt(p):
    if not p:
        return ''
    m = re.fullmatch(r'\s*(\d{2})\s*([A-ZÇĞİÖŞÜ]{1,3})\s*(\d{1,5})\s*', p.upper())
    return f'{m.group(1)} {m.group(2)} {m.group(3)}' if m else p.strip()


GARAJ = {
    'IKITELLIGARAJI': 'İkitelli', 'IKITELLIISLETTIRMEGARAJI2': 'İkitelli 2', 'SULTANGAZIGARAJI': 'Sultangazi',
    'KURTKÖY': 'Kurtköy', 'ADALAR': 'Adalar', 'TRAMVAY': 'Tramvay', 'BAŞAKŞEHİRGARAJI': 'Başakşehir',
}

# busphoto model adı -> (marka, model)
MARKALAR = [('Mercedes-Benz', 'Mercedes-Benz'), ('BredaMenarinibus', 'Karsan'), ('TEMSA', 'Temsa'),
            ('Akia', 'Akia'), ('BMC', 'BMC'), ('Otokar', 'Otokar'), ('Karsan', 'Karsan')]


def model_ayir(s):
    for on, marka in MARKALAR:
        if s.startswith(on):
            return marka, s[len(on):].strip()
    return '', s


# busphoto'da kaydı olmayan İETT araçları için seri aralıkları (Wikipedia + aynı serinin busphoto kayıtları)
SERILER = [
    ('G', 1001, 1020, 'Green Car', 'LSV 4', '2020'),
    ('G', 2001, 2040, 'Green Car', 'Shuttle 14', '2020'),
    ('G', 3001, 3060, 'SGMS', 'Mastiff M4', '2022'),
    ('G', 4001, 4050, 'Cleanvac', 'e-Micro', '2023'),
    ('G', 4051, 4060, 'Cleanvac', 'e-Micro', ''),
    ('K', 1001, 1248, 'Karsan', 'Avancity+ LU CNG', '2013'),
    ('K', 1501, 1810, 'Karsan', 'Avancity+ S', '2013'),
    ('M', 2001, 2394, 'Mercedes-Benz', 'O530 Citaro', '2006'),
    ('M', 2501, 2600, 'Mercedes-Benz', 'O530 Citaro G', '2006'),
    ('M', 4001, 4013, 'Mercedes-Benz', 'Conecto', '2012'),
    ('M', 4501, 4765, 'Mercedes-Benz', 'Conecto II G', '2012'),
    ('M', 4801, 4926, 'Mercedes-Benz', 'Conecto II G', '2015'),
    ('O', 1001, 3306, 'Otokar', 'Kent 290LF', '2013'),
    ('O', 4001, 4023, 'Otokar', 'Kent 290LF', '2012'),
    ('O', 4101, 4104, 'Otokar', 'Kent C 12', ''),
    ('O', 4105, 4108, 'Otokar', 'Kent C 12', '2023'),
    ('E', 1001, 1060, 'Karsan', 'e-Jest', '2024'),
]


def seri_bul(kapi):
    m = re.fullmatch(r'([A-Z])(\d{4})', kapi)
    if not m:
        return None
    for p, a, b, marka, model, yil in SERILER:
        if m.group(1) == p and a <= int(m.group(2)) <= b:
            return marka, model, yil
    return None


def operator_duzelt(s):
    s = re.sub(r'\s+', ' ', (s or '').strip())
    s = re.sub(r'Tic\.\s*A\.Ş\.?$', 'Tic. A.Ş.', s)
    return s


def main():
    ohm = oku('ohm.json')
    canli = oku('filo_konum.json')
    bp = oku('bp_iett.json')

    canli_iett = {r['KapiNo']: r for r in canli if '-' not in r['KapiNo']}
    bp_aktif, bp_cekilmis = {}, {}
    for r in bp:
        k = r.get('#', '')
        if not re.fullmatch(r'[A-Z]\d{4}', k):
            continue
        (bp_aktif if r['status'] == 'active' else bp_cekilmis).setdefault(k, r)

    araclar = []

    for r in ohm:
        hatlar = [h.strip() for h in re.split(r'\s+-\s+', r['BolgeAdi'] or '') if h.strip()]
        araclar.append({
            'filo': 'ÖHO', 'kapi': r['KapiKodu'], 'plaka': plaka_duzelt(r['Plaka']),
            'eskiPlaka': plaka_duzelt(r['exPlaka']), 'marka': r['MarkaAdi'] or '', 'model': r['ModelAdi'] or '',
            'yil': r['Yil'] or '', 'operator': operator_duzelt(r['IsletmeAdi']), 'hatlar': hatlar,
            'garaj': '', 'durum': 'Aktif', 'kaynak': 'emreunel159', 'not': '',
        })

    kaynak_sayac = collections.Counter()
    for kapi in sorted(set(canli_iett) | set(bp_aktif)):
        c = canli_iett.get(kapi)
        b = bp_aktif.get(kapi)
        if b and b['Model'].startswith('('):  # "(unknown)" gibi boş model kayıtları
            b = None
        w = bp_cekilmis.get(kapi)
        marka = model = yil = notu = ''
        if b:
            marka, model = model_ayir(b['Model'])
            yil = (b.get('Built') or '')[-4:]
            notu = b.get('Remarks', '')
            kaynak = 'busphoto'
        elif w:
            marka, model = model_ayir(w['Model'])
            yil = (w.get('Built') or '')[-4:]
            notu = w.get('Remarks', '')
            kaynak = 'busphoto'
        elif seri_bul(kapi):
            marka, model, yil = seri_bul(kapi)
            kaynak = 'seri aralığı'
        else:
            kaynak = 'bilinmiyor'
        if b and not yil and seri_bul(kapi):
            yil = seri_bul(kapi)[2]
        kaynak_sayac[kaynak] += 1

        if w and not b:
            durum = 'Şüpheli'
            notu = ('Filodan çıkmış görünüyor' + (f" ({w.get('To...')})" if w.get('To...') else '')
                    + (f'. {notu}' if notu else ''))
        elif not c:
            durum = 'Canlı listede yok'
        else:
            durum = 'Aktif'

        plaka = plaka_duzelt((c or {}).get('Plaka')) or plaka_duzelt((b or w or {}).get('Plate', ''))
        garaj = (c or {}).get('Garaj') or ''
        araclar.append({
            'filo': 'İETT', 'kapi': kapi, 'plaka': plaka, 'eskiPlaka': '', 'marka': marka, 'model': model,
            'yil': yil, 'operator': 'İETT', 'hatlar': [], 'garaj': GARAJ.get(garaj, garaj), 'durum': durum,
            'kaynak': kaynak, 'not': notu,
        })

    yazim.duzelt(araclar)  # OTOKAR ve Otokar tek marka sayılsın
    json.dump(araclar, open(os.path.join(KOK, 'veri', 'filo.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, separators=(',', ':'))

    print('Toplam araç:', len(araclar))
    print('Filo:', dict(collections.Counter(a['filo'] for a in araclar)))
    print('İETT model kaynağı:', dict(kaynak_sayac))
    print('Durum:', dict(collections.Counter(a['durum'] for a in araclar)))
    print('Marka:', collections.Counter(a['marka'] for a in araclar).most_common())
    print('Operatör:', collections.Counter(a['operator'] for a in araclar).most_common())
    print('Garaj:', collections.Counter(a['garaj'] for a in araclar if a['filo'] == 'İETT').most_common())
    print('Plakasız:', sum(1 for a in araclar if not a['plaka']), '| Yılsız:', sum(1 for a in araclar if not a['yil']))


if __name__ == '__main__':
    main()
