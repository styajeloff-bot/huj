import type { SpecialEquipmentPrice } from './types'
import {
  formatCommerceCatalogPrice,
  formatCommerceRequestPrice,
} from '~/features/commerce/requestPrice'

interface SpecialEquipmentPricingView {
  price: SpecialEquipmentPrice
  price_from?: SpecialEquipmentPrice
  price_on_request?: boolean
}

export const formatSpecialEquipmentMoney = (
  value: Exclude<SpecialEquipmentPrice, null>,
): string => formatCommerceCatalogPrice(value)

export const specialEquipmentPriceLabel = (
  pricing: SpecialEquipmentPricingView,
): string => formatCommerceRequestPrice(pricing)
