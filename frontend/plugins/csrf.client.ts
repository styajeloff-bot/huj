/**
 * CSRF token injection for all mutating requests.
 *
 * Contract with the backend (fastapi/presentation/middleware/csrf.py):
 *   - Backend sets a `csrfToken` cookie on login when CSRF_ENABLED=true.
 *   - Any POST / PUT / PATCH / DELETE must echo that value in the
 *     `X-CSRF-Token` header; otherwise the middleware rejects with 403.
 *   - Webhook / health / docs endpoints are exempt server-side.
 *
 * We wrap the global `$fetch` (ofetch) instance via `$fetch.create()` so
 * every `$fetch(...)` AND `useFetch(...)` call on the client picks up the
 * header transparently — no change required at the call site.
 *
 * If the cookie is absent (unauthenticated user) we skip the header so
 * public endpoints such as `/auth/login` remain callable.
 */

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export default defineNuxtPlugin(() => {
  // Nuxt ships a global `$fetch` from ofetch. Replacing it with a
  // preconfigured instance is the supported way to add default hooks
  // (see: https://nuxt.com/docs/getting-started/data-fetching#passing-headers-and-cookies).
  const originalFetch = globalThis.$fetch

  if (!originalFetch || typeof originalFetch.create !== 'function') {
    // Defensive: older / stripped builds. Nothing to wrap → bail out quietly.
    return
  }

  const wrapped = originalFetch.create({
    onRequest({ options }) {
      const rawMethod = options.method
      const method = typeof rawMethod === 'string' ? rawMethod.toUpperCase() : 'GET'
      if (!MUTATING_METHODS.has(method)) {
        return
      }

      // `useCookie` is auto-imported by Nuxt; reading it inside the hook
      // picks up the current value on every request (cookie may be set
      // mid-session after login).
      const token = useCookie<string | null>('csrfToken').value
      if (!token) {
        return
      }

      // `options.headers` can be a plain object, a `Headers` instance, or
      // an array of tuples. Normalize to `Headers` so we can set safely.
      const headers = new Headers(
        options.headers as HeadersInit | undefined,
      )
      if (!headers.has('X-CSRF-Token')) {
        headers.set('X-CSRF-Token', token)
      }
      options.headers = headers
    },
  })

  // Overwrite the global. `useFetch` internally resolves `$fetch` via
  // `useNuxtApp().$fetch ?? globalThis.$fetch`, so this covers both.
  globalThis.$fetch = wrapped
})
