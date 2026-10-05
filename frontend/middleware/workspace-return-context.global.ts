import { createPublicStorefrontApi, useStorefront } from '~/features/storefront'
import {
  isWorkspacePath,
  normalizeWorkspaceReturnLocation,
  readWorkspaceReturnStorefront,
  resolveWorkspaceReturnRedirect,
  toWorkspaceRouteLocation,
  WORKSPACE_RETURN_STOREFRONT_QUERY,
  WORKSPACE_RETURN_VALIDATION_STATE,
  type WorkspaceReturnValidationCache,
} from '~/features/workspace/returnContext'

export default defineNuxtRouteMiddleware(async (to, from) => {
  const target = toWorkspaceRouteLocation(to)
  if (!isWorkspacePath(to.path)) return

  const validationCache = useState<WorkspaceReturnValidationCache>(
    WORKSPACE_RETURN_VALIDATION_STATE,
    () => ({}),
  )
  const sourceStorefrontSlug = readWorkspaceReturnStorefront(from.params.storefrontSlug)
  const currentStorefront = useStorefront()
  if (
    sourceStorefrontSlug
    && currentStorefront.is_resolved.value
    && currentStorefront.is_active.value
    && !currentStorefront.is_default.value
    && currentStorefront.id.value
    && currentStorefront.slug.value === sourceStorefrontSlug
  ) {
    validationCache.value[sourceStorefrontSlug] = {
      id: currentStorefront.id.value,
      slug: sourceStorefrontSlug,
    }
  }

  const redirect = resolveWorkspaceReturnRedirect(
    {
      ...toWorkspaceRouteLocation(from),
      storefrontSlug: sourceStorefrontSlug,
    },
    target,
  )
  if (redirect) return navigateTo(redirect, { replace: true })

  const rawReturnStorefront = to.query[WORKSPACE_RETURN_STOREFRONT_QUERY]
  if (rawReturnStorefront === undefined) return

  const requestedSlug = readWorkspaceReturnStorefront(rawReturnStorefront)
  let resolvedSlug: string | null = null
  if (requestedSlug && Object.hasOwn(validationCache.value, requestedSlug)) {
    resolvedSlug = validationCache.value[requestedSlug]?.slug ?? null
  } else if (requestedSlug) {
    let resolvedStorefront: WorkspaceReturnValidationCache[string] = null
    try {
      const storefront = await createPublicStorefrontApi(useRuntimeConfig()).resolve(requestedSlug)
      if (storefront.is_active && !storefront.is_default && storefront.slug) {
        resolvedSlug = storefront.slug
        resolvedStorefront = {
          id: storefront.id,
          slug: storefront.slug,
        }
        validationCache.value[resolvedSlug] = resolvedStorefront
      }
    } catch {
      // An unresolvable return context is removed below; workspace stays global.
    }
    validationCache.value[requestedSlug] = resolvedStorefront
  }

  const normalized = normalizeWorkspaceReturnLocation(target, resolvedSlug)
  if (normalized) return navigateTo(normalized, { replace: true })
})
