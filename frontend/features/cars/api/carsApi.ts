import type { CatalogId, UUID } from '~/types/ids'
import type { StorefrontApiPath } from '~/features/storefront'
export interface VehicleCategoryOption {
  id: string
  name: string
  parent_id?: string | null
  children?: VehicleCategoryOption[]
}

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Query parameter interfaces
// ---------------------------------------------------------------------------

export interface CarsFilterQuery {
  ids?: UUID[]
  page?: number
  limit?: number
  group_by?: string
  mark?: CatalogId
  model?: CatalogId
  generation?: CatalogId
  configuration?: CatalogId
  trim?: CatalogId
  transmission?: string
  horse_power?: string
  color?: string
  color_inter?: string
  warehouse?: string
  category?: string
  years?: string
  minPrice?: number
  maxPrice?: number
  sortBy?: string
  specialOffer?: boolean
  featured?: boolean
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface CarsResponse {
  items: unknown[]
  total: number
  page: number
  limit: number
  total_pages: number
}

export type FacetField =
  | 'marks'
  | 'models'
  | 'generations'
  | 'trims'
  | 'colors'
  | 'colors_inter'
  | 'transmissions'
  | 'horse_powers'
  | 'years'
  | 'ranges'
  | 'warehouses'
  | 'categories'

export interface FacetsQuery {
  fields: FacetField[]
  mark_id?: CatalogId
  model_id?: CatalogId
  generation_id?: CatalogId
  popular?: boolean
  country?: string
}

export interface CarMarkFacet {
  id: CatalogId
  ids?: CatalogId[]
  name: string
  country?: string | null
  count?: number
}

export interface FacetsResponse {
  marks?: CarMarkFacet[]
  models?: unknown[]
  generations?: { items: unknown[]; total: number; grouped: unknown[] }
  trims?: unknown[]
  colors?: unknown[]
  colors_inter?: unknown[]
  transmissions?: unknown[]
  horse_powers?: unknown[]
  years?: unknown[]
  ranges?: {
    min_price?: string | number | null
    max_price?: string | number | null
    min_year?: string | number | null
    max_year?: string | number | null
  }
  warehouses?: unknown[]
  categories?: VehicleCategoryOption[]
}

export interface ModelShowcaseQuery {
  mark_id?: CatalogId[]
}

export interface ModelShowcaseItem {
  id: CatalogId
  name: string
  mark_id: CatalogId
  mark_name: string
  year_from: number | null
  year_to: number | null
  vehicles_count: number
  image_filename: string | null
  min_price: number | null
  max_price: number | null
  category: string | null
  body_type: string | null
  volume?: string | null
  horse_power?: string | null
  time_to_100?: string | null
}

export interface ModelShowcaseResponse {
  items: ModelShowcaseItem[]
}

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createCarsApi = (
  config: RuntimeConfig,
  storefrontApiPath: StorefrontApiPath,
) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    /** List cars with full filtering, pagination and sorting. */
    getCars: (query: CarsFilterQuery, signal?: AbortSignal) =>
      request<CarsResponse>(storefrontApiPath('/cars'), { query, signal }),

    /** Combined filter-panel dropdowns — one request for all dropdowns. */
    getFacets: (query: FacetsQuery, signal?: AbortSignal) =>
      request<FacetsResponse>(storefrontApiPath('/cars/facets'), { query, signal }),

    /** Aggregated cards for the public model range without vehicle pagination or N+1. */
    getModelShowcase: (query: ModelShowcaseQuery = {}, signal?: AbortSignal) =>
      request<ModelShowcaseResponse>(storefrontApiPath('/cars/model-showcase'), {
        query,
        signal,
      }),

    /** Single car detail by ID. */
    getCarById: <T = Record<string, unknown>>(id: UUID) =>
      request<T>(storefrontApiPath(`/cars/${id}`)),

    /** Specifications for a catalog model. */
    getCarSpecifications: (modelId: CatalogId) =>
      request<{ specs?: string[] }>(storefrontApiPath(`/cars/specifications/${modelId}`)),

    checkAvailability: (vehicleIds: UUID[]) =>
      request<{ statuses: { vehicle_id: UUID; status: string }[] }>(
        storefrontApiPath('/cars/check-availability'),
        { method: 'GET', params: { vehicle_id: vehicleIds } },
      ),

    getAvailableCounts: (vehicleIds: UUID[]) =>
      request<{ counts: { vehicle_id: UUID; available_count: number }[] }>(
        storefrontApiPath('/cars/available-counts'),
        { method: 'POST', body: { vehicle_ids: vehicleIds } },
      ),
  }
}
