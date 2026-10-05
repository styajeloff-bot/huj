import { useAuthStore } from '~/features/auth/store/auth'
import { useToast } from '~/composables/useToast'
import {
  WORKSPACE_MENU,
  isBusinessRoleName,
} from '~/features/workspace/config/menu'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { useStorefront } from '~/features/storefront'
import {
  findWorkspaceMenuItemForPath,
  getAvailableWorkspaceMenu,
  getFirstAvailableWorkspaceRoute,
  canAttemptWorkspaceNotificationTarget,
} from '~/features/workspace/utils/menuVisibility'
import {
  normalizeWorkspaceReturnLocation,
  toWorkspaceRouteLocation,
  WORKSPACE_RETURN_STOREFRONT_QUERY,
} from '~/features/workspace/returnContext'
import {
  recoverWorkspaceVisibilityTarget,
  resolveWorkspaceVisibilityScope,
  resolveWorkspaceVisibilityTarget,
  useWorkspaceReturnValidationCache,
} from '~/features/workspace/visibilityTarget'

/**
 * Restricts /workspace/* to business roles (dealer, leasing_company,
 * distributor, carcraft_employee). Clients are sent to their /cabinet.
 * Mirrors the checkAuth-first pattern from require-admin.ts.
 */
export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return

  const authStore = useAuthStore()
  const authed = await authStore.checkAuth()
  if (!authed) return navigateTo('/auth')

  if (!authStore.isBusinessRole) return navigateTo('/cabinet')

  const role = authStore.userRole
  if (!isBusinessRoleName(role)) return navigateTo('/cabinet')

  const visibilityStore = useSectionVisibilityStore()
  const storefront = useStorefront()
  const validationCache = useWorkspaceReturnValidationCache()
  const defaultStorefront = storefront.is_resolved.value
    && storefront.is_default.value
    && storefront.id.value
    ? { id: storefront.id.value, slug: null }
    : null
  const visibilityScope = resolveWorkspaceVisibilityScope(role)
  const target = visibilityScope
    ? resolveWorkspaceVisibilityTarget(
        visibilityScope,
        to.query[WORKSPACE_RETURN_STOREFRONT_QUERY],
        validationCache.value,
        defaultStorefront,
      )
    : null

  if (!target) {
    const normalized = normalizeWorkspaceReturnLocation(toWorkspaceRouteLocation(to), null)
    if (normalized) return navigateTo(normalized, { replace: true })
    throw createError({
      statusCode: 503,
      statusMessage: 'Настройки рабочего кабинета временно недоступны',
    })
  }

  await visibilityStore.load(target)
  const recovery = recoverWorkspaceVisibilityTarget(
    target,
    visibilityStore.statusFor(target).statusCode,
    toWorkspaceRouteLocation(to),
    validationCache.value,
  )
  if (recovery) return navigateTo(recovery, { replace: true })

  if (to.path === '/workspace') return

  const visibility = visibilityStore.visibilityFor(target)
  const availableItems = getAvailableWorkspaceMenu(role, authStore, visibility)
  const routeItem = findWorkspaceMenuItemForPath(WORKSPACE_MENU[role], to.path)

  if (routeItem && !availableItems.some((item) => item.key === routeItem.key)
    && !canAttemptWorkspaceNotificationTarget(role, to.path, to.query, visibility)) {
    if (process.client) {
      try {
        const toast = useToast()
        toast.error('У вас нет доступа к этому разделу')
      } catch {}
    }
    return navigateTo(getFirstAvailableWorkspaceRoute(role, authStore, visibility))
  }
})
