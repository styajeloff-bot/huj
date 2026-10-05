import { resolveSectionVisibilityApiBase } from '../apiBase'
import type {
  AdminSectionVisibilityMatrices,
  GlobalVisibilityScope,
  SectionVisibilityMatrix,
  SectionVisibilityTarget,
  StorefrontVisibilityScope,
  UpdateSectionVisibilityPayload,
} from '../types'
import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

const runtimePath = (target: SectionVisibilityTarget): string => {
  if (target.scope === 'public') {
    return target.storefront.slug
      ? `/api/v1/storefronts/${encodeURIComponent(target.storefront.slug)}/section-visibility/public`
      : '/api/v1/section-visibility/public'
  }
  if (target.storefront?.slug) {
    return `/api/v1/storefronts/${encodeURIComponent(target.storefront.slug)}/workspace/section-visibility`
  }
  return '/api/v1/workspace/section-visibility'
}

export const createSectionVisibilityApi = (config: RuntimeConfig) => {
  const baseURL = resolveSectionVisibilityApiBase(config, import.meta.server)
  const forwardedAuthHeaders = import.meta.server
    ? useRequestHeaders(['cookie', 'authorization'])
    : {}
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL,
      credentials: 'include',
      headers: forwardedAuthHeaders,
      ...options,
    })

  return {
    getRuntime: (target: SectionVisibilityTarget) => request<SectionVisibilityMatrix>(
      runtimePath(target),
    ),
    getAdminGlobalMatrices: () => request<AdminSectionVisibilityMatrices>(
      '/api/v1/admin/section-visibility',
    ),
    updateAdminGlobalMatrix: (
      scope: GlobalVisibilityScope,
      body: UpdateSectionVisibilityPayload,
    ) => request<SectionVisibilityMatrix>(
      `/api/v1/admin/section-visibility/${scope}`,
      { method: 'PATCH', body },
    ),
    getAdminStorefrontMatrices: (storefrontId: UUID) => request<AdminSectionVisibilityMatrices>(
      `/api/v1/admin/storefronts/${storefrontId}/section-visibility`,
    ),
    updateAdminStorefrontMatrix: (
      storefrontId: UUID,
      scope: StorefrontVisibilityScope,
      body: UpdateSectionVisibilityPayload,
    ) => request<SectionVisibilityMatrix>(
      `/api/v1/admin/storefronts/${storefrontId}/section-visibility/${scope}`,
      { method: 'PATCH', body },
    ),
  }
}
