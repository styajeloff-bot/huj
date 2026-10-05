import type { Ref } from 'vue'

import {
  isStorefrontVisibilityScope,
  isWorkspaceVisibilityScope,
} from '~/features/sectionVisibility/config'
import type {
  SectionVisibilityTarget,
  VisibilityStorefrontTarget,
  WorkspaceVisibilityScope,
} from '~/features/sectionVisibility/types'
import { useStorefront } from '~/features/storefront'
import {
  normalizeWorkspaceReturnLocation,
  readValidatedWorkspaceReturnStorefront,
  WORKSPACE_RETURN_STOREFRONT_QUERY,
  WORKSPACE_RETURN_VALIDATION_STATE,
  type WorkspaceQueryValue,
  type WorkspaceReturnValidationCache,
  type WorkspaceRouteLocation,
} from '~/features/workspace/returnContext'

export const resolveWorkspaceVisibilityScope = (
  role: string | null | undefined,
): WorkspaceVisibilityScope | null => isWorkspaceVisibilityScope(role) ? role : null

export const resolveWorkspaceVisibilityTarget = (
  scope: WorkspaceVisibilityScope,
  returnStorefrontValue: WorkspaceQueryValue,
  validationCache: WorkspaceReturnValidationCache,
  defaultStorefront: VisibilityStorefrontTarget | null,
): SectionVisibilityTarget | null => {
  if (scope === 'carcraft_employee') return { scope, storefront: null }
  if (!isStorefrontVisibilityScope(scope)) return null

  const hasReturnContext = returnStorefrontValue !== undefined
  if (hasReturnContext) {
    const storefront = readValidatedWorkspaceReturnStorefront(
      returnStorefrontValue,
      validationCache,
    )
    return storefront ? { scope, storefront } : null
  }

  return defaultStorefront ? { scope, storefront: defaultStorefront } : null
}

export const recoverWorkspaceVisibilityTarget = (
  target: SectionVisibilityTarget,
  statusCode: number | null,
  route: WorkspaceRouteLocation,
  validationCache: WorkspaceReturnValidationCache,
): WorkspaceRouteLocation | null => {
  const slug = target.storefront?.slug
  if (!slug || statusCode !== 404) return null
  validationCache[slug] = null
  return normalizeWorkspaceReturnLocation(route, null)
}

export const useWorkspaceReturnValidationCache = () => useState<WorkspaceReturnValidationCache>(
  WORKSPACE_RETURN_VALIDATION_STATE,
  () => ({}),
)

export const useWorkspaceVisibilityTarget = (
  scope: Readonly<Ref<WorkspaceVisibilityScope | null>>,
) => {
  const route = useRoute()
  const validationCache = useWorkspaceReturnValidationCache()
  const storefront = useStorefront()

  return computed<SectionVisibilityTarget | null>(() => {
    const currentScope = scope.value
    if (!currentScope) return null
    const defaultStorefront = storefront.is_resolved.value
      && storefront.is_default.value
      && storefront.id.value
      ? { id: storefront.id.value, slug: null }
      : null
    return resolveWorkspaceVisibilityTarget(
      currentScope,
      route.query[WORKSPACE_RETURN_STOREFRONT_QUERY],
      validationCache.value,
      defaultStorefront,
    )
  })
}
