import { useAuthStore } from '~/features/auth/store/auth'

/**
 * Route middleware: restricts access to users with the `auth:admin` scope.
 *
 * - Must run AFTER `auth` (or be combined with it) so that `user` is hydrated.
 *   For pages under `pages/admin/**` we declare both middlewares to be explicit.
 * - Scope check uses `hasAdminScope` which falls back to the `carcraft_employee`
 *   role when the backend has not yet emitted scopes on the JWT — keeps the
 *   UI working during the incremental rollout on the backend side.
 * - Redirects to `/` (not `/auth`) because the user IS authenticated, they
 *   just lack the privilege; sending them to `/auth` would be confusing.
 */
export default defineNuxtRouteMiddleware(async () => {
  if (import.meta.server) return

  const authStore = useAuthStore()

  const authed = await authStore.checkAuth()
  if (!authed) {
    return navigateTo('/auth')
  }

  if (!authStore.hasAdminScope) {
    return navigateTo('/')
  }
})
