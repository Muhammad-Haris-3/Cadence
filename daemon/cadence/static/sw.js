// Minimal service worker.
//
// Its job is not offline support -- the data lives on this machine and the
// daemon is either running or there is nothing to show. It exists so Chrome
// treats the dashboard as installable, and so the app window opens to a shell
// instead of a connection error when the daemon happens to be stopped.
//
// Network-first everywhere: a cached dashboard showing yesterday's numbers
// would be worse than a brief blank.

const SHELL = "cadence-shell-v1";
const SHELL_FILES = [
  "/",
  "/static/icons/icon-192.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  // Never serve stale data. If the API is unreachable, the page says so itself.
  if (new URL(request.url).pathname.startsWith("/api/")) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok && request.mode === "navigate") {
          const copy = response.clone();
          caches.open(SHELL).then((cache) => cache.put("/", copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match("/")))
  );
});
