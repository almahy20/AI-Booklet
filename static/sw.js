const CACHE_NAME = 'ai-booklet-v2';
const ASSETS_TO_CACHE = [
  '/',
  '/static/style.css',
  '/static/manifest.json',
  '/static/html2pdf.bundle.min.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            return caches.delete(name);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // For API calls and dynamic live PDF / download requests, always use network directly
  if (url.pathname.startsWith('/api/') || url.pathname.includes('pdf') || url.pathname.includes('download')) {
    return;
  }

  // Network first with cache fallback for HTML and static resources
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful GET responses for static files
        if (response.status === 200 && event.request.method === 'GET' && url.pathname.startsWith('/static/')) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
        }
        return response;
      })
      .catch(() => {
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          if (event.request.headers.get('accept')?.includes('text/html')) {
            return caches.match('/');
          }
        });
      })
  );
});
