import { useAuthStore } from '~/features/auth/store/auth'

/**
 * On /cabinet: business roles belong in the fullscreen /workspace area,
 * so bounce them there. Clients stay.
 */
export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return

  const authStore = useAuthStore()
  const authed = await authStore.checkAuth()
  if (!authed) return

  if (authStore.isBusinessRole) return navigateTo('/workspace')
})
