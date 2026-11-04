"""GitHub'daki güncel veriyi bilgisayardaki projeye indirir.

Veriler her gün GitHub'da otomatik taranıp güncellendiği için en güncel hali depodadır (bagcifahri/filoist).
yayinla.py ve exe/APK derleme betikleri önce bunu çalıştırır; böylece eski veriyle yayın ya da derleme yapılmaz.
İnternet yoksa uyarı verir ve bilgisayardaki veriyle devam edilir (çıkış kodu yine 0); --zorunlu verilirse 1 döner.
"""
import os, shutil, subprocess, sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAYIN = os.path.join(KOK, 'iphone', 'yayin')
DEPO = 'https://github.com/bagcifahri/filoist.git'
VERI_DOSYALARI = ['veri/filo.json', 'veri/durum.json', 'veri/iett_canli.json', 'veri/busphoto.json']


def git(*args):
    return subprocess.run(['git', '-C', YAYIN, *args], check=True, text=True, encoding='utf-8',
                          capture_output=True).stdout


def esitle():
    """Depoyu çeker ve veri dosyalarını projeye kopyalar. Başarısızsa hata fırlatır."""
    if not os.path.isdir(os.path.join(YAYIN, '.git')):
        subprocess.run(['git', 'clone', '-q', DEPO, YAYIN], check=True)
        # E-posta adresi görünmesin diye GitHub'ın gizli adresi kullanılır
        git('config', 'user.name', 'Fahri')
        git('config', 'user.email', '342485943+bagcifahri@users.noreply.github.com')
    git('fetch', '-q', 'origin', 'main')
    # Yerel kopya yalnızca yayın aracı; içeriği her zaman GitHub'dakiyle aynı olmalı
    git('reset', '-q', '--hard', 'origin/main')
    yeni = 0
    for goreli in VERI_DOSYALARI:
        kaynak, hedef = os.path.join(YAYIN, goreli), os.path.join(KOK, goreli)
        if not os.path.exists(kaynak):
            continue
        if not os.path.exists(hedef) or open(kaynak, 'rb').read() != open(hedef, 'rb').read():
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            shutil.copyfile(kaynak, hedef)
            yeni += 1
    print(f'GitHub verisi alındı ({yeni} dosya güncellendi)' if yeni else 'Veri zaten güncel')
    uygulama_verisini_uret()


def uygulama_verisini_uret():
    """Uygulamanın veri dosyası (uygulama/filo.js) indirilmez, buradan üretilir: böylece bilgisayardaki
    teknik özellikler (veri/teknik.json) GitHub'daki eski bir filo.js ile ezilmez."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import uygulama_verisi
    uygulama_verisi.yaz()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        esitle()
    except Exception as e:
        print('UYARI: GitHub\'daki güncel veri alınamadı, bilgisayardaki veri kullanılacak.', e)
        # İnternet yokken de teknik özelliklerdeki değişiklikler derlemeye girsin
        uygulama_verisini_uret()
        return 1 if '--zorunlu' in sys.argv else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
