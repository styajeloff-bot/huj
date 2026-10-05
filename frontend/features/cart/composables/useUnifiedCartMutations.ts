import type { Ref } from 'vue'
import {
  commerceCartSelectionUpdates,
  type CommerceCartLine,
} from '~/features/commerce/cartProjection'
import { applyCommerceCartSelectionUpdatesAtomically } from '~/features/commerce/cartSelectionMutation'
import type { CommerceItemRef } from '~/features/commerce/types'
import { useSpecialEquipmentCommerceShellStore } from '~/features/specialEquipment/store/commerceShell'
import { useCartStore } from '~/features/cart/store/cart'
import type { UUID } from '~/types/ids'

interface UnifiedCartMutationOptions {
  items: Readonly<Ref<CommerceCartLine[]>>
  recalculate: () => Promise<boolean>
  onCleared?: () => void
}

export const useUnifiedCartMutations = ({
  items,
  recalculate,
  onCleared,
}: UnifiedCartMutationOptions) => {
  const cartStore = useCartStore()
  const specialEquipmentShell = useSpecialEquipmentCommerceShellStore()
  const toast = useToast()

  const allSelected = computed(() => items.value.length > 0
    && items.value.every(item => item.is_selected || Boolean(item.unavailable_status)))

  const updateSelection = async (
    item: CommerceItemRef,
    isSelected: boolean,
    cartItemId?: UUID,
  ) => {
    try {
      if (item.type === 'vehicle') {
        const result = await cartStore.updateSelection(item.id, isSelected)
        if (!result.success) throw new Error(result.error)
      } else {
        if (!cartItemId) throw new Error('Не удалось определить позицию корзины')
        const updates = commerceCartSelectionUpdates(items.value, cartItemId, isSelected)
        if (updates.length === 0) throw new Error('Не удалось определить комплект в корзине')
        await applyCommerceCartSelectionUpdatesAtomically({
          updates,
          currentItems: specialEquipmentShell.cartItems,
          patch: async (selectionCartItemId, selectionState) => {
            await specialEquipmentShell.updateCartItem(selectionCartItemId, {
              is_selected: selectionState,
            })
          },
          reload: async () => {
            const loaded = await specialEquipmentShell.loadCart({
              force: true,
              resolveGuestProducts: true,
            })
            if (!loaded) {
              throw new Error(specialEquipmentShell.cartError || 'Не удалось обновить корзину')
            }
          },
        })
      }
      await recalculate()
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось обновить выбор транспортного средства')
    }
  }

  const removeItem = async (item: CommerceItemRef, cartItemId?: UUID) => {
    try {
      if (item.type === 'vehicle') {
        const result = await cartStore.removeFromCart(item.id)
        if (!result.success) throw new Error(result.error)
      } else {
        if (!cartItemId) throw new Error('Не удалось определить позицию корзины')
        await specialEquipmentShell.removeCartItem(cartItemId)
      }
      await recalculate()
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось удалить транспортное средство из корзины')
    }
  }

  const removeItemWithConfirm = (item: CommerceItemRef, cartItemId?: UUID) => {
    if (confirm('Удалить транспортное средство из корзины?')) {
      void removeItem(item, cartItemId)
    }
  }

  const selectAll = async () => {
    try {
      if (cartStore.items.length > 0) {
        const vehicleResult = await cartStore.selectAll()
        if (!vehicleResult.success) throw new Error(vehicleResult.error)
      }
      await Promise.all(
        specialEquipmentShell.cartItems
          .filter(item => !item.is_selected)
          .map(item => specialEquipmentShell.updateCartItem(item.id, { is_selected: true })),
      )
      await recalculate()
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось выбрать все транспортные средства')
    }
  }

  const unselectAll = async () => {
    try {
      if (cartStore.items.length > 0) {
        const vehicleResult = await cartStore.unselectAll()
        if (!vehicleResult.success) throw new Error(vehicleResult.error)
      }
      await Promise.all(
        specialEquipmentShell.cartItems
          .filter(item => item.is_selected)
          .map(item => specialEquipmentShell.updateCartItem(item.id, { is_selected: false })),
      )
      await recalculate()
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось снять выбор с транспортных средств')
    }
  }

  const clearCart = async () => {
    if (!confirm('Вы уверены, что хотите очистить корзину?')) return
    try {
      if (cartStore.items.length > 0) {
        const vehicleResult = await cartStore.clearCart()
        if (!vehicleResult.success) throw new Error(vehicleResult.error)
      }
      if (specialEquipmentShell.cartIds.length > 0) {
        await specialEquipmentShell.clearCart()
      }
      onCleared?.()
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось полностью очистить корзину')
    }
  }

  const updateItemQuantity = async (
    item: CommerceItemRef,
    quantity: number,
    cartItemId?: UUID,
    allowOverstock?: boolean,
    onSettled?: () => void,
  ) => {
    try {
      if (item.type === 'vehicle') {
        const result = await cartStore.updateQuantity(item.id, quantity, allowOverstock)
        if (!result.success) {
          console.error(result.error)
          toast.error('Не удалось обновить количество')
          return
        }
      } else {
        if (!cartItemId) {
          toast.error('Не удалось определить позицию корзины')
          return
        }
        try {
          await specialEquipmentShell.updateCartItem(cartItemId, {
            quantity,
            ...(allowOverstock !== undefined ? { allow_overstock: allowOverstock } : {}),
          })
        } catch (requestError: unknown) {
          console.error(requestError)
          const failure = requestError as { data?: { detail?: string; title?: string; message?: string }; message?: string }
          const message = failure?.data?.detail ?? failure?.data?.title ?? failure?.data?.message ?? failure?.message ?? 'Не удалось обновить количество. Проверьте доступный остаток.'
          toast.error(message)
          return
        }
      }
      await recalculate()
    } finally {
      onSettled?.()
    }
  }

  const updateItemPrice = async (item: CommerceItemRef, price: number | null, cartItemId?: UUID) => {
    try {
      if (item.type === 'vehicle') {
        const result = await cartStore.updatePrice(item.id, price)
        if (!result.success) throw new Error(result.error)
      } else {
        if (!cartItemId) throw new Error('Не удалось определить позицию корзины')
        await specialEquipmentShell.updateCartItem(cartItemId, { custom_price: price })
      }
      await recalculate()
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось обновить цену')
    }
  }

  const updateItemComment = async (item: CommerceItemRef, comment: string, cartItemId?: UUID) => {
    try {
      if (item.type === 'vehicle') {
        const result = await cartStore.updateComment(item.id, comment)
        if (!result.success) throw new Error(result.error)
      } else {
        if (!cartItemId) throw new Error('Не удалось определить позицию корзины')
        await specialEquipmentShell.updateCartItem(cartItemId, { comment })
      }
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось сохранить комментарий')
    }
  }

  const updateItemAdditionalOptions = async (
    item: CommerceItemRef,
    payload: {
      equipments?: Array<{ equipment_code: string; price?: number | null }>
      services?: Array<{ service_code: string; price?: number | null }>
    },
    cartItemId?: UUID,
  ) => {
    try {
      if (item.type === 'vehicle') {
        const result = await cartStore.updateAdditionalOptions(item.id, payload)
        if (!result.success) throw new Error(result.error)
      } else {
        if (!cartItemId) throw new Error('Не удалось определить позицию корзины')
        await specialEquipmentShell.updateCartItem(cartItemId, payload)
      }
      await recalculate()
    } catch (requestError: unknown) {
      console.error(requestError)
      toast.error('Не удалось сохранить дополнительные опции')
    }
  }

  return {
    allSelected,
    clearCart,
    removeItem,
    removeItemWithConfirm,
    selectAll,
    unselectAll,
    updateItemAdditionalOptions,
    updateItemComment,
    updateItemPrice,
    updateItemQuantity,
    updateSelection,
  }
}
