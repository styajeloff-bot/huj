import type { UUID } from '~/types/ids'
import type { SpecialEquipmentPrice } from './types'

export interface SpecialEquipmentCartCreationResult {
  created: boolean
  cart_item: { id: UUID }
}

export const createdSpecialEquipmentCartItemIds = (
  results: readonly SpecialEquipmentCartCreationResult[],
): UUID[] => results.flatMap(result => result.created ? [result.cart_item.id] : [])

export interface SpecialEquipmentServerCartSnapshot {
  id: UUID
  product_id: UUID
  quantity: number
  parent_item_id: UUID | null
  is_selected: boolean
  custom_price: SpecialEquipmentPrice
  comment: string | null
  equipments: Array<Record<string, unknown>>
  services: Array<Record<string, unknown>>
}

interface ServerCartCreateBody {
  product_id: UUID
  quantity: number
  parent_item_id: UUID | null
  is_selected: boolean
  comment: string | null
  equipments: Array<Record<string, unknown>>
  services: Array<Record<string, unknown>>
}

interface ServerCartPatchBody {
  quantity: number
  parent_item_id: UUID | null
  is_selected: boolean
  custom_price: SpecialEquipmentPrice
  comment: string | null
  equipments: Array<Record<string, unknown>>
  services: Array<Record<string, unknown>>
}

export interface SpecialEquipmentServerCartApi {
  createCartItem: (body: ServerCartCreateBody) => Promise<SpecialEquipmentCartCreationResult>
  updateCartItem: (cartItemId: UUID, body: ServerCartPatchBody) => Promise<unknown>
  removeCartItem: (cartItemId: UUID) => Promise<unknown>
}

export interface ReconcileSpecialEquipmentServerCartGroupOptions {
  api: SpecialEquipmentServerCartApi
  currentItems: readonly SpecialEquipmentServerCartSnapshot[]
  parentProductId: UUID
  quantity: number
  children: ReadonlyArray<{ productId: UUID; quantity: number }>
}

export interface ReconciledSpecialEquipmentServerCartGroup {
  parentCartItemId: UUID
  cartItemIds: UUID[]
}

const createBody = (
  item: SpecialEquipmentServerCartSnapshot,
): ServerCartCreateBody => ({
  product_id: item.product_id,
  quantity: item.quantity,
  parent_item_id: item.parent_item_id,
  is_selected: item.is_selected,
  comment: item.comment,
  equipments: item.equipments.map(option => ({ ...option })),
  services: item.services.map(option => ({ ...option })),
})

const patchBody = (
  item: SpecialEquipmentServerCartSnapshot,
): ServerCartPatchBody => ({
  quantity: item.quantity,
  parent_item_id: item.parent_item_id,
  is_selected: item.is_selected,
  custom_price: item.custom_price,
  comment: item.comment,
  equipments: item.equipments.map(option => ({ ...option })),
  services: item.services.map(option => ({ ...option })),
})

const errorText = (error: unknown): string => error instanceof Error
  ? error.message
  : 'Не удалось согласовать комплект корзины'

export const reconcileSpecialEquipmentServerCartGroup = async ({
  api,
  currentItems,
  parentProductId,
  quantity,
  children,
}: ReconcileSpecialEquipmentServerCartGroupOptions): Promise<ReconciledSpecialEquipmentServerCartGroup> => {
  const snapshotsById = new Map(currentItems.map(item => [item.id, item]))
  const createdIds: UUID[] = []
  const mutatedSnapshots = new Map<UUID, SpecialEquipmentServerCartSnapshot>()
  const deletedSnapshots: SpecialEquipmentServerCartSnapshot[] = []
  const rememberCreation = (result: SpecialEquipmentCartCreationResult) => {
    if (result.created) {
      createdIds.push(result.cart_item.id)
      return
    }
    const snapshot = snapshotsById.get(result.cart_item.id)
    if (!snapshot) {
      throw new Error('Корзина изменилась до завершения сборки комплекта')
    }
    mutatedSnapshots.set(snapshot.id, snapshot)
  }

  try {
    const parentResult = await api.createCartItem({
      product_id: parentProductId,
      quantity,
      parent_item_id: null,
      is_selected: true,
      comment: null,
      equipments: [],
      services: [],
    })
    rememberCreation(parentResult)
    const parentCartItemId = parentResult.cart_item.id
    const desiredProductIds = new Set(children.map(child => child.productId))
    const childIds: UUID[] = []
    for (const child of children) {
      const result = await api.createCartItem({
        product_id: child.productId,
        quantity: child.quantity,
        parent_item_id: parentCartItemId,
        is_selected: true,
        comment: null,
        equipments: [],
        services: [],
      })
      rememberCreation(result)
      childIds.push(result.cart_item.id)
    }
    const staleChildren = currentItems.filter(item => (
      item.parent_item_id === parentCartItemId
      && !desiredProductIds.has(item.product_id)
    ))
    for (const stale of staleChildren) {
      await api.removeCartItem(stale.id)
      deletedSnapshots.push(stale)
    }
    return { parentCartItemId, cartItemIds: [parentCartItemId, ...childIds] }
  } catch (error: unknown) {
    const compensationFailures: string[] = []
    for (const cartItemId of [...createdIds].reverse()) {
      try {
        await api.removeCartItem(cartItemId)
      } catch (compensationError: unknown) {
        compensationFailures.push(errorText(compensationError))
      }
    }
    for (const snapshot of mutatedSnapshots.values()) {
      try {
        await api.updateCartItem(snapshot.id, patchBody(snapshot))
      } catch (compensationError: unknown) {
        compensationFailures.push(errorText(compensationError))
      }
    }
    for (const snapshot of deletedSnapshots) {
      try {
        const restored = await api.createCartItem(createBody(snapshot))
        if (snapshot.custom_price !== null) {
          await api.updateCartItem(restored.cart_item.id, patchBody(snapshot))
        }
      } catch (compensationError: unknown) {
        compensationFailures.push(errorText(compensationError))
      }
    }
    if (compensationFailures.length > 0) {
      throw new Error(`${errorText(error)}. Не удалось полностью восстановить корзину: ${compensationFailures.join('; ')}`)
    }
    throw error
  }
}
