/* Guitar Comeback HQ service worker.
   Strategy: network-first for data.json and index.html (fresh when online),
   cache-first for everything else. Bump CACHE_VERSION when precached assets change. */
var CACHE_VERSION = 'gchq-v3';
var PRECACHE = ['.', 'index.html', 'data.json', 'backlog.json', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE_VERSION).then(function (c) {
    // Per-asset, not addAll(): addAll is atomic, so one missing file (backlog.json
    // before the first tools/ run) would fail the whole install.
    return Promise.all(PRECACHE.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE_VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  if (url.origin !== location.origin) return; // let tab links etc. go straight out
  var networkFirst = /(?:^|\/)(data\.json|backlog\.json|index\.html)?$/.test(url.pathname);
  if (networkFirst) {
    e.respondWith(
      fetch(e.request).then(function (res) {
        var copy = res.clone();
        caches.open(CACHE_VERSION).then(function (c) { c.put(e.request, copy); });
        return res;
      }).catch(function () { return caches.match(e.request); })
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(function (hit) { return hit || fetch(e.request); })
    );
  }
});
