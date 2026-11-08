"""veri/filo.json dosyasını uygulamanın yüklediği sıkıştırılmış uygulama/filo.js dosyasına çevirir.

Uygulamada gösterilen "son güncelleme" tarihi veri/durum.json içindeki veriGuncelleme alanından alınır.
Model başına teknik özellikler veri/teknik.json dosyasından eklenir.
"""
import datetime, json, os

import yazim

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALANLAR = ['filo', 'kapi', 'plaka', 'eskiPlaka', 'marka', 'model', 'yil', 'operator', 'hatlar', 'garaj', 'durum', 'kaynak', 'not']
AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık']


def tarih_yazi(iso):
    """'2026-11-02T09:03:00+03:00' -> '2 Kasım 2026, 09:03' (saat yoksa yalnız tarih)."""
    t = datetime.datetime.fromisoformat(iso)
    yazi = f'{t.day} {AYLAR[t.month - 1]} {t.year}'
    return yazi + (f', {t:%H:%M}' if 'T' in iso else '')


# Araç tipi filtresi: teknik bilgideki ayrıntılı tip ("12 m solo şehir içi otobüs, doğal gazlı") birkaç gruba indirilir.
# Sıra önemli: "körüklü metrobüs" metrobüs, "elektrikli minibüs" minibüs sayılır.
SINIFLAR = [('küçük', 'Elektrikli küçük araç'), ('minibüs', 'Minibüs'), ('midibüs', 'Midibüs'),
            ('çift katlı', 'Çift katlı otobüs'), ('metrobüs', 'Metrobüs'), ('körüklü', 'Körüklü otobüs'),
            ('şehirler arası', 'Şehirler arası otobüs'), ('otobüs', 'Solo otobüs')]


def arac_sinifi(tip):
    tip = (tip or '').lower()
    return next((ad for parca, ad in SINIFLAR if parca in tip), '')


def yaz():
    # Depodaki veri eski yazımla kalmış olsa bile uygulamaya tek yazım gider
    araclar = yazim.duzelt(json.load(open(os.path.join(KOK, 'veri', 'filo.json'), encoding='utf-8')))
    durum_yolu = os.path.join(KOK, 'veri', 'durum.json')
    iso = json.load(open(durum_yolu, encoding='utf-8'))['veriGuncelleme'] if os.path.exists(durum_yolu) else '2026-11-01'
    # Hat ayracı boşluk olamaz: "48N Sabit" gibi hat adlarında boşluk var
    satirlar = [['|'.join(a[k]) if k == 'hatlar' else a[k] for k in ALANLAR] for a in araclar]
    veri = {'alanlar': ALANLAR, 'satirlar': satirlar, 'tarih': tarih_yazi(iso)}
    # Model başına teknik özellikler; detay panelinde gösterilir
    teknik_yolu = os.path.join(KOK, 'veri', 'teknik.json')
    if os.path.exists(teknik_yolu):
        teknik = json.load(open(teknik_yolu, encoding='utf-8'))
        modeller = {k: {**m, 'sinif': arac_sinifi(m.get('tip'))} for k, m in teknik['modeller'].items()}
        veri['teknik'] = {'modeller': modeller, 'kaynaklar': teknik['kaynaklar']}

    os.makedirs(os.path.join(KOK, 'uygulama'), exist_ok=True)
    with open(os.path.join(KOK, 'uygulama', 'filo.js'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('window.FILO=' + json.dumps(veri, ensure_ascii=False, separators=(',', ':')) + ';\n')
    print(len(satirlar), 'araç yazıldı |', veri['tarih'])


if __name__ == '__main__':
    yaz()
