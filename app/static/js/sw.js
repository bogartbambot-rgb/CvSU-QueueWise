/* Only static files and a generic offline screen are cached. Never cache API/private data. */
const CACHE = 'queuewise-shell-v110';
const SHELL = ['/','/offline','/static/css/styles.css','/static/css/auth.css','/static/js/app.js','/static/icons/icon-192.png','/static/icons/icon-512.png','/manifest.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/offline')));
    return;
  }
  if (request.method === 'GET' && (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest')) {
    // Network-first avoids an old cached JavaScript/CSS file hiding a new UI update.
    event.respondWith(fetch(request).then(response => {
      if (response.ok && (url.pathname.startsWith('/static/') || url.pathname === '/manifest.webmanifest')) {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(request, copy));
      }
      return response;
    }).catch(() => caches.match(request)));
  }
});
