import { isUuid, type UUID } from '~/types/ids'

export const SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY = 'carcraft:special-equipment:favorites:v1'
export const SPECIAL_EQUIPMENT_CART_STORAGE_KEY = 'carcraft:special-equipment:cart:v2'
export const SPECIAL_EQUIPMENT_CART_VERSION = 2 as const

const LEGACY_CART_IDS_STORAGE_KEY = 'carcraft:special-equipment:cart:v1'
const LEGACY_CART_STATE_STORAGE_KEY = 'carcraft:special-equipment:cart-state:v1'

export const SPECIAL_EQUIPMENT_MAX_CART_QUANTITY = 1000

export interface StoredSpecialEquipmentCartState {
  local_id: UUID
  product_id: UUID
  quantity: number
  allow_overstock?: boolean
  parent_local_id: UUID | null
  is_selected: boolean
  comment: string | null
  equipments: Array<Record<string, unknown>>
  services: Array<Record<string, unknown>>
}

export interface SpecialEquipmentGuestCartSnapshot {
  version: typeof SPECIAL_EQUIPMENT_CART_VERSION
  transfer_id: UUID
  items: StoredSpecialEquipmentCartState[]
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const storedOptions = (value: unknown): Array<Record<string, unknown>> =>
  Array.isArray(value)
    ? value.filter(isRecord)
    : []

const positiveQuantity = (value: unknown): number | null => {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value <= 0) return null
  return Math.min(value, SPECIAL_EQUIPMENT_MAX_CART_QUANTITY)
}

export const parseStoredLine = (value: unknown): StoredSpecialEquipmentCartState | null => {
  if (!isRecord(value)) return null
  if (!isUuid(value.local_id) || !isUuid(value.product_id)) return null
  if (value.parent_local_id !== null && !isUuid(value.parent_local_id)) return null
  const quantity = positiveQuantity(value.quantity)
  if (quantity === null) return null
  const parentLocalId = value.parent_local_id !== null && isUuid(value.parent_local_id) ? value.parent_local_id : null
  const allowOverstock = parentLocalId === null && value.allow_overstock === true

  return {
    local_id: value.local_id,
    product_id: value.product_id,
    quantity,
    allow_overstock: allowOverstock,
    parent_local_id: parentLocalId,
    is_selected: typeof value.is_selected === 'boolean' ? value.is_selected : true,
    comment: typeof value.comment === 'string' ? value.comment : null,
    equipments: storedOptions(value.equipments),
    services: storedOptions(value.services),
  }
}

export const parseGuestCart = (value: unknown): SpecialEquipmentGuestCartSnapshot | null => {
  if (!isRecord(value) || value.version !== SPECIAL_EQUIPMENT_CART_VERSION) return null
  if (!isUuid(value.transfer_id) || !Array.isArray(value.items)) return null

  const items = value.items.map(parseStoredLine)
  if (items.some(item => item === null)) return null
  const validItems = items as StoredSpecialEquipmentCartState[]
  const localIds = new Set(validItems.map(item => item.local_id))
  if (localIds.size !== validItems.length) return null
  if (validItems.some(item => item.parent_local_id !== null && !localIds.has(item.parent_local_id))) {
    return null
  }
  if (validItems.some(item => item.parent_local_id !== null && item.parent_local_id === item.local_id)) {
    return null
  }
  const childIds = new Set(validItems.filter(item => item.parent_local_id !== null).map(item => item.local_id))
  if (validItems.some(item => item.parent_local_id !== null && childIds.has(item.parent_local_id))) {
    return null
  }

  return {
    version: SPECIAL_EQUIPMENT_CART_VERSION,
    transfer_id: value.transfer_id,
    items: validItems,
  }
}

const readLegacyCart = (): SpecialEquipmentGuestCartSnapshot | null => {
  if (!import.meta.client) return null
  try {
    const idsValue: unknown = JSON.parse(localStorage.getItem(LEGACY_CART_IDS_STORAGE_KEY) ?? '[]')
    const stateValue: unknown = JSON.parse(localStorage.getItem(LEGACY_CART_STATE_STORAGE_KEY) ?? '[]')
    if (!Array.isArray(idsValue)) return null
    const productIds = [...new Set(idsValue.filter(isUuid))]
    if (productIds.length === 0) return null
    const stateByProduct = new Map<UUID, Record<string, unknown>>()
    if (Array.isArray(stateValue)) {
      for (const value of stateValue) {
        if (isRecord(value) && isUuid(value.product_id)) stateByProduct.set(value.product_id, value)
      }
    }
    return {
      version: SPECIAL_EQUIPMENT_CART_VERSION,
      transfer_id: crypto.randomUUID(),
      items: productIds.map((productId) => {
        const state = stateByProduct.get(productId)
        return {
          local_id: crypto.randomUUID(),
          product_id: productId,
          quantity: 1,
          parent_local_id: null,
          is_selected: typeof state?.is_selected === 'boolean' ? state.is_selected : true,
          comment: typeof state?.comment === 'string' ? state.comment : null,
          equipments: storedOptions(state?.equipments),
          services: storedOptions(state?.services),
        }
      }),
    }
  } catch {
    return null
  }
}

