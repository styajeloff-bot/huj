import { useAuthStore } from '~/features/auth/store/auth'

export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return
  const authStore = useAuthStore()
  const authenticated = await authStore.checkAuth()
  if (!authenticated) return navigateTo('/auth')
  const hasCatalogScope = authStore.hasScope('special-equipment-catalog:read')
    || authStore.hasScope('special-equipment-catalog:write')
  if (!authStore.isCarCraftEmployee || !hasCatalogScope) return navigateTo('/workspace')
})
