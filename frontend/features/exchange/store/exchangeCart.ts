import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createExchangeApi } from '../api/exchangeApi'
import type { EntityId, ExchangeCartItem, VehicleId, WarehouseInfo } from '../types'
import { useAuthStore } from '~/features/auth/store/auth'
import type { UUID } from '~/types/ids'

export const useExchangeCartStore = defineStore('exchangeCart', () => {
  const items = ref<ExchangeCartItem[]>([])
  const loading = ref(false)
  const submitting = ref(false)
  const initialized = ref(false)
  const count = ref(0)
  const config = useRuntimeConfig()
  const api = createExchangeApi(config)
  const authStore = useAuthStore()

  // Computed
  const totalItems = computed(() => items.value.length)
  const isEmpty = computed(() => totalItems.value === 0)
  const totalAmount = computed(() =>
    items.value.reduce<number>((sum, item) => {
      const price = Number(item.support_price_display ?? item.discount_price ?? item.base_price) || 0
      return sum + price * (item.quantity || 1)
    }, 0)
  )
  const isValid = computed(() =>
    items.value.length > 0 &&
    items.value.every(item => item.selected_warehouse_ids.length > 0)
  )

  // Actions
  async function fetchCart() {
    if (!authStore.isLeasingCompany) return
    loading.value = true
    try {
      const data = await api.getCart()
      items.value = data.cart_items
      count.value = data.summary.total_items
      initialized.value = true
    } catch (error) {
      console.error('Failed to fetch exchange cart:', error)
    } finally {
      loading.value = false
    }
  }

  async function addItem(vehicleId: VehicleId, quantity: number = 1, warehouseId?: EntityId | null) {
    try {
      const body: { vehicle_id: VehicleId; quantity: number; warehouse_id?: EntityId } = {
        vehicle_id: vehicleId,
        quantity,
      }
      if (warehouseId) body.warehouse_id = warehouseId
      const result = await api.createCartItem(body)
      await fetchCart() // Refresh to get enriched data
      return result
    } catch (error) {
      console.error('Failed to add to exchange cart:', error)
      throw error
    }
  }

  async function removeItem(itemId: UUID) {
    try {
      await api.removeCartItem(itemId)
      items.value = items.value.filter(item => item.id !== itemId)
      count.value = items.value.length
    } catch (error) {
      console.error('Failed to remove from exchange cart:', error)
      throw error
    }
  }

  async function updateItem(itemId: UUID, data: {
    quantity?: number
    expiration_at?: string | null
    discount_type?: string | null
    discount_value?: number | null
    selected_support_ids?: UUID[]
  }) {
    try {
      await api.updateCartItem(itemId, data)
      // Optimistic update
      const item = items.value.find(i => i.id === itemId)
      if (item) {
        Object.assign(item, data)
      }
    } catch (error) {
      console.error('Failed to update exchange cart item:', error)
      throw error
    }
  }

  async function setSupportPrograms(itemId: UUID, supportIds: UUID[]) {
    await updateItem(itemId, { selected_support_ids: supportIds })
    // The server owns support type classification and aggregated display prices.
    await fetchCart()
  }

  async function setWarehouses(itemId: UUID, warehouseIds: EntityId[]) {
    try {
      await api.updateCartItem(itemId, { warehouses: warehouseIds })
      const item = items.value.find(i => i.id === itemId)
      if (item) {
        item.selected_warehouse_ids = warehouseIds
      }
    } catch (error) {
      console.error('Failed to set warehouses:', error)
      throw error
    }
  }

  async function setOptions(itemId: UUID, optionIds: EntityId[]) {
    try {
      await api.updateCartItem(itemId, { options: optionIds })
      const item = items.value.find(i => i.id === itemId)
      if (item) {
        item.selected_option_ids = optionIds
      }
    } catch (error) {
      console.error('Failed to set options:', error)
      throw error
    }
  }

  async function setDealerComment(itemId: UUID, dealerId: UUID, comment: string) {
    try {
      await api.updateCartItem(itemId, {
        dealer_comment: { dealer_id: dealerId, comment },
      })
      const item = items.value.find(i => i.id === itemId)
      if (item) {
        const existing = item.dealer_comments.find(dc => dc.dealer_id === dealerId)
        if (existing) {
          existing.comment = comment
        } else {
          item.dealer_comments.push({ dealer_id: dealerId, dealer_name: '', comment })
        }
      }
    } catch (error) {
      console.error('Failed to set dealer comment:', error)
      throw error
    }
  }

  async function uploadFile(itemId: UUID, file: File) {
    try {
      await api.uploadCartItemFile(itemId, file)
      await fetchCart()
    } catch (error) {
      console.error('Failed to upload file:', error)
      throw error
    }
  }

  async function clearCart() {
    try {
      await api.clearCart()
      items.value = []
      count.value = 0
    } catch (error) {
      console.error('Failed to clear exchange cart:', error)
      throw error
    }
  }

  async function submitCart() {
    submitting.value = true
    try {
      const result = await api.submitCart()
      items.value = []
      count.value = 0
      return result
    } catch (error) {
      console.error('Failed to submit exchange cart:', error)
      throw error
    } finally {
      submitting.value = false
    }
  }

  async function getAvailableWarehouses(vehicleId: VehicleId): Promise<WarehouseInfo[]> {
    try {
      const data = await api.getAvailableWarehouses(vehicleId)
      return data.warehouses
    } catch (error) {
      console.error('Failed to get warehouses:', error)
      return []
    }
  }

  async function getCount(): Promise<number> {
    try {
      const data = await api.getCartCount()
      count.value = data.count
      return data.count
    } catch (error) {
      return 0
    }
  }

  function isInCart(vehicleId: VehicleId): boolean {
    return items.value.some(item => item.vehicle_id === vehicleId)
  }

  async function removeByVehicleId(vehicleId: VehicleId) {
    const item = items.value.find(i => i.vehicle_id === vehicleId)
    if (item) {
      await removeItem(item.id)
    }
  }

  function reset() {
    items.value = []
    count.value = 0
    initialized.value = false
  }

  return {
    items,
    loading,
    submitting,
    initialized,
    count,
    totalItems,
    isEmpty,
    totalAmount,
    isValid,
    fetchCart,
    addItem,
    removeItem,
    updateItem,
    setWarehouses,
    setOptions,
    setDealerComment,
    setSupportPrograms,
    uploadFile,
    clearCart,
    submitCart,
    getAvailableWarehouses,
    getCount,
    isInCart,
    removeByVehicleId,
    reset,
  }
})
