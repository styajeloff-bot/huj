import type {
  CommerceCartLine,
  CommerceCartOption,
} from '~/features/commerce/cartProjection'
import { toStorefrontInternalRoute, type PublicRouteBuilder } from '~/utils/storefrontRoute'
import { toSpecialEquipmentProxyUrl } from '../media'
import type {
  SpecialEquipmentCartItem,
  SpecialEquipmentCommerceProduct,
} from '../types'

const finiteMoney = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const commerceCartOptions = (
  options: readonly Record<string, unknown>[],
): CommerceCartOption[] => options.map((option) => ({
  equipment_code: typeof option.equipment_code === 'string'
    ? option.equipment_code
    : undefined,
  service_code: typeof option.service_code === 'string'
    ? option.service_code
    : undefined,
  price: finiteMoney(option.price),
}))

const specialEquipmentModelName = (product: SpecialEquipmentCommerceProduct): string => {
  const mark = product.mark.name?.trim() || ''
  const model = product.model.name?.trim() || ''
  if (!mark || !model) return model || product.modification?.name?.trim() || ''
  const normalizedMark = mark.toLocaleLowerCase('ru-RU')
  const normalizedModel = model.toLocaleLowerCase('ru-RU')
  return normalizedModel.startsWith(`${normalizedMark} `)
    ? model.slice(mark.length).trim()
    : model
}

export const specialEquipmentCommerceCartLine = (
  item: SpecialEquipmentCartItem,
  publicRoute: PublicRouteBuilder,
): CommerceCartLine => {
  const product = item.product
  const requestPrice = product.price_on_request === true
    ? finiteMoney(product.price_from)
    : null
  const basePrice = requestPrice ?? finiteMoney(product.price) ?? 0
  const customPrice = finiteMoney(item.custom_price)
  const availableCount = product.available_count ?? null
  const saleStatus = product.sale_status || 'unavailable'
  const isSaleStatusAvailable = saleStatus === 'available' || saleStatus === 'on_order'
  const allowOverstock = item.allow_overstock === true
  const unavailableStatus = !isSaleStatusAvailable
    ? saleStatus
    : availableCount === null
      ? 'availability_unconfirmed'
      : (allowOverstock && (availableCount ?? 0) >= 1)
        ? ''
        : availableCount < item.quantity
          ? 'out_of_stock'
          : ''
  return {
    cart_id: item.id,
    parent_cart_id: item.parent_item_id,
    ref: { type: 'special_equipment', id: item.product_id },
    mark_name: product.mark.name?.trim() || 'Спецтехника',
    model_name: specialEquipmentModelName(product),
    base_price: basePrice,
    list_price: product.price_on_request ? null : finiteMoney(product.base_price),
    price_known: requestPrice !== null || product.price !== null || customPrice !== null,
    price_on_request: product.price_on_request === true,
    price_from: requestPrice ?? undefined,
    custom_price: customPrice,
    comment: item.comment ?? '',
    equipments: commerceCartOptions(item.equipments),
    services: commerceCartOptions(item.services),
    is_selected: item.is_selected,
    added_at: item.added_at,
    year: product.manufacture_year ?? undefined,
    color: product.body_color?.name ?? undefined,
    quantity: Math.max(1, item.quantity),
    allow_overstock: allowOverstock,
    available_count: availableCount,
    image_url: toSpecialEquipmentProxyUrl(product.primary_image?.content_url),
    detail_url: toStorefrontInternalRoute(product.detail_url, publicRoute),
    group_name: product.modification?.name ?? undefined,
    quantity_editable: isSaleStatusAvailable && availableCount !== null && availableCount > 0,
    price_editable: false,
    availability: saleStatus,
    unavailable_status: unavailableStatus,
    capabilities: {
      can_lease: product.capabilities.can_lease,
      can_buy: product.capabilities.can_buy,
      can_preorder: product.capabilities.can_preorder,
    },
  }
}
