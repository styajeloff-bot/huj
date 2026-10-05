import type { useRuntimeConfig } from '#app'
import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// --- Interfaces ---

export type PurchaseType = 'reservation' | 'full_purchase'

export interface PurchaseOrder {
  id: UUID
  user_id: UUID
  vehicle_id: UUID
  leasing_application_id: UUID | null
  payment_id?: UUID | null
  status: string
  purchase_type: PurchaseType
  payment_method: string
  [key: string]: unknown
}

export interface OrdersResponse {
  orders: PurchaseOrder[]
}

export interface OrderDetailResponse {
  order: PurchaseOrder
}

export interface CreateOrderPayload {
  items: Array<{ vehicle_id: UUID; quantity?: number }>
  purchase_type: PurchaseType
  payment_method: string
  down_payment_percent?: number
}

export interface CreateOrderResponse {
  orders: PurchaseOrder[]
  widgetData?: unknown
  sbpData?: unknown
}

export interface Payment {
  id: UUID
  purchase_order_id: UUID
  user_id: UUID
  status: string
  fiscal_status: string | null
  receipt_url: string | null
  error_message: string | null
  paid_at: string | null
  [key: string]: unknown
}

export interface PaymentsResponse {
  payments: Payment[]
}

export interface ScheduleItem {
  id: UUID
  purchase_order_id: UUID
  payment_id: UUID | null
  [key: string]: unknown
}

export interface ScheduleResponse {
  schedule: ScheduleItem[]
}

export interface CreatePaymentPayload {
  scope: 'remaining' | 'scheduled'
  schedule_id?: UUID
  payment_method?: 'card' | 'sbp' | 'bank_transfer'
}

export interface CreatePaymentResponse {
  payment: Payment
  order?: PurchaseOrder
  scheduleItem?: ScheduleItem
  widgetData?: unknown
  sbpData?: unknown
}

export interface PaymentStatusResponse {
  payment: {
    id: UUID
    status: string
    fiscal_status: string | null
    receipt_url: string | null
    error_message: string | null
    paid_at: string | null
  }
}

export interface ReceiptResponse {
  receipt: unknown
}

export interface CancellationResponse {
  order: PurchaseOrder
}

export interface ReservedVehicle {
  vehicle_id: UUID
  status: string
  purchase_type: PurchaseType
}

export interface ReservedVehiclesResponse {
  vehicles: ReservedVehicle[]
}

// --- Factory ---

export const createPurchasesApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, { baseURL: config.public.apiBase, credentials: 'include', ...options })

  return {
    /** GET /api/v1/purchases?status= */
    getOrders(status?: string) {
      const query = status ? `?status=${status}` : ''
      return request<OrdersResponse>(`/api/v1/purchases${query}`)
    },

    /** GET /api/v1/purchases/:orderId */
    getOrderDetails(orderId: UUID) {
      return request<OrderDetailResponse>(`/api/v1/purchases/${orderId}`)
    },

    /** POST /api/v1/purchases */
    createOrder(payload: CreateOrderPayload) {
      const body: Record<string, unknown> = {
        items: payload.items,
        purchase_type: payload.purchase_type,
        payment_method: payload.payment_method,
      }
      if (payload.down_payment_percent) {
        body.down_payment_percent = payload.down_payment_percent
      }
      return request<CreateOrderResponse>('/api/v1/purchases', {
        method: 'POST',
        body,
      })
    },

    /** POST /api/v1/purchases/:orderId/payments */
    createPayment(orderId: UUID, payload: CreatePaymentPayload) {
      return request<CreatePaymentResponse>(`/api/v1/purchases/${orderId}/payments`, {
        method: 'POST',
        body: payload,
      })
    },

    /** POST /api/v1/purchases/:orderId/request-cancellation */
    requestCancellation(orderId: UUID, reason?: string) {
      return request<CancellationResponse>(`/api/v1/purchases/${orderId}/request-cancellation`, {
        method: 'POST',
        body: { reason },
      })
    },

    /** GET /api/v1/purchases/:orderId/payments */
    getPayments(orderId: UUID) {
      return request<PaymentsResponse>(`/api/v1/purchases/${orderId}/payments`)
    },

    /** GET /api/v1/purchases/:orderId/schedule */
    getSchedule(orderId: UUID) {
      return request<ScheduleResponse>(`/api/v1/purchases/${orderId}/schedule`)
    },

    /** GET /api/v1/purchases/payments/:paymentId/status */
    checkPaymentStatus(paymentId: UUID) {
      return request<PaymentStatusResponse>(`/api/v1/purchases/payments/${paymentId}/status`)
    },

    /** GET /api/v1/purchases/payments/:paymentId/receipt */
    getReceipt(paymentId: UUID) {
      return request<ReceiptResponse>(`/api/v1/purchases/payments/${paymentId}/receipt`)
    },

    /** GET /api/v1/purchases/my-vehicle-ids */
    getMyReservedVehicles() {
      return request<ReservedVehiclesResponse>('/api/v1/purchases/my-vehicle-ids')
    },
  }
}
