/**
 * Global $fetch interceptor: silent token refresh on 401.
 *
 * When any API call returns 401 (access token expired), this wrapper:
 *   1. Serializes refresh attempts so parallel requests don't race
 *   2. Calls /api/v1/auth/refresh once
 *   3. Retries the original request with the new access token cookie
 *   4. If refresh fails → clears local auth state, broadcasts logout to
 *      sibling tabs, and redirects to /auth.
 *
 * This plugin runs AFTER csrf.client.ts (alphabetically "f" > "c"), so the
 * final call chain is:
 *   fetch-auth wrapper → csrf wrapper → original ofetch
 *
 * Auth endpoints (login, logout, refresh, register, verify-phone, resend-code)
 * are bypassed to avoid infinite loops.
 */

import { useAuthStore } from '~/features/auth/store/auth'

declare global {
  interface Error {
    _handledByAuthInterceptor?: boolean
  }
}

let isRefreshing = false
let refreshPromise: Promise<boolean> | null = null

/** Attempt refresh once; concurrent callers wait on the same promise. */
const tryRefresh = async (originalFetch: typeof globalThis.$fetch): Promise<boolean> => {
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }

  isRefreshing = true
  refreshPromise = (async () => {
    try {
      const config = useRuntimeConfig()
      await originalFetch('/api/v1/auth/refresh', {
        method: 'POST',
        baseURL: config.public.apiBase,
        credentials: 'include',
      })
      return true
    } catch {
      return false
    } finally {
      isRefreshing = false
      refreshPromise = null
    }
  })()

  return refreshPromise
}

const isAuthEndpoint = (request: unknown): boolean => {
  if (typeof request !== 'string') return false
  return (
    request.includes('/auth/refresh') ||
    request.includes('/auth/login') ||
    request.includes('/auth/logout') ||
    request.includes('/auth/register') ||
    request.includes('/auth/verify-phone') ||
    request.includes('/auth/resend-code')
  )
}

export default defineNuxtPlugin(() => {
  const originalFetch = globalThis.$fetch
  if (!originalFetch) return

  const wrappedFetch = async (request: any, options: any = {}) => {
    if (isAuthEndpoint(request)) {
      return originalFetch(request, options)
    }

    try {
      return await originalFetch(request, options)
    } catch (error: any) {
      if (error?.statusCode === 401 && !options?._skipAuthRefresh) {
        const refreshed = await tryRefresh(originalFetch)
        if (refreshed) {
          return await originalFetch(request, options)
        }

        // Refresh failed — tear down session
        const authStore = useAuthStore()
        authStore.logoutLocal()
        authStore.broadcastLogout()

        if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/auth')) {
          navigateTo('/auth')
        }

        error._handledByAuthInterceptor = true
        throw error
      }
      throw error
    }
  }

  // Wrap $fetch.create so feature API factories (which use $fetch.create)
  // still get the 401 → refresh → retry behaviour.
  wrappedFetch.create = (defaults: any) => {
    const created = originalFetch.create(defaults)

    const wrappedCreated = async (request: any, options: any = {}) => {
      if (isAuthEndpoint(request)) {
        return created(request, options)
      }

      try {
        return await created(request, options)
      } catch (error: any) {
        if (error?.statusCode === 401 && !options?._skipAuthRefresh) {
          const refreshed = await tryRefresh(originalFetch)
          if (refreshed) {
            return await created(request, options)
          }

          const authStore = useAuthStore()
          authStore.logoutLocal()
          authStore.broadcastLogout()

          if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/auth')) {
            navigateTo('/auth')
          }

          error._handledByAuthInterceptor = true
          throw error
        }
        throw error
      }
    }

    wrappedCreated.create = (overrideDefaults: any) => {
      return wrappedFetch.create({ ...defaults, ...overrideDefaults })
    }

    if ('native' in created) {
      ;(wrappedCreated as any).native = (created as any).native
    }
    if ('raw' in created) {
      ;(wrappedCreated as any).raw = (created as any).raw
    }

    return wrappedCreated
  }

  if ('native' in originalFetch) {
    ;(wrappedFetch as any).native = (originalFetch as any).native
  }
  if ('raw' in originalFetch) {
    ;(wrappedFetch as any).raw = (originalFetch as any).raw
  }

  globalThis.$fetch = wrappedFetch as any
})
