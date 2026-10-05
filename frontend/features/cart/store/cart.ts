import { defineStore } from 'pinia'
import { ref, computed, readonly, watch } from 'vue'
import { useCartSupportSelection } from '~/features/cart/composables/useCartSupportSelection'
import { useAuthStore } from '~/features/auth/store/auth'
import { createCartApi } from '~/features/cart/api/cartApi'
import {
  createSingleFlight,
  entriesForGuestCartSave,
  normalizeGuestCartTransferOptions,
  parseGuestCartStorage,
  transferGuestCartEntries,
  type ValidGuestCartEntry,
} from '~/features/cart/guestCartPersistence'
import { isUuid, type CatalogId, type UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'
import type { SupportBadgeProgram } from '~/types/support'

/** Refund-style support: show as separate row. Direct discount: show two columns (without/with). */
export const SUPPORT_TYPE_REFUND = [
  'down_payment_compensation',
  'vehicle_discount_dealer_compensation',
  'leasing_interest_compensation'
] as const
export const SUPPORT_TYPE_DIRECT = 'vehicle_discount_dealer_invoice' as const

export type SupportTypeRefund = (typeof SUPPORT_TYPE_REFUND)[number]
export type SupportDisplayMode = 'refund' | 'direct' | null

export interface AdditionalOptionSelection {
  equipment_code?: string
  service_code?: string
  price?: number | null
}

export interface CartItem {
  cart_id: UUID
  vehicle_id: UUID
  modification_id?: CatalogId
  complectation_id?: CatalogId
  configuration_id?: CatalogId
  mark_id?: CatalogId
  model_id?: CatalogId
  mark_name: string
  model_name: string
  base_price: number
  discount_price?: number | null
  has_support?: boolean
  support_type?: string | null
  support_params?: Record<string, unknown> | null
  support_program_info?: {
    id?: UUID
    name?: string | null
    bill_of_lading?: unknown | null
  } | null
  applicable_support_programs?: SupportBadgeProgram[]
  custom_price?: number | null
  comment?: string
  equipments?: AdditionalOptionSelection[]
  services?: AdditionalOptionSelection[]
  vin?: string | null
  is_model_order?: boolean
  is_selected: boolean
  added_at: string
  year?: number
  color?: string
  quantity: number
  allow_overstock?: boolean
  images?: string[]
  configuration_name?: string
  group_name?: string
  id?: UUID
  effective_price?: number
  price_from?: number
  transfer_id?: UUID
}

interface SupportStatusItem {
  vehicle_id: UUID
  has_support: boolean
  support_type: string | null
  support_params: Record<string, unknown> | null
  /** Подходящие support_program_id для ТС (legacy fallback для выбора в UI). */
  eligible_program_ids?: UUID[]
  applicable_support_programs?: SupportBadgeProgram[]
}

export const useCartStore = defineStore('cart', () => {
  const items = ref<CartItem[]>([])
  const loading = ref(false)
  const fetchingCart = ref(false)
  const initialized = ref(false)
  const config = useRuntimeConfig()
  const { apiPath, storageKey } = useStorefront()
  const cartApi = createCartApi(config, apiPath)
  const authStore = useAuthStore()
  const supportSelection = useCartSupportSelection()

  // Local storage for guests
  const GUEST_CART_KEY = computed(() => storageKey('guest-cart-items'))

  const getOptionalString = (value: unknown) => typeof value === 'string' ? value : undefined
  const getOptionalNumber = (value: unknown) =>
    typeof value === 'number' && Number.isFinite(value) ? value : undefined
  const getNullableString = (value: unknown) =>
    value === null ? null : getOptionalString(value)
  const getNullableNumber = (value: unknown) =>
    value === null ? null : getOptionalNumber(value)
  const getCatalogId = (value: unknown): CatalogId | undefined =>
    typeof value === 'string' ? value : undefined
  const getGuestQuantity = (value: unknown) =>
    typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : 1

  const getAdditionalOptions = (value: unknown): AdditionalOptionSelection[] | undefined => {
    if (!Array.isArray(value)) return undefined

    return value.flatMap((option) => {
      if (typeof option !== 'object' || option === null || Array.isArray(option)) return []

      const raw = option as Record<string, unknown>
      const normalized: AdditionalOptionSelection = {}
      const equipmentCode = getOptionalString(raw.equipment_code)
      const serviceCode = getOptionalString(raw.service_code)
      const price = getNullableNumber(raw.price)

      if (equipmentCode !== undefined) normalized.equipment_code = equipmentCode
      if (serviceCode !== undefined) normalized.service_code = serviceCode
      if (price !== undefined) normalized.price = price

      return [normalized]
    })
  }

  const toCartItem = ({
    raw,
    vehicleId,
    transferId,
  }: ValidGuestCartEntry): CartItem => {
    const cartItem: CartItem = {
      // This UUID is a local row key and is never derived from an entity or catalog ID.
      cart_id: isUuid(raw.cart_id) ? raw.cart_id : crypto.randomUUID(),
      vehicle_id: vehicleId,
      mark_name: getOptionalString(raw.mark_name) || 'Автомобиль',
      model_name: getOptionalString(raw.model_name) || '',
      base_price: getOptionalNumber(raw.base_price) ?? 0,
      is_selected: typeof raw.is_selected === 'boolean' ? raw.is_selected : true,
      added_at: getOptionalString(raw.added_at) || new Date().toISOString(),
      quantity: getGuestQuantity(raw.quantity),
      allow_overstock: raw.allow_overstock === true,
    }

    const modificationId = getCatalogId(raw.modification_id)
    const complectationId = getCatalogId(raw.complectation_id)
    const configurationId = getCatalogId(raw.configuration_id)
    const markId = getCatalogId(raw.mark_id)
    const modelId = getCatalogId(raw.model_id)
    const discountPrice = getNullableNumber(raw.discount_price)
    const customPrice = getNullableNumber(raw.custom_price)
    const supportType = getNullableString(raw.support_type)
    const comment = getOptionalString(raw.comment)
    const equipments = getAdditionalOptions(raw.equipments)
    const services = getAdditionalOptions(raw.services)
    const vin = getNullableString(raw.vin)
    const year = getOptionalNumber(raw.year)
    const color = getOptionalString(raw.color)
    const images = Array.isArray(raw.images)
      ? raw.images.filter((image): image is string => typeof image === 'string')
      : undefined
    const configurationName = getOptionalString(raw.configuration_name)
    const groupName = getOptionalString(raw.group_name)
    const id = isUuid(raw.id) ? raw.id : undefined
    const effectivePrice = getOptionalNumber(raw.effective_price)
    const priceFrom = getOptionalNumber(raw.price_from)

    if (modificationId !== undefined) cartItem.modification_id = modificationId
    if (complectationId !== undefined) cartItem.complectation_id = complectationId
    if (configurationId !== undefined) cartItem.configuration_id = configurationId
    if (markId !== undefined) cartItem.mark_id = markId
    if (modelId !== undefined) cartItem.model_id = modelId
    if (discountPrice !== undefined) cartItem.discount_price = discountPrice
    if (typeof raw.has_support === 'boolean') cartItem.has_support = raw.has_support
    if (supportType !== undefined) cartItem.support_type = supportType
    if (typeof raw.support_params === 'object' && raw.support_params !== undefined) {
      cartItem.support_params = raw.support_params as Record<string, unknown> | null
    }
    if (customPrice !== undefined) cartItem.custom_price = customPrice
    if (comment !== undefined) cartItem.comment = comment
    if (equipments !== undefined) cartItem.equipments = equipments
    if (services !== undefined) cartItem.services = services
    if (vin !== undefined) cartItem.vin = vin
    if (typeof raw.is_model_order === 'boolean') cartItem.is_model_order = raw.is_model_order
    if (year !== undefined) cartItem.year = year
    if (color !== undefined) cartItem.color = color
    if (images !== undefined) cartItem.images = images
    if (configurationName !== undefined) cartItem.configuration_name = configurationName
    if (groupName !== undefined) cartItem.group_name = groupName
    if (id !== undefined) cartItem.id = id
    if (effectivePrice !== undefined) cartItem.effective_price = effectivePrice
    if (priceFrom !== undefined) cartItem.price_from = priceFrom
    if (transferId) cartItem.transfer_id = transferId

    return cartItem
  }

  // Computed properties
  const totalItems = computed(() => items.value.length)
  const selectedItems = computed(() => items.value.filter(item => item.is_selected))
  const selectedCount = computed(() => 
    selectedItems.value.reduce((sum, item) => sum + (item.quantity || 1), 0)
  )
  
  const totalAmount = computed(() => 
    selectedItems.value.reduce((sum, item) => {
      // Приоритет: custom_price > discount_price > base_price
      const price = Number(item.custom_price) || Number(item.discount_price) || Number(item.base_price) || 0
      return sum + price * (item.quantity || 1)
    }, 0)
  )

  const baseTotal = computed(() =>
    selectedItems.value.reduce((sum, item) => {
      const price = Number(item.base_price) || 0
      return sum + (isNaN(price) ? 0 : price) * (item.quantity || 1)
    }, 0)
  )

  const totalDiscount = computed(() =>
    selectedItems.value.reduce((sum, item) => {
      const basePrice = Number(item.base_price) || 0
      const discountPrice = Number(item.discount_price) || 0
      if (discountPrice > 0 && !isNaN(basePrice) && !isNaN(discountPrice)) {
        return sum + (basePrice - discountPrice) * (item.quantity || 1)
      }
      return sum
    }, 0)
  )

  const selectedVehicleIds = computed<UUID[]>(() =>
    selectedItems.value.map(item => item.vehicle_id)
  )

  /** For calculator UI: show two columns (direct) or support row (refund). Direct takes precedence. */
  const supportDisplayMode = computed((): SupportDisplayMode => {
    const selected = selectedItems.value
    const hasDirect = selected.some(
      (i) => i.has_support && i.support_type === SUPPORT_TYPE_DIRECT
    )
    const hasRefund = selected.some(
      (i) => i.has_support && i.support_type && SUPPORT_TYPE_REFUND.includes(i.support_type as SupportTypeRefund)
    )
    if (hasDirect) return 'direct'
    if (hasRefund) return 'refund'
    return null
  })

  const isEmpty = computed(() => totalItems.value === 0)
  const hasSelectedItems = computed(() => selectedCount.value > 0)

  // Guest cart helpers
  const persistGuestCartEntries = (entries: unknown[]) => {
    if (!import.meta.client) return

    if (entries.length === 0) {
      localStorage.removeItem(GUEST_CART_KEY.value)
      return
    }

    localStorage.setItem(GUEST_CART_KEY.value, JSON.stringify(entries))
  }

  const saveGuestCart = () => {
    if (import.meta.client) {
      const entries = entriesForGuestCartSave(
        items.value,
        localStorage.getItem(GUEST_CART_KEY.value),
      )
      persistGuestCartEntries(entries)
    }
  }

  const loadGuestCart = (): CartItem[] => {
    if (import.meta.client) {
      const snapshot = parseGuestCartStorage(localStorage.getItem(GUEST_CART_KEY.value))
      if (snapshot.malformed) {
        console.error('Error parsing guest cart: storage payload is not a JSON array')
        return []
      }

      return snapshot.validEntries.map(toCartItem)
    }
    return []
  }

  const clearGuestCart = () => {
    if (import.meta.client) {
      localStorage.removeItem(GUEST_CART_KEY.value)
    }
  }

  /** Обновить cart-support по support-status: убрать устаревшие id, добавить новые доступные программы. */
  const refreshSupportSelectionsFromServer = async () => {
    const vehicleIds = items.value.map(item => item.vehicle_id)

    if (vehicleIds.length === 0) return

    try {
      const data: any = await $fetch('/api/v1/calculator/support-status', {
        method: 'POST',
        body: { vehicle_ids: vehicleIds },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      const statuses: SupportStatusItem[] = Array.isArray(data?.items) ? data.items : []
      const byVehicleId = new Map(statuses.map(status => [status.vehicle_id, status]))

      items.value = items.value.map((item) => {
        const status = byVehicleId.get(item.vehicle_id)
        if (!status) return item

        return {
          ...item,
          has_support: Boolean(status.has_support),
          support_type: status.support_type || null,
          support_params: status.support_params || null,
          applicable_support_programs: status.applicable_support_programs || []
        }
      })

      for (const status of statuses) {
        supportSelection.ensureProgramsApplied(
          status.vehicle_id,
          Array.isArray(status.applicable_support_programs)
            ? status.applicable_support_programs.map(program => program.id)
            : (Array.isArray(status.eligible_program_ids) ? status.eligible_program_ids : [])
        )
      }
    } catch (error) {
      console.error('Error refreshing support selections from server:', error)
    }
  }

  const refreshGuestSupportInfo = async () => {
    if (authStore.isAuthenticated || items.value.length === 0) return

    const vehicleIds = items.value.map(item => item.vehicle_id)

    if (vehicleIds.length === 0) return

    try {
      const data: any = await $fetch('/api/v1/calculator/support-status', {
        method: 'POST',
        body: { vehicle_ids: vehicleIds },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      const statuses: SupportStatusItem[] = Array.isArray(data?.items) ? data.items : []
      const byVehicleId = new Map(statuses.map(status => [status.vehicle_id, status]))

      let changed = false
      items.value = items.value.map((item) => {
        const status = byVehicleId.get(item.vehicle_id)
        if (!status) return item

        const hasSupport = Boolean(status.has_support)
        const supportType = status.support_type || null
        const supportParams = status.support_params || null
        const applicableSupportPrograms = status.applicable_support_programs || []
        const oldParamsKey = JSON.stringify(item.support_params || null)
        const newParamsKey = JSON.stringify(supportParams)
        const oldProgramsKey = JSON.stringify(item.applicable_support_programs || [])
        const newProgramsKey = JSON.stringify(applicableSupportPrograms)

        if (
          item.has_support === hasSupport &&
          (item.support_type || null) === supportType &&
          oldParamsKey === newParamsKey &&
          oldProgramsKey === newProgramsKey
        ) {
          return item
        }

        changed = true
        return {
          ...item,
          has_support: hasSupport,
          support_type: supportType,
          support_params: supportParams,
          applicable_support_programs: applicableSupportPrograms
        }
      })

      if (changed) {
        saveGuestCart()
      }

      // Обновляем cart-support для гостей по тем же данным
      for (const status of statuses) {
        supportSelection.ensureProgramsApplied(
          status.vehicle_id,
          Array.isArray(status.applicable_support_programs)
            ? status.applicable_support_programs.map(program => program.id)
            : (Array.isArray(status.eligible_program_ids) ? status.eligible_program_ids : [])
        )
      }
    } catch (error) {
      console.error('Error refreshing guest support info:', error)
    }
  }

  // Actions
  const fetchCart = async () => {
    try {
      if (fetchingCart.value) {
        return { success: true }
      }
      fetchingCart.value = true

      if (authStore.isLeasingCompany) {
        items.value = []
        return { success: true }
      }

      if (!authStore.isAuthenticated) {
        items.value = loadGuestCart()
        return { success: true }
      }

      loading.value = true
      const data: any = await $fetch(apiPath('/cart/'), {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      items.value = data.items || []
      // После загрузки корзины синхронизируем cart-support с доступными программами
      await refreshSupportSelectionsFromServer()
      return { success: true }
    } catch (error: unknown) {
      console.error('Error fetching cart:', error)
      const fetchErr = error as { data?: { error?: string } }
      return {
        success: false,
        error: fetchErr.data?.error || 'Ошибка загрузки корзины'
      }
    } finally {
      fetchingCart.value = false
      loading.value = false
    }
  }

  const addToCart = async (vehicleId: UUID, carData?: any) => {
    try {
      loading.value = true

      // For authenticated users, use API
      if (authStore.isAuthenticated) {
        const data: any = await $fetch(apiPath('/cart/'), {
          method: 'POST',
          body: { vehicle_id: vehicleId, quantity: 1 },
          baseURL: config.public.apiBase,
          credentials: 'include'
        })

        // Refresh cart to get updated data
        await fetchCart()

        return { success: true, message: data.message }
      } else {
        // For guests, use localStorage
        const existingItem = items.value.find(item => 
          item.vehicle_id === vehicleId
        )
        
        if (existingItem) {
          return { success: false, error: 'Автомобиль уже в корзине' }
        }

        const cartItem: CartItem = {
          ...(carData || {}),
          cart_id: crypto.randomUUID(),
          vehicle_id: vehicleId,
          mark_name: carData?.mark_name || 'Автомобиль',
          model_name: carData?.model_name || '',
          base_price: carData?.base_price ?? 0,
          discount_price: carData?.discount_price ?? null,
          is_selected: carData?.is_selected ?? true,
          added_at: new Date().toISOString(),
          quantity: 1,
          transfer_id: crypto.randomUUID(),
        }

        items.value.push(cartItem)
        saveGuestCart()
        await refreshGuestSupportInfo()
        
        return { success: true, message: 'Добавлено в корзину' }
      }
    } catch (error: any) {
      console.error('Error adding to cart:', error)
      return { 
        success: false, 
        error: error.data?.error || 'Ошибка добавления в корзину' 
      }
    } finally {
      loading.value = false
    }
  }

  const removeFromCart = async (vehicleId: UUID) => {
    try {
      loading.value = true

      if (authStore.isAuthenticated) {
        const data: any = await $fetch(apiPath(`/cart/${vehicleId}`), {
          method: 'DELETE',
          baseURL: config.public.apiBase,
          credentials: 'include'
        })

        // Remove item from local state
        items.value = items.value.filter(item => item.vehicle_id !== vehicleId)
        
        return { success: true, message: data.message }
      } else {
        // For guests, remove from localStorage
        items.value = items.value.filter(item => 
          item.vehicle_id !== vehicleId
        )
        saveGuestCart()
        
        return { success: true, message: 'Удалено из корзины' }
      }
    } catch (error: any) {
      console.error('Error removing from cart:', error)
      return { 
        success: false, 
        error: error.data?.error || 'Ошибка удаления из корзины' 
      }
    } finally {
      loading.value = false
    }
  }

  const updateSelection = async (vehicleId: UUID, isSelected: boolean) => {
    if (authStore.isAuthenticated) {
      try {
        const data: any = await $fetch(apiPath(`/cart/${vehicleId}`), {
          method: 'PATCH',
          body: { is_selected: isSelected },
          baseURL: config.public.apiBase,
          credentials: 'include'
        })

        const item = items.value.find(item => item.vehicle_id === vehicleId)
        if (item) {
          item.is_selected = isSelected
        }

        return { success: true }
      } catch (error: any) {
        console.error('Error updating selection:', error)
        return { 
          success: false, 
          error: error.data?.error || 'Ошибка обновления выбора' 
        }
      }
    } else {
      const item = items.value.find(item => item.vehicle_id === vehicleId)
      if (item) {
        item.is_selected = isSelected
        saveGuestCart()
        return { success: true }
      }
      return { success: false, error: 'Элемент не найден в корзине' }
    }
  }

  const bulkUpdateSelection = async (updates: Array<{ vehicle_id: UUID; is_selected: boolean }>) => {
    try {
      loading.value = true
      const data: any = await $fetch(apiPath('/cart/'), {
        method: 'PATCH',
        body: { items: updates },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })

      updates.forEach(update => {
        const item = items.value.find(item => item.vehicle_id === update.vehicle_id)
        if (item) {
          item.is_selected = update.is_selected
        }
      })

      return { success: true, message: data.message }
    } catch (error: any) {
      console.error('Error bulk updating cart:', error)
      return { 
        success: false, 
        error: error.data?.error || 'Ошибка массового обновления' 
      }
    } finally {
      loading.value = false
    }
  }

  const clearCart = async () => {
    try {
      loading.value = true

      if (authStore.isAuthenticated) {
        const data: any = await $fetch(apiPath('/cart/'), {
          method: 'DELETE',
          baseURL: config.public.apiBase,
          credentials: 'include'
        })

        items.value = []
        
        return { success: true, message: data.message }
      } else {
        // For guests, clear localStorage
        items.value = []
        clearGuestCart()
        
        return { success: true, message: 'Корзина очищена' }
      }
    } catch (error: any) {
      console.error('Error clearing cart:', error)
      return { 
        success: false, 
        error: error.data?.error || 'Ошибка очистки корзины' 
      }
    } finally {
      loading.value = false
    }
  }

  const selectAll = async () => {
    if (authStore.isAuthenticated) {
      const updates = items.value.map(item => ({
        vehicle_id: item.vehicle_id,
        is_selected: true
      }))
      return await bulkUpdateSelection(updates)
    } else {
      items.value.forEach(item => {
        item.is_selected = true
      })
      saveGuestCart()
      return { success: true, message: 'Все элементы выбраны' }
    }
  }

  const unselectAll = async () => {
    if (authStore.isAuthenticated) {
      const updates = items.value.map(item => ({
        vehicle_id: item.vehicle_id,
        is_selected: false
      }))
      return await bulkUpdateSelection(updates)
    } else {
      items.value.forEach(item => {
        item.is_selected = false
      })
      saveGuestCart()
      return { success: true, message: 'Выбор снят со всех элементов' }
    }
  }

  const clearSelectedItems = async () => {
    
    try {
      loading.value = true

      if (authStore.isAuthenticated) {
        // Remove selected items from server
        const selectedIds = selectedItems.value.map(item => item.vehicle_id)
        
        for (const id of selectedIds) {
          await $fetch(apiPath(`/cart/${id}`), {
            method: 'DELETE',
            baseURL: config.public.apiBase,
            credentials: 'include'
          })
        }

        // Remove from local state
        const itemsBeforeFilter = items.value.length
        items.value = items.value.filter(item => !item.is_selected)
        
        return { success: true, message: 'Выбранные элементы удалены' }
      } else {
        // For guests, remove from localStorage
        const itemsBeforeFilter = items.value.length
        items.value = items.value.filter(item => !item.is_selected)
        saveGuestCart()
        
        return { success: true, message: 'Выбранные элементы удалены' }
      }
    } catch (error: any) {
      console.error('Error clearing selected items:', error)
      return { 
        success: false, 
        error: error.data?.error || 'Ошибка удаления выбранных элементов' 
      }
    } finally {
      loading.value = false
    }
  }

  const isInCart = (vehicleId: UUID) => {
    return items.value.some(item => item.vehicle_id === vehicleId)
  }

  const performGuestCartTransfer = async () => {
    if (!import.meta.client || !authStore.isAuthenticated) return

    try {
      loading.value = true

      const snapshot = parseGuestCartStorage(localStorage.getItem(GUEST_CART_KEY.value))
      if (snapshot.malformed) {
        console.error('Error transferring guest cart: storage payload is not a JSON array')
        const result = await fetchCart()
        initialized.value = true
        return result
      }

      if (snapshot.entries.length === 0) {
        const result = await fetchCart()
        initialized.value = true
        return result
      }

      const transferResult = await transferGuestCartEntries(
        snapshot,
        {
          transferCartEntry: async ({ raw, vehicleId, transferId }) => {
            const equipments = normalizeGuestCartTransferOptions(
              raw.equipments,
              'equipment_code',
            )
            const services = normalizeGuestCartTransferOptions(
              raw.services,
              'service_code',
            )

            await cartApi.transferGuestCart(transferId, {
              vehicle_id: vehicleId,
              quantity: getGuestQuantity(raw.quantity),
              allow_overstock: raw.allow_overstock === true,
              equipments,
              services,
            })
          },
          persistRemaining: persistGuestCartEntries,
        },
      )

      for (const failure of transferResult.failures) {
        console.error(`Error adding vehicle ${failure.entry.vehicleId} to cart:`, failure.error)
      }

      const result = await fetchCart()
      initialized.value = true
      return result
    } catch (error: any) {
      console.error('Error transferring guest cart:', error)
      return { success: false, error: 'Ошибка переноса корзины' }
    } finally {
      loading.value = false
    }
  }

  const transferGuestCartToServer = createSingleFlight(performGuestCartTransfer)

  const getCartCount = async () => {
    try {
      const data: any = await $fetch(apiPath('/cart/'), {
        params: { fields: 'count' },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      return data.count || 0
    } catch (error) {
      console.error('Error getting cart count:', error)
      return 0
    }
  }

  /**
   * Client-side check using the already-loaded store state.
   * Fetches the cart first if it hasn't been initialised yet.
   */
  const checkVehicleInCart = async (vehicleId: UUID) => {
    if (authStore.isAuthenticated && !initialized.value) {
      await fetchCart()
    }
    const match = items.value.find(item => item.vehicle_id === vehicleId)
    return { in_cart: Boolean(match), cart_item: match || null }
  }

  // Backward compatibility alias
  const checkModificationInCart = checkVehicleInCart

  /** Unified partial update — hits `PATCH /cart/{vehicle_id}` with any subset of fields. */
  const patchItem = async (
    vehicleId: UUID,
    patch: {
      quantity?: number
      allow_overstock?: boolean
      custom_price?: number | null
      comment?: string | null
      is_selected?: boolean
      equipments?: AdditionalOptionSelection[]
      services?: AdditionalOptionSelection[]
    }
  ) => {
    if (authStore.isAuthenticated) {
      await $fetch(apiPath(`/cart/${vehicleId}`), {
        method: 'PATCH',
        body: patch,
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    }
    const item = items.value.find(item => item.vehicle_id === vehicleId)
    if (item) {
      if (patch.quantity !== undefined) item.quantity = patch.quantity
      if (patch.allow_overstock !== undefined) item.allow_overstock = patch.allow_overstock
      if (patch.custom_price !== undefined) item.custom_price = patch.custom_price
      if (patch.comment !== undefined) item.comment = patch.comment ?? undefined
      if (patch.is_selected !== undefined) item.is_selected = patch.is_selected
      if (patch.equipments !== undefined) item.equipments = patch.equipments
      if (patch.services !== undefined) item.services = patch.services
    }
    if (!authStore.isAuthenticated) saveGuestCart()
  }

  const updateQuantity = async (vehicleId: UUID, quantity: number, allowOverstock?: boolean) => {
    if (quantity < 1) quantity = 1
    try {
      await patchItem(vehicleId, { quantity, ...(allowOverstock === undefined ? {} : { allow_overstock: allowOverstock }) })
      return { success: true }
    } catch (error: any) {
      console.error('Error updating quantity:', error)
      return { success: false, error: error.data?.error || 'Ошибка обновления количества' }
    }
  }

  const updatePrice = async (vehicleId: UUID, customPrice: number | null) => {
    try {
      await patchItem(vehicleId, { custom_price: customPrice })
      return { success: true }
    } catch (error: any) {
      console.error('Error updating price:', error)
      return { success: false, error: error.data?.error || 'Ошибка обновления цены' }
    }
  }

  const updateComment = async (vehicleId: UUID, comment: string) => {
    try {
      await patchItem(vehicleId, { comment })
      return { success: true }
    } catch (error: any) {
      console.error('Error updating comment:', error)
      return { success: false, error: error.data?.error || 'Ошибка обновления комментария' }
    }
  }

  const updateAdditionalOptions = async (
    vehicleId: UUID,
    payload: { equipments?: AdditionalOptionSelection[]; services?: AdditionalOptionSelection[] }
  ) => {
    try {
      await patchItem(vehicleId, payload)
      return { success: true }
    } catch (error: any) {
      console.error('Error updating additional options:', error)
      return { success: false, error: error.data?.error || 'Ошибка обновления доп. опций' }
    }
  }

  const performInitialization = async () => {
    if (initialized.value) {
      return
    }

    if (authStore.isAuthenticated && !authStore.isClient && !authStore.isDealer) {
      items.value = []
      initialized.value = true
      return
    }
    
    if (authStore.isAuthenticated) {
      const result = await transferGuestCartToServer()
      if (result?.success === false) return
    } else {
      const guestItems = loadGuestCart()
      items.value = guestItems
      await refreshGuestSupportInfo()
    }

    initialized.value = true
  }

  const initialize = createSingleFlight(performInitialization)

  // Keep the public collection deeply readonly without returning readonly refs
  // as Pinia state. Computed projections are excluded from SSR serialization,
  // so hydration never attempts to assign payload values into readonly RefImpls.
  const exposedItems = computed(() => readonly(items.value))
  const exposedLoading = computed(() => loading.value)

  if (import.meta.client) {
    watch(
      () => authStore.isAuthenticated,
      async (isAuthenticated, wasAuthenticated) => {
        if (isAuthenticated && wasAuthenticated === false) {
          initialized.value = false
          await initialize()
        } else if (!isAuthenticated && wasAuthenticated === true) {
          items.value = []
          initialized.value = false
          await initialize()
        }
      }
    )
  }

  return {
    items: exposedItems,
    loading: exposedLoading,
    totalItems,
    selectedItems,
    selectedCount,
    totalAmount,
    baseTotal,
    totalDiscount,
    selectedVehicleIds,
    supportDisplayMode,
    isEmpty,
    hasSelectedItems,
    fetchCart,
    addToCart,
    removeFromCart,
    updateSelection,
    bulkUpdateSelection,
    clearCart,
    clearSelectedItems,
    selectAll,
    unselectAll,
    isInCart,
    getCartCount,
    checkVehicleInCart,
    checkModificationInCart,
    transferGuestCartToServer,
    updateQuantity,
    updatePrice,
    updateComment,
    updateAdditionalOptions,
    refreshGuestSupportInfo,
    initialize
  }
})
