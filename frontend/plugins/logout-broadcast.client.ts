import { useAuthStore } from '~/features/auth/store/auth'

/**
 * Cross-tab logout synchronization.
 *
 * When the user logs out in ONE tab, every other open tab must drop its
 * in-memory auth state and navigate to `/auth`. Cookies are already cleared
 * server-side, but Pinia state in sibling tabs does not observe that.
 *
 * Primary transport: `BroadcastChannel` (Chrome, Firefox, Edge, Safari 15.4+).
 * Fallback: `storage` event for older Safari / privacy modes that stub out
 * BroadcastChannel. We never actually persist auth data — we toggle a
 * scratch key so the event fires in sibling tabs.
 *
 * The emitter side lives in `features/auth/store/auth.ts#broadcastLogout`;
 * this plugin only attaches the listeners.
 */

const CHANNEL_NAME = 'carcraft-auth'
const STORAGE_KEY = 'carcraft-auth-logout'
const LOGIN_PATH = '/auth'

interface LogoutMessage {
  type: 'logout'
  ts?: number
}

export default defineNuxtPlugin(() => {
  if (!process.client) return

  const authStore = useAuthStore()

  const handleRemoteLogout = () => {
    // Sibling tab already hit the backend logout endpoint — just purge our
    // local state and send the user to the login page. Using `logoutLocal`
    // avoids re-calling the logout API and the re-broadcast that would
    // cause.
    authStore.logoutLocal()
    // Best-effort redirect; suppress if we're already on the auth page.
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith(LOGIN_PATH)) {
      navigateTo(LOGIN_PATH)
    }
  }

  // --- Transport 1: BroadcastChannel (modern browsers) ---------------------
  let channel: BroadcastChannel | null = null
  if (typeof BroadcastChannel !== 'undefined') {
    try {
      channel = new BroadcastChannel(CHANNEL_NAME)
      channel.addEventListener('message', (event: MessageEvent) => {
        const data = event?.data as LogoutMessage | null
        if (data && data.type === 'logout') {
          handleRemoteLogout()
        }
      })
    } catch {
      // Some privacy modes throw on `new BroadcastChannel`. Fall back silently.
      channel = null
    }
  }

  // --- Transport 2: storage event (Safari fallback) ------------------------
  const handleStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY && event.newValue !== null) {
      handleRemoteLogout()
    }
  }
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', handleStorage)
  }

  // Cleanup for HMR — Nuxt plugins otherwise leak listeners in dev.
  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      channel?.close()
      if (typeof window !== 'undefined') {
        window.removeEventListener('storage', handleStorage)
      }
    })
  }
})
