/* Натяжка / TapTension — работа без интернета.
   Файлы приложения кешируются при первой загрузке; при каждом запуске кеш тихо обновляется из сети.
   При выпуске новой версии поменяйте VERSION. */
var VERSION = "natyazhka-v2.4";
var FILES = [
  "./",
  "index.html",
  "guide.html",
  "guide-en.html",
  "privacy.html",
  "manifest.json",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/apple-touch-icon.png"
];

self.addEventListener("install", function(e){
  e.waitUntil(
    caches.open(VERSION).then(function(c){ return c.addAll(FILES); }).then(function(){ return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function(e){
  e.waitUntil(
    caches.keys().then(function(keys){
      return Promise.all(keys.filter(function(k){ return k !== VERSION; }).map(function(k){ return caches.delete(k); }));
    }).then(function(){ return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function(e){
  var req = e.request;
  if(req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  e.respondWith(
    caches.open(VERSION).then(function(cache){
      return cache.match(req, { ignoreSearch: true }).then(function(hit){
        var net = fetch(req).then(function(res){
          if(res && res.ok && res.type === "basic") cache.put(req, res.clone());
          return res;
        }).catch(function(){ return hit; });
        return hit || net;
      });
    })
  );
});
