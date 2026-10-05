import type { useRuntimeConfig } from '#app'
import type { SiteApplicationSourceType } from '~/features/applications/sourceType'
import type { UUID } from '~/types/ids'
import type { StorefrontApiPath } from '~/features/storefront'
import type {
  CommerceCompanyPayload,
  CommerceCreateOrderResult,
  CommerceCreatePaymentResult,
  CommerceItem,
  CommerceItemRef,
  CommerceItemType,
  CommerceLeasingCalculationPayload,
  CommerceLeasingApplicationResult,
  CommerceMoney,
  CommerceOrder,
  CommercePayment,
  CommercePaymentMethod,
  CommercePurchaseType,
  CommerceScheduleItem,
} from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

interface CommerceItemResponse {
  item: CommerceItem
}

interface CommerceOrdersResponse {
  items: CommerceOrder[]
}

interface CommerceOrderResponse {
  order: CommerceOrder
}

interface CommercePaymentsResponse {
  items: CommercePayment[]
}

interface CommercePaymentStatusResponse {
  payment: CommercePayment
}

interface CommerceScheduleResponse {
  items: CommerceScheduleItem[]
}

export interface CommerceCreateOrderBody {
  item: CommerceItemRef
  quantity?: number
  purchase_type: CommercePurchaseType
  payment_method: CommercePaymentMethod
  down_payment_percent?: CommerceMoney
}

export interface CommerceCreatePaymentBody {
  scope: 'remaining' | 'scheduled'
  schedule_id?: UUID
  payment_method: CommercePaymentMethod
}

export interface CommerceCreateLeasingApplicationBody {
  source_type: SiteApplicationSourceType
  items: Array<{
    item: CommerceItemRef
    quantity: number
    allow_overstock?: boolean
    custom_price?: CommerceMoney
    comment?: string
    equipments?: Array<Record<string, unknown>>
    services?: Array<Record<string, unknown>>
    leasing_purpose?: string
    leasing_purposes?: string[] | null
    leasing_purpose_comment?: string
    regions?: string[]
    cart_item_ids?: UUID[]
  }>
  company_id?: UUID
  company?: CommerceCompanyPayload
  name?: string
  email?: string
  down_payment_percent?: CommerceMoney
  lease_term_months?: number
  calculation?: CommerceLeasingCalculationPayload
}

const rootApiPath: StorefrontApiPath = (path) => `/api/v1${path}`

export const createCommerceApi = (
  config: RuntimeConfig,
  storefrontApiPath: StorefrontApiPath = rootApiPath,
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

  const orderPath = (type: CommerceItemType, orderId: UUID): string =>
    `/api/v1/commerce/orders/${encodeURIComponent(type)}/${encodeURIComponent(orderId)}`

  return {
    getItem: (item: CommerceItemRef) => request<CommerceItemResponse>(
      storefrontApiPath(
        `/commerce/items/${encodeURIComponent(item.type)}/${encodeURIComponent(item.id)}`,
      ),
    ),

    createOrder: (body: CommerceCreateOrderBody, idempotencyKey: string) =>
      request<CommerceCreateOrderResult>('/api/v1/commerce/orders', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body,
      }),

    getOrders: (type: CommerceItemType) => request<CommerceOrdersResponse>(
      '/api/v1/commerce/orders',
      { query: { type } },
    ),

    getOrder: (type: CommerceItemType, orderId: UUID) =>
      request<CommerceOrderResponse>(orderPath(type, orderId)),

    getPayments: (type: CommerceItemType, orderId: UUID) =>
      request<CommercePaymentsResponse>(`${orderPath(type, orderId)}/payments`),

    createPayment: (
      type: CommerceItemType,
      orderId: UUID,
      body: CommerceCreatePaymentBody,
      idempotencyKey: string,
    ) => request<CommerceCreatePaymentResult>(`${orderPath(type, orderId)}/payments`, {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body,
    }),

    getPaymentStatus: (type: CommerceItemType, orderId: UUID, paymentId: UUID) =>
      request<CommercePaymentStatusResponse>(
        `${orderPath(type, orderId)}/payments/${encodeURIComponent(paymentId)}/status`,
      ),

    getSchedule: (type: CommerceItemType, orderId: UUID) =>
      request<CommerceScheduleResponse>(`${orderPath(type, orderId)}/schedule`),

    cancelOrder: (type: CommerceItemType, orderId: UUID, reason?: string) =>
      request<CommerceOrderResponse>(`${orderPath(type, orderId)}/cancellation`, {
        method: 'PUT',
        body: { reason: reason?.trim() || null },
      }),

    createLeasingApplication: (body: CommerceCreateLeasingApplicationBody, idempotencyKey: string = crypto.randomUUID()) =>
      request<CommerceLeasingApplicationResult>(storefrontApiPath('/commerce/leasing-applications'), {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body,
      }),
  }
}
