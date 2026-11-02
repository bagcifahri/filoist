"""Filoist'in kodunu GitHub'a gönderir; iPhone sürümünü GitHub yayınlar: https://bagcifahri.github.io/filoist/

GitHub deposu (bagcifahri/filoist) sitenin kaynağıdır. Depodaki iş akışı (.github/workflows/filoist.yml):
- her gün kaynakları tarar, değişiklik varsa veriyi günceller ve siteyi yeniden yayınlar;
- bu betikle kod gönderildiğinde siteyi yeniden üretip yayınlar.

Adımlar:
1. GitHub'daki güncel veri bilgisayara alınır (scripts/veri_esitle.py); veri hep depodan gelir.
   GitHub'ın ulaşamadığı İETT ve busphoto.eu kayıtları burada, Türkiye bağlantısıyla tazelenir.
2. iphone/pwa_hazirla.py ile site bilgisayarda da üretilir (hata varsa yükleme yapılmaz).
3. Kaynak dosyalar iphone/yayin/ (deponun yerel kopyası) klasörüne aktarılır, değişiklik varsa gönderilir.

Kimlik, bilgisayardaki Git kimlik yöneticisinden (GitHub hesabı) alınır.
"""
import datetime, os, shutil, subprocess, sys

BURA = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURA)
YAYIN = os.path.join(BURA, 'yayin')
sys.path.insert(0, os.path.join(KOK, 'scripts'))
import guncelle, veri_esitle  # noqa: E402

# Depoya giden dosyalar (proje köküne göre); klasörler tümüyle kopyalanır
KAYNAKLAR = [
    '.github/workflows/filoist.yml', '.gitignore',
    'uygulama/index.html', 'uygulama/filo.js', 'veri/filo.json', 'veri/durum.json', 'veri/iett_canli.json',
    'veri/busphoto.json',
    'scripts/guncelle.py', 'scripts/birlestir.py', 'scripts/uygulama_verisi.py', 'scripts/veri_esitle.py',
    'masaustu/sayfa_hazirla.py', 'masaustu/fontlar',
    'iphone/pwa_hazirla.py', 'iphone/simge_ciz.py', 'iphone/yayinla.py',
]


def git(*args, yakala=False):
    return subprocess.run(['git', '-C', YAYIN, *args], check=True, text=True, encoding='utf-8',
                          capture_output=yakala).stdout


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        veri_esitle.esitle()
    except Exception as e:
        # Güncel veri alınmadan gönderilirse GitHub'daki daha yeni veri eskisiyle ezilir
        sys.exit(f'GitHub\'daki güncel veri alınamadı, yayın yapılmadı: {e}')
    guncelle.yedekleri_tazele()
    subprocess.run([sys.executable, os.path.join(BURA, 'pwa_hazirla.py')], check=True)

    # Yerel kopya, KAYNAKLAR listesiyle birebir aynı olsun (.git hariç)
    for ad in os.listdir(YAYIN):
        if ad != '.git':
            yol = os.path.join(YAYIN, ad)
            shutil.rmtree(yol) if os.path.isdir(yol) else os.remove(yol)
    for goreli in KAYNAKLAR:
        kaynak, hedef = os.path.join(KOK, goreli), os.path.join(YAYIN, goreli)
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        shutil.copytree(kaynak, hedef) if os.path.isdir(kaynak) else shutil.copyfile(kaynak, hedef)

    git('add', '-A')
    if not git('status', '--porcelain', yakala=True).strip():
        print('Değişiklik yok, yüklenecek bir şey bulunmadı.')
        return
    git('commit', '-q', '-m', 'Filoist güncellemesi ' + datetime.datetime.now().strftime('%d.%m.%Y %H:%M'))
    git('push', '-q', 'origin', 'HEAD:main')
    print('Gönderildi. GitHub siteyi birkaç dakika içinde yayınlar: https://bagcifahri.github.io/filoist/')
    print('İlerleme: https://github.com/bagcifahri/filoist/actions')


if __name__ == '__main__':
    main()
