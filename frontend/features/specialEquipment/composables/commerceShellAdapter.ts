import type { RouteLocationRaw } from 'vue-router'
import { commerceCheckoutLocation } from '~/features/commerce/adapters/commerceAdapters'
import type { UUID } from '~/types/ids'
import { toStorefrontInternalRoute, type PublicRouteBuilder } from '~/utils/storefrontRoute'
import type {
  SpecialEquipmentCheckoutIntent,
  SpecialEquipmentCommerceProduct,
} from '../types'

export type CommerceShellCountSource =
  | { kind: 'vehicle'; count: number }
  | { kind: 'special_equipment'; count: number }

export const totalCommerceShellCount = (sources: CommerceShellCountSource[]): number =>
  sources.reduce((total, source) => total + Math.max(0, source.count), 0)

export const specialEquipmentProductTitle = (product: SpecialEquipmentCommerceProduct): string => {
  if (product.title) return product.title
  const parts = [product.mark.name, product.model.name, product.modification?.name, product.trim?.name]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
  return parts.join(' ') || 'Спецтехника'
}

export const specialEquipmentProductLocation = (
  product: SpecialEquipmentCommerceProduct,
  publicRoute: PublicRouteBuilder,
): string | null => toStorefrontInternalRoute(product.detail_url, publicRoute)

export const specialEquipmentCheckoutLocation = (
  productId: UUID,
  intent: SpecialEquipmentCheckoutIntent,
  publicRoute: PublicRouteBuilder,
): RouteLocationRaw => {
  const location = commerceCheckoutLocation({ type: 'special_equipment', id: productId }, intent)
  return typeof location === 'object' && 'path' in location && typeof location.path === 'string'
    ? { ...location, path: publicRoute(location.path) }
    : location
}
