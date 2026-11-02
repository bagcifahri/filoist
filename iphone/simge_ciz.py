"""Filoist uygulama simgesi: koyu zemin üzerinde otobüs tabelası gibi kehribar LED noktalarla yazılmış "F"."""
import os
from PIL import Image, ImageDraw, ImageFilter

BAND = (20, 32, 43)
PANEL = (28, 27, 22)
LED = (255, 176, 0)
SONUK = (58, 50, 30)
# 5x7 nokta matris "F"
F = ['11111',
     '10000',
     '10000',
     '11110',
     '10000',
     '10000',
     '10000']


def ciz(boyut=1024):
    img = Image.new('RGB', (boyut, boyut), BAND)
    d = ImageDraw.Draw(img)
    # Tabela paneli (iOS köşeleri kendisi yuvarlar; panel ortadaki güvenli alanda kalır)
    p0, p1 = int(boyut * 0.17), int(boyut * 0.83)
    d.rounded_rectangle([p0, p0, p1, p1], radius=int(boyut * 0.05), fill=PANEL)
    adim = (p1 - p0) / 9
    r = adim * 0.36
    yanan = Image.new('RGB', (boyut, boyut), (0, 0, 0))
    dy = ImageDraw.Draw(yanan)
    for sat in range(7):
        for sut in range(5):
            cx = p0 + adim * (sut + 2.5)
            cy = p0 + adim * (sat + 1.5)
            acik = F[sat][sut] == '1'
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=LED if acik else SONUK)
            if acik:
                dy.ellipse([cx - r * 1.3, cy - r * 1.3, cx + r * 1.3, cy + r * 1.3], fill=LED)
    # Hafif LED parlaması
    parilti = yanan.filter(ImageFilter.GaussianBlur(boyut * 0.02))
    return Image.blend(img, Image.composite(parilti, img, parilti.convert('L')), 0.35)


def simgeleri_yaz(klasor):
    os.makedirs(klasor, exist_ok=True)
    buyuk = ciz()
    for ad, b in (('apple-touch-icon.png', 180), ('simge-192.png', 192), ('simge-512.png', 512)):
        buyuk.resize((b, b), Image.LANCZOS).save(os.path.join(klasor, ad), optimize=True)
    return buyuk


if __name__ == '__main__':
    simgeleri_yaz(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'site', 'simgeler'))
