/* Only static files and a generic offline screen are cached. Never cache API/private data. */
const CACHE = 'queuewise-shell-v3';
const SHELL = ['/','/offline','/static/css/styles.css','/static/js/app.js','/static/icons/icon-192.png','/static/icons/icon-512.png'];
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
    event.respondWith(caches.match(request).then(hit => hit || fetch(request)));
  }
});
