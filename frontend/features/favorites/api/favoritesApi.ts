import type { CatalogId, UUID } from '~/types/ids'
import type { StorefrontApiPath } from '~/features/storefront'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface FavoriteItem {
  id?: UUID
  vehicle_id: UUID
  brand_id?: CatalogId
  mark_id?: CatalogId
  model_id?: CatalogId
  modification_id?: CatalogId
  complectation_id?: CatalogId
  brand_name?: string
  model_name?: string
  mark_name?: string
  group_name?: string
  base_price?: number
  discount_price?: number
  price?: number
  year?: number
  vehicle_year?: number
  color?: string
  vin?: string
  images?: string[]
  main_image?: string | null
  [key: string]: unknown
}

export interface FavoritesResponse {
  favorites: FavoriteItem[]
}

export interface ActionResult {
  success: boolean
  error?: string
}

const prettifyFavoriteToken = (value: unknown): string => {
  if (typeof value !== 'string' || value.length === 0) {
    return ''
  }

  return value.replaceAll('_', ' ').trim()
}

export const hasFavoriteVehicleId = (
  favorite: Record<string, unknown>,
): favorite is Record<string, unknown> & { vehicle_id: UUID } =>
  typeof favorite.vehicle_id === 'string' && favorite.vehicle_id.length > 0

export const normalizeFavoriteItem = (
  favorite: Partial<FavoriteItem> & Record<string, unknown> & { vehicle_id: UUID }
): FavoriteItem => {
  const rawMarkName = favorite.mark_name ?? favorite.brand_name ?? favorite.mark_id ?? ''
  const rawModelName = favorite.model_name ?? favorite.model_id ?? ''
  const markName = prettifyFavoriteToken(rawMarkName)
  const markPrefix = typeof favorite.mark_id === 'string' && favorite.mark_id.length > 0
    ? `${favorite.mark_id}_`
    : ''
  const normalizedModelSource = typeof rawModelName === 'string' && markPrefix && rawModelName.startsWith(markPrefix)
    ? rawModelName.slice(markPrefix.length)
    : rawModelName
  const modelName = prettifyFavoriteToken(normalizedModelSource)
  const images = Array.isArray(favorite.images)
    ? favorite.images.filter((image): image is string => typeof image === 'string' && image.length > 0)
    : []
  const mainImage = typeof favorite.main_image === 'string' && favorite.main_image.length > 0
    ? favorite.main_image
    : images[0] ?? null
  const basePrice = Number(favorite.base_price ?? favorite.price ?? 0) || undefined
  const discountPrice = Number(favorite.discount_price ?? basePrice ?? 0) || undefined
  const year = Number(favorite.vehicle_year ?? favorite.year ?? 0) || undefined

  return {
    ...favorite,
    id: typeof favorite.id === 'string' ? favorite.id : undefined,
    vehicle_id: favorite.vehicle_id,
    mark_name: markName,
    brand_name: markName,
    model_name: modelName,
    images,
    main_image: mainImage,
    base_price: basePrice,
    discount_price: discountPrice,
    price: Number(favorite.price ?? discountPrice ?? basePrice ?? 0) || undefined,
    year,
    vehicle_year: year,
    group_name: typeof favorite.group_name === 'string' ? favorite.group_name : undefined,
    color: typeof favorite.color === 'string' ? favorite.color : undefined,
    vin: typeof favorite.vin === 'string' ? favorite.vin : undefined,
    mark_id: typeof favorite.mark_id === 'string' ? favorite.mark_id : undefined,
    model_id: typeof favorite.model_id === 'string' ? favorite.model_id : undefined,
    complectation_id: typeof favorite.complectation_id === 'string' ? favorite.complectation_id : undefined,
  }
}

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createFavoritesApi = (
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
    /** Fetch all favorites for the authenticated user. */
    getFavorites: () =>
      request<FavoritesResponse>(storefrontApiPath('/client/favorites')),

    /** Add a vehicle to favorites by ID. */
    addFavorite: (vehicleId: UUID) =>
      request<void>(storefrontApiPath(`/client/favorites/${vehicleId}`), { method: 'POST' }),

    /** Remove a vehicle from favorites by ID. */
    removeFavorite: (vehicleId: UUID) =>
      request<void>(storefrontApiPath(`/client/favorites/${vehicleId}`), { method: 'DELETE' }),

    /** Clear all favorites for the authenticated user. */
    clearFavorites: () =>
      request<void>(storefrontApiPath('/client/favorites?confirm=true'), {
        method: 'DELETE',
      }),

    /** Bulk remove multiple vehicles from favorites. */
    bulkRemoveFavorites: (vehicleIds: UUID[]) => {
      const query = vehicleIds
        .map((vehicleId) => `ids=${encodeURIComponent(vehicleId)}`)
        .join('&')
      return request<void>(storefrontApiPath(`/client/favorites?${query}`), {
        method: 'DELETE',
      })
    },
  }
}
