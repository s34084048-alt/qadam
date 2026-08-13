/*
 * QADAM service worker.
 *
 * WHAT IS CACHED, AND WHAT DELIBERATELY IS NOT.
 *
 * Cached: the app shell, and the reference data that never describes a
 * patient — the module catalogue, the safety boundary, the analyte catalogue,
 * the foot risk model, and the emergency positioning reference. The emergency
 * reference matters most here: a responder needs it at a roadside, which is
 * exactly where there is no signal.
 *
 * NOT cached: anything about a patient. Cases, images, overlays, lab panels
 * and filed reports are never written to the cache. A cached patient record
 * would sit on a shared clinic device indefinitely, outside the erasure path
 * that the API guarantees — so the answer to "can I read old cases offline"
 * is no, on purpose.
 */

const SHELL = 'qadam-shell-v1'
const REFERENCE = 'qadam-reference-v1'

// Patient-free reference endpoints, safe to serve stale.
const REFERENCE_PATHS = [
  '/api/v1/modules',
  '/api/v1/safety',
  '/api/v1/health',
  '/api/v1/labs/catalogue',
  '/api/v1/foot/risk-model',
  '/api/v1/reference/emergency',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL).then((cache) => cache.addAll(['/', '/index.html']))
      .catch(() => undefined)
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== SHELL && k !== REFERENCE)
            .map((k) => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  )
})

function isReference(url) {
  return REFERENCE_PATHS.some((path) => url.pathname === path)
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // Reference data: serve from network, fall back to cache when offline.
  if (isReference(url)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(REFERENCE).then((cache) => cache.put(request, copy))
          }
          return response
        })
        .catch(() => caches.match(request).then((cached) => cached ?? Response.json(
          {
            error: {
              code: 'offline_no_cache',
              message: 'This reference has not been loaded on this device yet, '
                       + 'and there is no connection to fetch it.',
              hint: 'Open the app once while online to store it for offline use.',
              details: {},
            },
          },
          { status: 503 },
        ))),
    )
    return
  }

  // Every other API call is network-only. Patient data is never cached.
  if (url.pathname.startsWith('/api/')) return

  // App shell: cache-first, then populate. After one successful online visit
  // the interface opens with no connection.
  event.respondWith(
    caches.match(request).then((cached) => {
      const network = fetch(request)
        .then((response) => {
          if (response.ok && response.type === 'basic') {
            const copy = response.clone()
            caches.open(SHELL).then((cache) => cache.put(request, copy))
          }
          return response
        })
        .catch(() => cached ?? caches.match('/index.html'))
      return cached ?? network
    }),
  )
})
