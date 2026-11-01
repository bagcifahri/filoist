const SURUM = 'filoist-c150faa4fc68';
const DOSYALAR = [
  "./",
  "filo.js",
  "fontlar/BarlowCondensed-600-latin-ext.woff2",
  "fontlar/BarlowCondensed-600-latin.woff2",
  "fontlar/BarlowCondensed-700-latin-ext.woff2",
  "fontlar/BarlowCondensed-700-latin.woff2",
  "fontlar/DotGothic16-400-latin-ext.woff2",
  "fontlar/DotGothic16-400-latin.woff2",
  "fontlar/IBMPlexMono-500-latin-ext.woff2",
  "fontlar/IBMPlexMono-500-latin.woff2",
  "fontlar/IBMPlexMono-600-latin-ext.woff2",
  "fontlar/IBMPlexMono-600-latin.woff2",
  "fontlar/IBMPlexSans-400-latin-ext.woff2",
  "fontlar/IBMPlexSans-400-latin.woff2",
  "fontlar/IBMPlexSans-500-latin-ext.woff2",
  "fontlar/IBMPlexSans-500-latin.woff2",
  "fontlar/IBMPlexSans-600-latin-ext.woff2",
  "fontlar/IBMPlexSans-600-latin.woff2",
  "fontlar/fontlar.css",
  "index.html",
  "manifest.webmanifest",
  "simgeler/apple-touch-icon.png",
  "simgeler/simge-192.png",
  "simgeler/simge-512.png"
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SURUM).then(c => c.addAll(DOSYALAR)).then(() => self.skipWaiting()));
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
