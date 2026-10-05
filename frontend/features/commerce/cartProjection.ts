import type { UUID } from '~/types/ids'
import type { SupportBadgeProgram } from '~/types/support'
import type {
  CommerceCheckoutLine,
  CommerceItem,
  CommerceItemRef,
  CommercePurchaseSelection,
} from './types'

export interface CommerceCartOption {
  equipment_code?: string
  service_code?: string
  price?: number | null
}

export interface CommerceSupportProgramInfo {
  id?: UUID
  name?: string | null
  bill_of_lading?: unknown | null
}

export interface CommerceCartLine {
  cart_id: UUID
  parent_cart_id?: UUID | null
  parent_title?: string | null
  ref: CommerceItemRef
  mark_name: string
  model_name: string
  base_price: number
  list_price?: number | null
  price_known?: boolean
  discount_price?: number | null
  custom_price?: number | null
  has_support?: boolean
  support_type?: string | null
  support_params?: Record<string, unknown> | null
  support_program_info?: CommerceSupportProgramInfo | null
  applicable_support_programs?: readonly SupportBadgeProgram[]
  comment: string
  equipments: readonly CommerceCartOption[]
  services: readonly CommerceCartOption[]
  vin?: string | null
  is_model_order?: boolean
  is_selected: boolean
  added_at: string
  year?: number
  color?: string
  quantity: number
  allow_overstock?: boolean
  available_count?: number | null
  images?: readonly string[]
  image_url: string | null
  detail_url: string | null
  configuration_name?: string
  group_name?: string
  effective_price?: number
  price_from?: number
  price_on_request?: boolean
  quantity_editable: boolean
  price_editable: boolean
  unavailable_status: string
  availability?: string
  capabilities: {
    can_lease: boolean
    can_buy: boolean
    can_preorder: boolean
  }
}

export interface CommerceCartSelectionUpdate {
  cart_item_id: UUID
  is_selected: boolean
}

export const commerceCartSelectionUpdates = (
  lines: readonly CommerceCartLine[],
  cartItemId: UUID,
  isSelected: boolean,
): CommerceCartSelectionUpdate[] => {
  const target = lines.find(line => line.cart_id === cartItemId)
  if (!target || target.ref.type !== 'special_equipment') return []

  const ids = new Set<UUID>([cartItemId])
  if (target.parent_cart_id && isSelected) ids.add(target.parent_cart_id)
  if (!target.parent_cart_id) {
    for (const line of lines) {
      if (line.ref.type === 'special_equipment' && line.parent_cart_id === cartItemId) {
        ids.add(line.cart_id)
      }
    }
  }
  return lines.flatMap(line => ids.has(line.cart_id)
    ? [{ cart_item_id: line.cart_id, is_selected: isSelected }]
    : [])
}

const finiteMoney = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export const MONEY_MINOR_SCALE = 100

export const moneyMinorUnits = (value: unknown): number => {
  const parsed = finiteMoney(value)
  if (parsed === null) return 0
  const absoluteMinor = Math.round((Math.abs(parsed) + Number.EPSILON) * MONEY_MINOR_SCALE)
  return parsed < 0 ? -absoluteMinor : absoluteMinor
}

const optionPriceMinorUnits = (option: unknown): number => {
  if (!option || typeof option !== 'object' || Array.isArray(option)) return 0
  return moneyMinorUnits((option as Record<string, unknown>).price)
}

export const commerceCartLinePrice = (line: CommerceCartLine): number =>
  finiteMoney(line.custom_price)
  ?? finiteMoney(line.discount_price)
  ?? finiteMoney(line.base_price)
  ?? 0

export const commerceCartLineOptionsTotal = (line: CommerceCartLine): number => {
  const options = [...(line.equipments ?? []), ...(line.services ?? [])]
  const totalMinor = options.reduce(
    (total, option) => total + optionPriceMinorUnits(option),
    0,
  )
  return totalMinor / MONEY_MINOR_SCALE
}

export const commerceCartBillableQuantity = (line: CommerceCartLine): number => {
  if (line.ref.type === 'special_equipment' && line.allow_overstock && typeof line.available_count === 'number') {
    return Math.min(line.quantity, line.available_count)
  }
  return line.quantity
}

export const commerceCartLineTotal = (line: CommerceCartLine): number =>
  (
    moneyMinorUnits(commerceCartLinePrice(line))
    + moneyMinorUnits(commerceCartLineOptionsTotal(line))
  ) * Math.max(1, commerceCartBillableQuantity(line)) / MONEY_MINOR_SCALE

const commerceCartCustomPrice = (line: CommerceCartLine): string | null => {
  const price = finiteMoney(line.custom_price)
  return price !== null && price > 0 ? price.toFixed(2) : null
}

export const selectedCommerceCartLines = (
  lines: readonly CommerceCartLine[],
): CommerceCartLine[] => {
  const eligibleIds = new Set(lines
    .filter(line => line.is_selected && !line.unavailable_status)
    .map(line => line.cart_id))
  return lines.filter(line => (
    eligibleIds.has(line.cart_id)
    && (!line.parent_cart_id || eligibleIds.has(line.parent_cart_id))
  ))
}

export const commerceCartRequiresManualLeasingConditions = (
  lines: readonly CommerceCartLine[],
): boolean => selectedCommerceCartLines(lines).some(line => (
  line.ref.type === 'special_equipment' && line.price_known === false
))

const MANUAL_LEASING_SHAPE_ERROR =
  'Технику без цены можно оформить в лизинг только одной единицей без автомобилей и других платных позиций.'