export const readSpecialEquipmentIds = (key: string): UUID[] => {
  if (!import.meta.client) return []
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(parsed) ? [...new Set(parsed.filter(isUuid))] : []
  } catch {
    return []
  }
}

export const writeSpecialEquipmentIds = (key: string, ids: Iterable<UUID>) => {
  if (!import.meta.client) return
  localStorage.setItem(key, JSON.stringify([...new Set(ids)]))
}

export const readSpecialEquipmentGuestCart = (): SpecialEquipmentGuestCartSnapshot | null => {
  if (!import.meta.client) return null
  try {
    const current = parseGuestCart(JSON.parse(localStorage.getItem(SPECIAL_EQUIPMENT_CART_STORAGE_KEY) ?? 'null'))
    if (current) return current
  } catch {
    // A malformed payload is replaced only by an explicit subsequent cart write.
  }

  const migrated = readLegacyCart()
  if (migrated) writeSpecialEquipmentGuestCart(migrated)
  return migrated
}

export const writeSpecialEquipmentGuestCart = (
  snapshot: SpecialEquipmentGuestCartSnapshot | null,
) => {
  if (!import.meta.client) return
  if (!snapshot || snapshot.items.length === 0) {
    localStorage.removeItem(SPECIAL_EQUIPMENT_CART_STORAGE_KEY)
  } else {
    localStorage.setItem(SPECIAL_EQUIPMENT_CART_STORAGE_KEY, JSON.stringify(snapshot))
  }
  localStorage.removeItem(LEGACY_CART_IDS_STORAGE_KEY)
  localStorage.removeItem(LEGACY_CART_STATE_STORAGE_KEY)
}

export const createSpecialEquipmentGuestCart = (
  items: StoredSpecialEquipmentCartState[] = [],
): SpecialEquipmentGuestCartSnapshot => ({
  version: SPECIAL_EQUIPMENT_CART_VERSION,
  transfer_id: crypto.randomUUID(),
  items,
})

export const replaceSpecialEquipmentGuestCartItems = (
  current: SpecialEquipmentGuestCartSnapshot | null,
  items: StoredSpecialEquipmentCartState[],
): SpecialEquipmentGuestCartSnapshot => ({
  version: SPECIAL_EQUIPMENT_CART_VERSION,
  transfer_id: current?.transfer_id ?? crypto.randomUUID(),
  items,
})

export interface SpecialEquipmentGuestCartGroupChild {
  product_id: UUID
  quantity: number
}

export interface SpecialEquipmentGuestCartGroupResult {
  snapshot: SpecialEquipmentGuestCartSnapshot
  parent: StoredSpecialEquipmentCartState
  children: StoredSpecialEquipmentCartState[]
}

export const reconcileSpecialEquipmentGuestCartGroup = (
  current: SpecialEquipmentGuestCartSnapshot,
  parentProductId: UUID,
  quantity: number,
  children: readonly SpecialEquipmentGuestCartGroupChild[],
  newLocalId: () => UUID,
): SpecialEquipmentGuestCartGroupResult => {
  const existingParent = current.items.find(item => (
    item.product_id === parentProductId && item.parent_local_id === null
  ))
  const parent: StoredSpecialEquipmentCartState = {
    local_id: existingParent?.local_id ?? newLocalId(),
    product_id: parentProductId,
    quantity: positiveQuantity(quantity) ?? 1,
    allow_overstock: existingParent?.allow_overstock === true,
    parent_local_id: null,
    is_selected: true,
    comment: existingParent?.comment ?? null,
    equipments: existingParent?.equipments ?? [],
    services: existingParent?.services ?? [],
  }
  const existingChildren = new Map(current.items
    .filter(item => item.parent_local_id === parent.local_id)
    .map(item => [item.product_id, item]))
  const childLines = children.map((child) => {
    const existing = existingChildren.get(child.product_id)
    return {
      local_id: existing?.local_id ?? newLocalId(),
      product_id: child.product_id,
      quantity: positiveQuantity(child.quantity) ?? 1,
      allow_overstock: false,
      parent_local_id: parent.local_id,
      is_selected: true,
      comment: existing?.comment ?? null,
      equipments: existing?.equipments ?? [],
      services: existing?.services ?? [],
    }
  })
  const unrelatedItems = current.items.filter(item => (
    item.local_id !== parent.local_id && item.parent_local_id !== parent.local_id
  ))
  return {
    snapshot: replaceSpecialEquipmentGuestCartItems(
      current,
      [...unrelatedItems, parent, ...childLines],
    ),
    parent,
    children: childLines,
  }
}

export const specialEquipmentGuestTransferBody = (
  snapshot: SpecialEquipmentGuestCartSnapshot,
) => ({
  version: SPECIAL_EQUIPMENT_CART_VERSION,
  items: snapshot.items.map(item => ({
    local_id: item.local_id,
    product_id: item.product_id,
    quantity: item.quantity,
    allow_overstock: item.allow_overstock === true,
    parent_local_id: item.parent_local_id,
    is_selected: item.is_selected,
    comment: item.comment,
    equipments: item.equipments,
    services: item.services,
  })),
})
