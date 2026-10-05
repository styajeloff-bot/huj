import { useAuthStore } from '~/features/auth/store/auth'
import type { UUID } from '~/types/ids'

/**
 * Wraps localStorage so each authenticated user gets an isolated namespace.
 *
 * Two reasons we never share a single global key across logins:
 *   1. switching accounts in the same browser would otherwise leak state
 *      (one user's calculator/filters/cart preview overwrites another's);
 *   2. logout-without-clear leaves stale data behind that re-appears on
 *      the next login.
 *
 * Usage:
 *   const storage = useScopedStorage('cart-calculator-state')
 *   storage.set({...})
 *   storage.get()
 *   storage.remove()
 *
 * Suffix scheme: `<key>:u<id>` for logged-in users, `<key>:guest` otherwise.
 * Old unscoped keys are cleaned up by `clearLegacy(baseKey)` so we don't
 * carry pre-refactor data into a user's namespace by accident.
 */

export interface ScopedStorage<T> {
  key: () => string
  get: () => T | null
  set: (value: T) => void
  remove: () => void
}

export function useScopedStorage<T = unknown>(baseKey: string): ScopedStorage<T> {
  const authStore = useAuthStore()

  const key = () => {
    const user = authStore.user as { id?: UUID } | null
    if (user && (user.id !== undefined && user.id !== null)) {
      return `${baseKey}:u${user.id}`
    }
    return `${baseKey}:guest`
  }

  const safeWindow = () =>
    typeof window !== 'undefined' && window.localStorage ? window.localStorage : null

  return {
    key,
    get(): T | null {
      const ls = safeWindow()
      if (!ls) return null
      try {
        const raw = ls.getItem(key())
        return raw === null ? null : (JSON.parse(raw) as T)
      } catch {
        return null
      }
    },
    set(value: T) {
      const ls = safeWindow()
      if (!ls) return
      try {
        ls.setItem(key(), JSON.stringify(value))
      } catch {
        // out of quota / serialization — silently swallow
      }
    },
    remove() {
      const ls = safeWindow()
      if (!ls) return
      try {
        ls.removeItem(key())
      } catch {
        // ignore
      }
    },
  }
}

/** Best-effort migration: drop the old unscoped key once. */
export function clearLegacy(baseKey: string): void {
  if (typeof window === 'undefined' || !window.localStorage) return
  try {
    window.localStorage.removeItem(baseKey)
  } catch {
    // ignore
  }
}
