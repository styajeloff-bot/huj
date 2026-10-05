import type { UUID } from '~/types/ids'
import type { SiteApplicationSourceType } from '~/features/applications/sourceType'
import type {
  SpecialEquipmentCartItem,
  SpecialEquipmentCreateOrderResponse,
  SpecialEquipmentLeasingApplicationResponse,
  SpecialEquipmentPaymentMethod,
  SpecialEquipmentPrice,
} from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
type StorefrontApiPath = (path: string) => string

export interface SpecialEquipmentCartItemPatch {
  quantity?: number
  allow_overstock?: boolean
  parent_item_id?: UUID | null
  is_selected?: boolean
  custom_price?: SpecialEquipmentPrice
  comment?: string | null
  equipments?: Array<Record<string, unknown>>
  services?: Array<Record<string, unknown>>
}

export interface CreateSpecialEquipmentCartItemBody {
  product_id: UUID
  quantity: number
  allow_overstock?: boolean
  parent_item_id?: UUID | null
  is_selected?: boolean
  comment?: string | null
  equipments?: Array<Record<string, unknown>>
  services?: Array<Record<string, unknown>>
}

export interface GuestCartTransferBody {
  version: 2
  items: Array<{
    local_id: UUID
    product_id: UUID
    quantity: number
    allow_overstock?: boolean
    parent_local_id: UUID | null
    is_selected: boolean
    comment: string | null
    equipments: Array<Record<string, unknown>>
    services: Array<Record<string, unknown>>
  }>
}

export interface GuestCartTransferResponse {
  transfer_id: UUID
  replayed: boolean
  item_ids: Record<UUID, UUID>
  items: SpecialEquipmentCartItem[]
}

export const createSpecialEquipmentCartApi = (
  config: RuntimeConfig,
  apiPath?: StorefrontApiPath,
) => {
  const forwardedAuthHeaders = import.meta.server
    ? useRequestHeaders(['cookie', 'authorization'])
    : {}
  const request = <T>(url: string, options: Record<string, unknown> = {}) => {
    const endpointHeaders = (options.headers ?? {}) as Record<string, string>
    return $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
      headers: {
        ...forwardedAuthHeaders,
        ...endpointHeaders,
      },
    })
  }
  const endpoint = (path: string) => apiPath
    ? apiPath(`/special-equipment${path}`)
    : `/api/v1/special-equipment${path}`

  return {
    createCartItem: (body: CreateSpecialEquipmentCartItemBody) =>
      request<{ created: boolean; cart_item: SpecialEquipmentCartItem }>(
        endpoint('/cart-items'),
        { method: 'POST', body, _skipAuthRefresh: true },
      ),

    updateCartItem: (cartItemId: UUID, body: SpecialEquipmentCartItemPatch) =>
      request<{ cart_item: Omit<SpecialEquipmentCartItem, 'product'> }>(
        endpoint(`/cart-items/${encodeURIComponent(cartItemId)}`),
        { method: 'PATCH', body, _skipAuthRefresh: true },
      ),

    removeCartItem: (cartItemId: UUID) => request<void>(
      endpoint(`/cart-items/${encodeURIComponent(cartItemId)}`),
      { method: 'DELETE', _skipAuthRefresh: true },
    ),

    clearCartItems: () => request<void>(endpoint('/cart-items'), {
      method: 'DELETE',
      query: { confirm: true },
      _skipAuthRefresh: true,
    }),

    transferGuestCart: (transferId: UUID, body: GuestCartTransferBody) =>
      request<GuestCartTransferResponse>(
        endpoint(`/cart-transfers/${encodeURIComponent(transferId)}`),
        { method: 'PUT', body },
      ),

    createOrder: (
      body: {
        cart_item_ids: UUID[]
        purchase_type: 'reservation' | 'preorder' | 'full_purchase'
        payment_method: SpecialEquipmentPaymentMethod
        down_payment_percent?: string
      },
      idempotencyKey: string,
    ) => request<SpecialEquipmentCreateOrderResponse>(
      endpoint('/purchase-orders'),
      {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body,
      },
    ),

    createLeasingApplication: (body: {
      source_type: SiteApplicationSourceType
      company_id: UUID
      cart_item_ids: UUID[]
      comment?: string
      leasing_purpose?: string | null
      leasing_purposes?: string[] | null
      regions?: string[]
      down_payment_percent?: string
      lease_term_months?: number
    }, idempotencyKey: string = crypto.randomUUID()) => request<SpecialEquipmentLeasingApplicationResponse>(
      endpoint('/leasing-applications'),
      { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body },
    ),
  }
}
