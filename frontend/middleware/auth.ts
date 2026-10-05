import { useAuthStore } from '~/features/auth/store/auth'

export default defineNuxtRouteMiddleware(async (to) => {
  const authStore = useAuthStore()

  if (import.meta.server) return

  const isAuthenticated = await authStore.checkAuth()

  if (!isAuthenticated) {
    return navigateTo({
      path: '/auth',
      query: { redirect: to.fullPath }
    })
  }
})