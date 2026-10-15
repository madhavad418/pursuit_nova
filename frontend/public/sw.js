/**
 * Self-unregistering service worker.
 *
 * This app registers no service worker — nothing in `src/` calls `navigator.serviceWorker.register`.
 * But browsers that loaded an earlier build (or another project on the same localhost origin) can
 * still hold a registration for `/sw.js`, and a registration outlives the page that created it.
 *
 * That stale worker kept serving module responses from its own cache. Mixed with freshly built
 * ones it put two copies of React into the page, so `resolveDispatcher()` returned null and the
 * first hook in a lazily-loaded route threw "Cannot read properties of null (reading 'useState')" —
 * reliably when switching tabs, because that is when a route chunk is fetched.
 *
 * It could not fix itself: the browser re-fetches `/sw.js` to look for an update, and with no file
 * here that request fell through to the SPA fallback and came back as `index.html` with a 200. An
 * HTML body is not a valid worker script, so the update failed and the old worker stayed forever.
 *
 * Serving this file ends that loop. It takes over, drops every cache, unregisters itself and
 * reloads open tabs onto clean modules. It installs no `fetch` handler, so it never intercepts a
 * request while it is alive. A browser with no registration never requests this file at all, so
 * this is inert for everyone else.
 *
 * Keep it until the stale registrations are gone from the browsers that matter. Removing it earlier
 * puts those browsers straight back into the loop above.
 */
self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys()
      await Promise.all(keys.map(key => caches.delete(key)))
    } catch (err) {
      // Clearing is best-effort: unregistering still has to happen.
      console.warn('[SW] cache clear failed', err)
    }
    await self.registration.unregister()
    // Reload anything this worker was controlling, so the page re-fetches its modules from the
    // network instead of continuing on the half-cached graph that caused the crash.
    const clients = await self.clients.matchAll({ type: 'window' })
    for (const client of clients) {
      try { await client.navigate(client.url) } catch { /* a tab may refuse; the next load is clean anyway */ }
    }
    console.log('[SW] stale worker removed, caches cleared')
  })())
})
