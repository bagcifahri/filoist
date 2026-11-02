"""uygulama/index.html dosyasından masaüstü sürümünün sayfasını üretir: masaustu/sayfa/

- Google Fonts bağlantıları yerine gömülü yazı tipleri (masaustu/fontlar) kullanılır.
- window.UYGULAMA = 'masaustu' işareti eklenir; sayfa bunu görünce Ayarlar bölümünü açar.

iPhone sürümü (iphone/pwa_hazirla.py) da sayfayı buradaki sayfa_uret ile üretir.
"""
import os, re, shutil

BURA = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURA)
FONTLAR = os.path.join(BURA, 'fontlar')
CIKTI = os.path.join(BURA, 'sayfa')


def sayfa_uret(uygulama, ek_head='', viewport='width=device-width, initial-scale=1'):
    """Ortak kaynak sayfayı tam bir HTML belgesine çevirir; yazı tipleri yerel, UYGULAMA işareti ekli."""
    html = open(os.path.join(KOK, 'uygulama', 'index.html'), encoding='utf-8').read()
    html, n = re.subn(r'<link rel="preconnect"[^>]*>\n|<link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]*>',
                      '', html)
    if n != 3:
        raise SystemExit(f'Google Fonts bağlantıları beklenen yerde değil ({n} bulundu)')
    html = html.replace('<style>', f'<link rel="stylesheet" href="fontlar/fontlar.css">\n{ek_head}'
                                   f'<script>window.UYGULAMA = "{uygulama}";</script>\n<style>', 1)
    return ('<!doctype html>\n<html lang="tr">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="{viewport}">\n'
            + html.replace('</style>', '</style>\n</head>\n<body>', 1) + '</body>\n</html>\n')


def klasor_hazirla(cikti, html):
    """Çıktı klasörünü sıfırdan kurar: sayfa, veri ve yazı tipleri."""
    if os.path.isdir(cikti):
        shutil.rmtree(cikti)
    shutil.copytree(FONTLAR, os.path.join(cikti, 'fontlar'))
    shutil.copy(os.path.join(KOK, 'uygulama', 'filo.js'), cikti)
    with open(os.path.join(cikti, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    klasor_hazirla(CIKTI, sayfa_uret('masaustu'))
    print('Masaüstü sayfası hazır:', CIKTI)


if __name__ == '__main__':
    main()
