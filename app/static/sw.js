const CACHE_NAME = "pivitlabs-oetsv-v1.5.0";
const STATIC_ASSETS = [
  "/",
  "/static/css/style.css?v=1.5.0",
  "/static/js/app.js?v=1.5.0",
  "/static/img/pivitlabs-logo.png",
  "/static/img/practice-studio-logo.png",
  "/static/img/icon-192.png",
  "/static/img/icon-512.png",
  "/manifest.webmanifest"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Network-first for API & dynamic endpoints, fallback to cache for static shell
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/adsi-admin")) {
    return;
  }
  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req))
  );
});
