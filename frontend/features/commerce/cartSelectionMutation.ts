import type { UUID } from '~/types/ids'

interface CommerceCartSelectionUpdate {
  cart_item_id: UUID
  is_selected: boolean
}

interface CommerceCartSelectionState {
  id: UUID
  is_selected: boolean
}

interface AtomicCommerceCartSelectionUpdateOptions {
  updates: readonly CommerceCartSelectionUpdate[]
  currentItems: readonly CommerceCartSelectionState[]
  patch: (cartItemId: UUID, isSelected: boolean) => Promise<void>
  reload: () => Promise<void>
}

const selectionMutationErrorText = (error: unknown): string => error instanceof Error
  ? error.message
  : 'Не удалось обновить выбор в корзине'

export const applyCommerceCartSelectionUpdatesAtomically = async ({
  updates,
  currentItems,
  patch,
  reload,
}: AtomicCommerceCartSelectionUpdateOptions): Promise<void> => {
  const currentById = new Map(currentItems.map(item => [item.id, item.is_selected]))
  const snapshots = updates.map((update) => {
    const isSelected = currentById.get(update.cart_item_id)
    if (isSelected === undefined) {
      throw new Error('Корзина изменилась до обновления выбора')
    }
    return { cart_item_id: update.cart_item_id, is_selected: isSelected }
  })
  const completed: CommerceCartSelectionUpdate[] = []

  try {
    for (const update of updates) {
      await patch(update.cart_item_id, update.is_selected)
      completed.push(snapshots[completed.length]!)
    }
  } catch (error: unknown) {
    const recoveryErrors: string[] = []
    for (const snapshot of [...completed].reverse()) {
      try {
        await patch(snapshot.cart_item_id, snapshot.is_selected)
      } catch (recoveryError: unknown) {
        recoveryErrors.push(selectionMutationErrorText(recoveryError))
      }
    }
    try {
      await reload()
    } catch (reloadError: unknown) {
      recoveryErrors.push(selectionMutationErrorText(reloadError))
    }
    if (recoveryErrors.length > 0) {
      throw new Error(`${selectionMutationErrorText(error)}. Не удалось полностью восстановить выбор: ${recoveryErrors.join('; ')}`)
    }
    throw error
  }
}
