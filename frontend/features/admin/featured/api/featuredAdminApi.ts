type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
import type { CatalogId, UUID } from '~/types/ids'

export interface FeaturedItem {
  id: UUID
  mark_name: string
  model_name: string
  model_id: CatalogId
  is_active: boolean
  is_eligible: boolean
  [key: string]: unknown
}

export interface FeaturedMark {
  id: CatalogId
  name: string
  [key: string]: unknown
}

export interface FeaturedModel {
  model_id: CatalogId
  mark_name: string
  model_name: string
  available_count: number
  min_price?: number | null
  is_featured: boolean
  [key: string]: unknown
}

export interface FetchModelsParams {
  mark_id?: string
  search?: string
  limit?: string
}

export const createFeaturedAdminApi = (config: RuntimeConfig, storefrontId: UUID) => {
  const root = `/api/v1/admin/storefronts/${storefrontId}/featured`
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  return {
    getFeatured: () =>
      request<{ featured: FeaturedItem[] }>(root),
    getMarks: () =>
      request<{ marks: FeaturedMark[] }>(`${root}/marks`),
    getModels: (params?: FetchModelsParams) => {
      const search = new URLSearchParams()
      if (params?.mark_id) search.set('mark_id', params.mark_id)
      if (params?.search) search.set('search', params.search)
      search.set('limit', params?.limit ?? '50')
      return request<{ models: FeaturedModel[] }>(`${root}/models?${search}`)
    },
    addFeatured: (modelId: CatalogId) =>
      request(root, { method: 'POST', body: { model_id: modelId } }),
    removeFeatured: (id: UUID) =>
      request(`${root}/${id}`, { method: 'DELETE' }),
    toggleActive: (id: UUID, active?: boolean) =>
      request<{ featured: FeaturedItem }>(`${root}/${id}`, {
        method: 'PATCH',
        body: active === undefined ? {} : { active }
      }),
    reorder: (orderedIds: UUID[]) =>
      request(`${root}/reorder`, { method: 'PUT', body: { ordered_ids: orderedIds } })
  }
}
