import type { CommerceItem, CommercePurchaseType } from './types'

export const resolveCommerceLinePurchaseType = (
  selectedType: CommercePurchaseType,
  availability: string,
): CommercePurchaseType => {
  if (selectedType === 'full_purchase') return 'full_purchase'
  return availability === 'on_order' ? 'preorder' : 'reservation'
}

export const resolveCommerceGroupPurchaseType = (
  selectedType: CommercePurchaseType,
  items: readonly Pick<CommerceItem, 'availability'>[],
): CommercePurchaseType => {
  if (selectedType === 'full_purchase') return 'full_purchase'
  return items.some(item => item.availability === 'on_order')
    ? 'preorder'
    : 'reservation'
}
