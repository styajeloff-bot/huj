import { useAuthStore } from '~/features/auth/store/auth'

export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return
  const authStore = useAuthStore()
  const authenticated = await authStore.checkAuth()
  if (!authenticated) return navigateTo('/auth')
  const scopes = authStore.userScopes
  const hasImportScope = scopes.includes('special-equipment-imports:read')
    || scopes.includes('special-equipment-imports:write')
    || scopes.includes('special-equipment-imports:apply')
  if (!authStore.isCarCraftEmployee || !hasImportScope) return navigateTo('/workspace')
})
