import { defineStore } from 'pinia'
import { usePurchase } from '~/features/purchases/composables/usePurchase'
import { useVehicleAvailability } from '~/features/cars/composables/useVehicleAvailability'
import type { UUID } from '~/types/ids'

export interface PurchaseOrder {
  id: UUID
  user_id: UUID
  vehicle_id: UUID
  purchase_type: 'reservation' | 'full_purchase'
  status: 'reserved' | 'purchased' | 'leasing_pending' | 'leasing_active' | 'cancelled' | 'cancellation_requested'
  total_price: number
  paid_amount: number
  remaining_amount: number
  leasing_application_id: UUID | null
  payment_id?: UUID | null
  cancellation_reason: string | null
  cancellation_requested_at: string | null
  cancelled_at: string | null
  created_at: string
  updated_at: string
  // Vehicle info
  vin: string | null
  color: string | null
  vehicle_year: number | null
  images: string[] | null
  mark_name: string
  mark_cyrillic: string | null
  model_name: string
  model_cyrillic: string | null
  generation_name: string | null
  configuration_name: string | null
  modification_name: string | null
  base_price: number | null
  // Warehouse info
  warehouse_name: string | null
  warehouse_address: string | null
  warehouse_brand: string | null
}

export interface Payment {
  id: UUID
  purchase_order_id: UUID
  payment_type: 'reservation' | 'remaining_balance' | 'full_purchase' | 'leasing_monthly'
  amount: number
  status: 'processing' | 'completed' | 'error' | 'pending_payment' | 'failed'
  payment_method: 'card' | 'sbp' | 'bank_transfer' | null
  receipt_url: string | null
  fiscal_status: 'pending' | 'sent' | 'completed' | 'failed' | null
  fiscal_receipt_id: string | null
  error_message: string | null
  paid_at: string | null
  created_at: string
}

export interface ScheduleItem {
  id: UUID
  purchase_order_id: UUID
  payment_number: number
  due_date: string
  amount: number
  principal: number | null
  interest: number | null
  is_paid: boolean
  payment_id: UUID | null
  payment_status: string | null
  payment_paid_at: string | null
  receipt_url: string | null
}

export const usePurchasesStore = defineStore('purchases', () => {
  const orders = ref<PurchaseOrder[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  // Map of vehicle_id -> order status for user's active orders
  const myVehicleStatusMap = ref<Map<UUID, string>>(new Map())

  const { fetchOrders: apiFetchOrders, createOrders: apiCreateOrders, createPayment: apiCreatePayment, requestCancellation: apiRequestCancellation, fetchPayments: apiFetchPayments, fetchSchedule: apiFetchSchedule, fetchReceipt: apiFetchReceipt, checkPaymentStatus: apiCheckPaymentStatus } = usePurchase()
  const { getMyReservedVehicles } = useVehicleAvailability()

  async function fetchOrders(statusFilter?: string) {
    loading.value = true
    error.value = null
    try {
      const response = await apiFetchOrders(statusFilter)
      orders.value = response.orders
    } catch (err: any) {
      error.value = err?.data?.error || err?.message || 'Ошибка загрузки заказов'
    } finally {
      loading.value = false
    }
  }

  async function createOrders(
    items: { vehicle_id: UUID; quantity?: number }[],
    purchaseType: 'reservation' | 'full_purchase',
    paymentMethod?: 'card' | 'sbp' | 'bank_transfer',
    downPaymentPercent?: number
  ) {
    loading.value = true
    error.value = null
    try {
      const response = await apiCreateOrders(items, purchaseType, paymentMethod, downPaymentPercent)
      // For gateway payments, return payment data for the frontend
      if (response.sbpData) {
        return { orders: response.orders, sbpData: response.sbpData }
      }
      if (response.widgetData) {
        return { orders: response.orders, widgetData: response.widgetData }
      }
      await fetchOrders()
      return { orders: response.orders }
    } catch (err: any) {
      error.value = err?.data?.error || err?.message || 'Ошибка создания заказа'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function payRemainingBalance(orderId: UUID, paymentMethod?: 'card' | 'sbp' | 'bank_transfer') {
    loading.value = true
    error.value = null
    try {
      const result = await apiCreatePayment(orderId, { scope: 'remaining', payment_method: paymentMethod })
      if (result.sbpData || result.widgetData) {
        return result
      }
      await fetchOrders()
      return result
    } catch (err: any) {
      error.value = err?.data?.error || err?.message || 'Ошибка оплаты'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function cancelOrder(orderId: UUID, reason?: string) {
    loading.value = true
    error.value = null
    try {
      const result = await apiRequestCancellation(orderId, reason)
      await fetchOrders()
      return result
    } catch (err: any) {
      error.value = err?.data?.error || err?.message || 'Ошибка запроса отмены'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getPayments(orderId: UUID): Promise<Payment[]> {
    const response = await apiFetchPayments(orderId)
    return response.payments
  }

  async function getSchedule(orderId: UUID): Promise<ScheduleItem[]> {
    const response = await apiFetchSchedule(orderId)
    return response.schedule
  }

  async function paySchedule(orderId: UUID, scheduleId: UUID, paymentMethod?: 'card' | 'sbp' | 'bank_transfer') {
    loading.value = true
    error.value = null
    try {
      const result = await apiCreatePayment(orderId, {
        scope: 'scheduled',
        schedule_id: scheduleId,
        payment_method: paymentMethod,
      })
      return result
    } catch (err: any) {
      error.value = err?.data?.error || err?.message || 'Ошибка оплаты платежа'
      throw err
    } finally {
      loading.value = false
    }
  }

  async function pollPaymentStatus(paymentId: UUID, intervalMs = 3000, maxAttempts = 600): Promise<{ status: string; receipt_url?: string | null }> {
    for (let i = 0; i < maxAttempts; i++) {
      const response = await apiCheckPaymentStatus(paymentId)
      const { status, receipt_url } = response.payment
      if (status === 'completed' || status === 'failed' || status === 'error') {
        return { status, receipt_url }
      }
      await new Promise(resolve => setTimeout(resolve, intervalMs))
    }
    return { status: 'timeout' }
  }

  async function getReceipt(paymentId: UUID) {
    return apiFetchReceipt(paymentId)
  }

  async function loadMyVehicleIds() {
    try {
      const vehicles = await getMyReservedVehicles()
      const map = new Map<UUID, string>()
      for (const v of vehicles) {
        map.set(v.vehicle_id, v.status)
      }
      myVehicleStatusMap.value = map
    } catch {
      // non-critical
    }
  }

  function isMyReservedVehicle(vehicleId: UUID): string {
    return myVehicleStatusMap.value.get(vehicleId) || ''
  }

  return {
    orders,
    loading,
    error,
    myVehicleStatusMap,
    fetchOrders,
    createOrders,
    payRemainingBalance,
    cancelOrder,
    getPayments,
    getSchedule,
    paySchedule,
    getReceipt,
    loadMyVehicleIds,
    isMyReservedVehicle,
    pollPaymentStatus,
  }
})
