"""Filoist'in iPhone sürümünü (ana ekrana eklenebilen, internetsiz çalışan web uygulaması) üretir: iphone/site/

site/ klasörünün içeriği olduğu gibi GitHub Pages gibi bir adrese yüklenir; iPhone'da Safari ile açılıp
"Paylaş → Ana Ekrana Ekle" denir. Sayfa, exe ile aynı kaynaktan (uygulama/index.html) üretilir.
"""
import hashlib, json, os, shutil, sys

BURA = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURA)
sys.path.insert(0, os.path.join(KOK, 'masaustu'))
from sayfa_hazirla import sayfa_uret, klasor_hazirla  # noqa: E402
from simge_ciz import simgeleri_yaz  # noqa: E402

CIKTI = os.path.join(BURA, 'site')
BAND = '#14202b'

EK_HEAD = f'''<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="{BAND}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Filoist">
<link rel="apple-touch-icon" href="simgeler/apple-touch-icon.png">
<link rel="icon" type="image/png" href="simgeler/simge-192.png">
<style>
/* iPhone, 16 pikselden küçük yazılı kutulara dokununca sayfayı büyütür; bunu önlemek için */
input, select {{ font-size: 16px !important; }}
</style>
<script>
if ('serviceWorker' in navigator) addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {{}}));
</script>
'''

MANIFEST = {
    'name': 'Filoist',
    'short_name': 'Filoist',
    'description': 'İstanbul otobüs filosu: İETT ve özel halk otobüsleri',
    'lang': 'tr',
    'start_url': './',
    'scope': './',
    'display': 'standalone',
    'background_color': BAND,
    'theme_color': BAND,
    'icons': [
        {'src': 'simgeler/simge-192.png', 'sizes': '192x192', 'type': 'image/png'},
        {'src': 'simgeler/simge-512.png', 'sizes': '512x512', 'type': 'image/png'},
        {'src': 'simgeler/simge-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
    ],
}

# Önbellek adı dosyaların özetinden üretilir: veri ya da sayfa değişince telefon yeni sürümü indirir
# cache: 'reload': tarayıcının HTTP önbelleğindeki eski dosya yeni sürümün içine alınmasın (GitHub Pages 10 dk önbellekler)
SW = '''const SURUM = 'filoist-%s';
const DOSYALAR = %s;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SURUM).then(c => c.addAll(DOSYALAR.map(d => new Request(d, { cache: 'reload' })))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(adlar => Promise.all(adlar.filter(a => a !== SURUM).map(a => caches.delete(a))))
    .then(() => self.clients.claim()));
});

// Önce önbellek: uygulama internetsiz de açılır
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(r => r || fetch(e.request)));
});
'''


def main():
    klasor_hazirla(CIKTI, sayfa_uret('iphone', EK_HEAD, 'width=device-width, initial-scale=1, viewport-fit=cover'))
    simgeleri_yaz(os.path.join(CIKTI, 'simgeler'))
    with open(os.path.join(CIKTI, 'manifest.webmanifest'), 'w', encoding='utf-8') as f:
        json.dump(MANIFEST, f, ensure_ascii=False, indent=2)
    # GitHub Pages dosyaları olduğu gibi sunsun
    open(os.path.join(CIKTI, '.nojekyll'), 'w').close()
    # Günlük taramanın zamanı; her gün değiştiği için önbelleğe alınmaz, yoksa uygulama her gün yeniden inerdi
    durum = os.path.join(KOK, 'veri', 'durum.json')
    if os.path.exists(durum):
        shutil.copy(durum, CIKTI)

    dosyalar, ozet = ['./'], hashlib.sha256()
    for kok, _, adlar in os.walk(CIKTI):
        for ad in sorted(adlar):
            if ad in ('sw.js', '.nojekyll', 'durum.json'):
                continue
            yol = os.path.join(kok, ad)
            goreli = os.path.relpath(yol, CIKTI).replace(os.sep, '/')
            dosyalar.append(goreli)
            ozet.update(goreli.encode() + open(yol, 'rb').read())
    with open(os.path.join(CIKTI, 'sw.js'), 'w', encoding='utf-8') as f:
        f.write(SW % (ozet.hexdigest()[:12], json.dumps(sorted(dosyalar), indent=2)))
    print('iPhone sürümü hazır:', CIKTI, '|', len(dosyalar), 'dosya önbelleğe alınacak')


if __name__ == '__main__':
    main()
