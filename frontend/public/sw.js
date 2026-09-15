/* eslint-disable no-restricted-globals */
// Rip N' Flip — Service Worker
// Cache-first for app shell, network-first for API + dynamic content,
// offline fallback page for navigation.

const VERSION = 'ripnflip-sw-v1';
const STATIC_CACHE = `${VERSION}-static`;
const RUNTIME_CACHE = `${VERSION}-runtime`;

const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/offline.html',
  '/icon-192.png',
  '/icon-512.png',
  '/apple-touch-icon.png',
  '/favicon.ico',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) =>
      cache.addAll(STATIC_ASSETS).catch(() => {
        // Don't block install on cache failure
      })
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((k) => !k.startsWith(VERSION))
          .map((k) => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

const isSameOrigin = (url) => new URL(url, self.location.href).origin === self.location.origin;

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Only handle GET
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // API requests + auth callbacks → always network, never cache (always fresh)
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) {
    return; // let browser handle naturally
  }

  // Same-origin navigations → network-first, fall back to cache, then offline.html
  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const fresh = await fetch(request);
          // cache the latest navigation HTML for offline use
          const cache = await caches.open(RUNTIME_CACHE);
          cache.put(request, fresh.clone()).catch(() => {});
          return fresh;
        } catch (e) {
          const cached = await caches.match(request);
          if (cached) return cached;
          const offline = await caches.match('/offline.html');
          if (offline) return offline;
          return new Response('Offline', { status: 503, statusText: 'Offline' });
        }
      })()
    );
    return;
  }

  // Static same-origin assets → stale-while-revalidate
  if (isSameOrigin(request.url)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(RUNTIME_CACHE);
        const cached = await cache.match(request);
        const networkPromise = fetch(request)
          .then((res) => {
            if (res && res.status === 200 && res.type === 'basic') {
              cache.put(request, res.clone()).catch(() => {});
            }
            return res;
          })
          .catch(() => cached);
        return cached || networkPromise;
      })()
    );
  }
  // Cross-origin (eBay images, Google fonts) → let browser handle
});

// Allow page to trigger immediate update
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});


// ─── Push notifications — Dethrone "Heart Attack" nudge ───
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'Rip N\' Flip', body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'Rip N\' Flip';
  const options = {
    body: data.body || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: data.notification_id || 'ripnflip-notification',
    data: {
      url: data.url || '/binders',
      notification_id: data.notification_id,
      type: data.type,
    },
    vibrate: [200, 80, 200],
    requireInteraction: data.type === 'dethrone',
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/binders';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.postMessage({ type: 'NOTIFICATION_CLICK', url: targetUrl });
          return client.focus().then((c) => c && c.navigate && c.navigate(targetUrl));
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl);
    })
  );
});
