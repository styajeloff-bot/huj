type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
import type { CatalogId, UUID } from '~/types/ids'
import type { StorefrontApiPath } from '~/features/storefront'
export type {
  AdditionalEquipmentCatalogItem,
  AdditionalEquipmentCatalogResponse,
  AdditionalServiceCatalogItem,
  AdditionalServiceCatalogResponse,
} from '~/utils/additionalOptionsApi'
import { createAdditionalOptionsApi } from '~/utils/additionalOptionsApi'

// ---------------------------------------------------------------------------
// Request interfaces
// ---------------------------------------------------------------------------

export interface CreateCartItemRequest {
  vehicle_id: UUID
  quantity?: number
  allow_overstock?: boolean
}

export interface GuestCartTransferRequest {
  vehicle_id: UUID
  quantity: number
  allow_overstock?: boolean
  equipments: Array<{ equipment_code: string; price?: number }>
  services: Array<{ service_code: string; price?: number }>
}

export interface GuestCartTransferResponse {
  transfer_id: UUID
  applied: boolean
  cart_item: CartItem | null
}

/** Partial update body for `PATCH /cart/{vehicle_id}`. */
export interface PatchCartItemRequest {
  is_selected?: boolean
  quantity?: number
  allow_overstock?: boolean
  /** null clears the custom price (dealer / employee only). */
  custom_price?: number | null
  /** null or '' clears the comment. */
  comment?: string | null
  equipments?: Array<{ equipment_code: string; price?: number | null }>
  services?: Array<{ service_code: string; price?: number | null }>
}

export interface BulkUpdateSelectionRequest {
  items: Array<{ vehicle_id: UUID; is_selected: boolean }>
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface CartItem {
  cart_id: UUID
  id?: UUID
  vehicle_id: UUID
  modification_id?: CatalogId
  complectation_id?: CatalogId
  configuration_id?: CatalogId
  quantity?: number
  allow_overstock?: boolean
  is_selected?: boolean
  custom_price?: number | null
  comment?: string
  equipments?: Array<{ equipment_code: string; price?: number | null }>
  services?: Array<{ service_code: string; price?: number | null }>
  [key: string]: unknown
}

export interface CartResponse {
  cart_items: CartItem[]
  [key: string]: unknown
}

export interface CartListResponse {
  items: CartItem[]
}

export interface CartCountResponse {
  count: number
}

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createCartApi = (
  config: RuntimeConfig,
  storefrontApiPath: StorefrontApiPath,
) => {
  const additionalOptionsApi = createAdditionalOptionsApi(config)
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    /** Fetch the full cart for the current user. */
    getCart: () =>
      request<CartListResponse>(storefrontApiPath('/cart/')),

    /** Get cart item count via lightweight projection. */
    getCount: () =>
      request<CartCountResponse>(storefrontApiPath('/cart/'), { params: { fields: 'count' } }),

    getEquipments: () =>
      additionalOptionsApi.getEquipments(),

    getServices: () =>
      additionalOptionsApi.getServices(),

    /** Create a cart item (POST /cart). Upserts on duplicate (user_id, vehicle_id). */
    create: (body: CreateCartItemRequest) =>
      request<{ message: string; cart_item: CartItem; created: boolean }>(
         storefrontApiPath('/cart/'),
        { method: 'POST', body },
      ),

    /** Apply one guest-cart row exactly once for the authenticated user. */
    transferGuestCart: (transferId: UUID, body: GuestCartTransferRequest) =>
      request<GuestCartTransferResponse>(
         storefrontApiPath(`/cart/guest-transfers/${transferId}`),
        { method: 'PUT', body },
      ),

    /** Partial update for a single cart item. */
    update: (vehicleId: UUID, patch: PatchCartItemRequest) =>
      request<{ message: string; cart_item: CartItem }>(
         storefrontApiPath(`/cart/${vehicleId}`),
        { method: 'PATCH', body: patch },
      ),

    /** Bulk toggle is_selected across multiple positions. */
    bulkUpdateSelection: (body: BulkUpdateSelectionRequest) =>
      request<{ message: string; updated_items: CartItem[] }>(
         storefrontApiPath('/cart/'),
        { method: 'PATCH', body },
      ),

    /** Remove a vehicle from the cart. */
    removeFromCart: (vehicleId: UUID) =>
      request<{ message: string; removed: boolean }>(
         storefrontApiPath(`/cart/${vehicleId}`),
        { method: 'DELETE' },
      ),

    /** Clear the entire cart. */
    clearCart: () =>
      request<{ message: string; deleted_count: number }>(
         storefrontApiPath('/cart/'),
        { method: 'DELETE' },
      ),
  }
}
