import type { CommerceCartLine } from '~/features/commerce/cartProjection'
import type { CartItemLike } from '../types'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

const finiteMoney = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export const vehicleCommerceCartLine = (item: CartItemLike): CommerceCartLine => {
  const firstImage = item.images?.[0]
  const basePrice = finiteMoney(item.base_price) ?? 0
  return {
    cart_id: item.cart_id,
    ref: { type: 'vehicle', id: item.vehicle_id },
    mark_name: item.mark_name,
    model_name: item.model_name,
    base_price: basePrice,
    discount_price: item.discount_price,
    custom_price: item.custom_price,
    has_support: item.has_support,
    support_type: item.support_type,
    support_params: item.support_params,
    support_program_info: item.support_program_info,
    applicable_support_programs: item.applicable_support_programs,
    comment: item.comment ?? '',
    equipments: item.equipments ?? [],
    services: item.services ?? [],
    vin: item.vin,
    is_model_order: item.is_model_order,
    is_selected: item.is_selected,
    added_at: item.added_at,
    year: item.year,
    color: item.color,
    quantity: Math.max(1, item.quantity || 1),
    allow_overstock: item.allow_overstock === true,
    images: item.images,
    image_url: firstImage ? vehicleImageUrl(firstImage) : null,
    detail_url: '/special-equipment',
    configuration_name: item.configuration_name,
    group_name: item.group_name,
    effective_price: item.effective_price,
    price_from: item.price_from,
    quantity_editable: true,
    price_editable: basePrice <= 0,
    unavailable_status: '',
    availability: 'available',
    capabilities: {
      can_lease: true,
      can_buy: basePrice > 0 && !item.is_model_order,
      can_preorder: basePrice > 0 && !item.is_model_order,
    },
  }
}
