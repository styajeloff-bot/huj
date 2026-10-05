import type { UUID } from '~/types/ids'

export function usePurchase() {
  const config = useRuntimeConfig()
  const baseURL = config.public.apiBase

  const fetchOrders = (status?: string) => {
    const query = status ? `?status=${status}` : ''
    return $fetch<{ orders: any[] }>(`/api/v1/purchases${query}`, {
      baseURL,
      credentials: 'include'
    })
  }

  const fetchOrderDetails = (orderId: UUID) => {
    return $fetch<{ order: any }>(`/api/v1/purchases/${orderId}`, {
      baseURL,
      credentials: 'include'
    })
  }

  const createOrders = (
    items: { vehicle_id: UUID; quantity?: number }[],
    purchaseType: 'reservation' | 'full_purchase',
    paymentMethod?: 'card' | 'sbp' | 'bank_transfer',
    downPaymentPercent?: number
  ) => {
    const body: Record<string, any> = { items, purchase_type: purchaseType, payment_method: paymentMethod }
    if (downPaymentPercent) body.down_payment_percent = downPaymentPercent
    return $fetch<{ orders: any[]; widgetData?: any; sbpData?: any }>('/api/v1/purchases', {
      method: 'POST',
      baseURL,
      credentials: 'include',
      body,
    })
  }

  const createPayment = (
    orderId: UUID,
    payload: {
      scope: 'remaining' | 'scheduled'
      schedule_id?: UUID
      payment_method?: 'card' | 'sbp' | 'bank_transfer'
    }
  ) => {
    return $fetch<{ payment: any; order?: any; scheduleItem?: any; widgetData?: any; sbpData?: any }>(`/api/v1/purchases/${orderId}/payments`, {
      method: 'POST',
      baseURL,
      credentials: 'include',
      body: payload
    })
  }

  const requestCancellation = (orderId: UUID, reason?: string) => {
    return $fetch<{ order: any }>(`/api/v1/purchases/${orderId}/request-cancellation`, {
      method: 'POST',
      baseURL,
      credentials: 'include',
      body: { reason }
    })
  }

  const fetchPayments = (orderId: UUID) => {
    return $fetch<{ payments: any[] }>(`/api/v1/purchases/${orderId}/payments`, {
      baseURL,
      credentials: 'include'
    })
  }

  const fetchSchedule = (orderId: UUID) => {
    return $fetch<{ schedule: any[] }>(`/api/v1/purchases/${orderId}/schedule`, {
      baseURL,
      credentials: 'include'
    })
  }

  const checkPaymentStatus = (paymentId: UUID) => {
    return $fetch<{ payment: { id: UUID; status: string; fiscal_status: string | null; receipt_url: string | null; error_message: string | null; paid_at: string | null } }>(`/api/v1/purchases/payments/${paymentId}/status`, {
      baseURL,
      credentials: 'include'
    })
  }

  const fetchReceipt = (paymentId: UUID) => {
    return $fetch<{ receipt: any }>(`/api/v1/purchases/payments/${paymentId}/receipt`, {
      baseURL,
      credentials: 'include'
    })
  }

  return {
    fetchOrders,
    fetchOrderDetails,
    createOrders,
    createPayment,
    requestCancellation,
    fetchPayments,
    fetchSchedule,
    fetchReceipt,
    checkPaymentStatus,
  }
}