/**
 * Mirrors the only unpriced shape that the backend can assign to one proposal.
 * A root physical unit may have zero-price child rows, while every additional
 * root or billable child would make the unknown proposal amount ambiguous.
 */
export const commerceCartManualLeasingError = (
  lines: readonly CommerceCartLine[],
): string | null => {
  const selected = selectedCommerceCartLines(lines)
  if (!selected.some(line => (
    line.ref.type === 'special_equipment' && line.price_known === false
  ))) return null

  const roots = selected.filter(line => !line.parent_cart_id)
  if (roots.length !== 1) return MANUAL_LEASING_SHAPE_ERROR
  const root = roots[0]!
  if (
    root.ref.type !== 'special_equipment'
    || root.price_known !== false
    || root.quantity !== 1
    || commerceCartLineOptionsTotal(root) !== 0
  ) return MANUAL_LEASING_SHAPE_ERROR

  const hasUnsupportedChild = selected.some(line => (
    line.cart_id !== root.cart_id
    && (
      line.ref.type !== 'special_equipment'
      || line.parent_cart_id !== root.cart_id
      || line.price_known === false
      || commerceCartLineTotal(line) !== 0
    )
  ))
  return hasUnsupportedChild ? MANUAL_LEASING_SHAPE_ERROR : null
}

export const commerceCartSelectedCount = (lines: readonly CommerceCartLine[]): number =>
  selectedCommerceCartLines(lines).reduce((total, line) => total + commerceCartBillableQuantity(line), 0)

export const commerceCartTotalAmount = (lines: readonly CommerceCartLine[]): number =>
  selectedCommerceCartLines(lines).reduce((total, line) => total + commerceCartLineTotal(line), 0)

/**
 * Subtotal not represented by authoritative vehicle prices on the backend.
 * It contains complete special-equipment lines plus vehicle equipment/services.
 */
export const commerceCartAdditionalAmount = (lines: readonly CommerceCartLine[]): number => {
  const totalMinor = selectedCommerceCartLines(lines).reduce((total, line) => {
    if (line.ref.type === 'special_equipment') {
      return total + moneyMinorUnits(commerceCartLineTotal(line))
    }
    return total + (
      moneyMinorUnits(commerceCartLineOptionsTotal(line))
      * Math.max(1, line.quantity)
    )
  }, 0)
  return totalMinor / MONEY_MINOR_SCALE
}

export const commerceCartVehicleIds = (lines: readonly CommerceCartLine[]): UUID[] =>
  selectedCommerceCartLines(lines)
    .filter((line) => line.ref.type === 'vehicle')
    .map((line) => line.ref.id)

export const commerceCartPurchaseSelections = (
  lines: readonly CommerceCartLine[],
): CommercePurchaseSelection[] => {
  const selected = selectedCommerceCartLines(lines)
    .filter(line => line.capabilities.can_buy || line.capabilities.can_preorder)
  const selectedSpecialIds = new Set(
    selected.filter(line => line.ref.type === 'special_equipment').map(line => line.cart_id),
  )

  return selected.flatMap((line) => {
    if (line.ref.type === 'vehicle') return [{ item: line.ref, quantity: line.quantity }]
    if (line.parent_cart_id && selectedSpecialIds.has(line.parent_cart_id)) return []
    const childIds = selected
      .filter(child => child.ref.type === 'special_equipment' && child.parent_cart_id === line.cart_id)
      .map(child => child.cart_id)
    const groupLines = [
      line,
      ...selected.filter(child => (
        child.ref.type === 'special_equipment'
        && child.parent_cart_id === line.cart_id
      )),
    ]
    return [{
      item: line.ref,
      quantity: line.quantity,
      cart_item_ids: [line.cart_id, ...childIds],
      group_items: groupLines.map(groupLine => ({
        item: groupLine.ref,
        quantity: groupLine.quantity,
        price: groupLine.price_known === false
          ? null
          : commerceCartLinePrice(groupLine).toFixed(2),
      })),
    }]
  })
}

const commerceItemProjection = (line: CommerceCartLine): CommerceItem => ({
  ref: line.ref,
  title: `${line.mark_name} ${line.model_name}`.trim(),
  subtitle: line.group_name ?? null,
  image_url: line.image_url,
  detail_url: line.detail_url,
  price: line.price_known === false ? null : commerceCartLinePrice(line).toFixed(2),
  price_on_request: line.price_on_request,
  price_from: line.price_from === undefined ? null : line.price_from.toFixed(2),
  currency_code: 'RUB',
  availability: line.availability || line.unavailable_status || 'available',
  manufacturer: line.mark_name || null,
  model: line.model_name || null,
  modification: line.group_name ?? null,
  year: line.year ?? null,
  facts: [],
  capabilities: line.capabilities,
})

export const commerceCheckoutLines = (
  lines: readonly CommerceCartLine[],
): CommerceCheckoutLine[] => selectedCommerceCartLines(lines).map((line) => ({
  item: commerceItemProjection(line),
  quantity: line.quantity,
  ...(line.allow_overstock ? { allow_overstock: true } : {}),
  custom_price: commerceCartCustomPrice(line),
  comment: line.comment,
  equipments: [...(line.equipments ?? [])],
  services: [...(line.services ?? [])],
  leasing_purpose: line.ref.type === 'special_equipment' ? 'special_equipment' : null,
  leasing_purpose_comment: null,
  regions: [],
  ...(line.ref.type === 'special_equipment'
    ? { cart_item_ids: [line.cart_id] }
    : {}),
}))
