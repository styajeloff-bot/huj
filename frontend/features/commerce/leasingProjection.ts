import { persistedLeasingPurposes } from '~/features/checkout/utils/leasingPurposes'
import type { CommerceCreateLeasingApplicationBody } from './api/commerceApi'
import type { CommerceCheckoutLine } from './types'

type CommerceLeasingApplicationItem = CommerceCreateLeasingApplicationBody['items'][number]

export const commerceLeasingApplicationItems = (
  lines: readonly CommerceCheckoutLine[],
): CommerceLeasingApplicationItem[] => lines.map(line => ({
  item: line.item.ref,
  quantity: line.quantity,
  ...(line.item.ref.type === 'vehicle' && line.allow_overstock ? { allow_overstock: true } : {}),
  ...(line.custom_price ? { custom_price: line.custom_price } : {}),
  ...(line.comment ? { comment: line.comment } : {}),
  equipments: line.equipments.map(option => ({ ...option })),
  services: line.services.map(option => ({ ...option })),
  leasing_purpose: persistedLeasingPurposes(line)[0],
  leasing_purposes: persistedLeasingPurposes(line),
  ...(line.leasing_purpose_comment
    ? { leasing_purpose_comment: line.leasing_purpose_comment }
    : {}),
  regions: [...line.regions],
  ...(line.item.ref.type === 'special_equipment'
    ? { cart_item_ids: [...(line.cart_item_ids ?? [])] }
    : {}),
}))
