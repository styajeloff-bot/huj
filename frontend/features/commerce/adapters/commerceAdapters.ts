import type { RouteLocationRaw } from 'vue-router'
import type { UUID } from '~/types/ids'
import type {
  CommerceCheckoutIntent,
  CommerceDomainAdapter,
  CommerceItem,
  CommerceItemRef,
  CommerceItemType,
} from '../types'

const detailLocation = (item: CommerceItem): RouteLocationRaw | null => item.detail_url

const specialEquipmentAdapter: CommerceDomainAdapter = {
  type: 'special_equipment',
  catalogLabel: 'Каталог транспортных средств и специальной техники',
  catalogLocation: '/special-equipment',
  detailLocation,
}

const adapters: Record<CommerceItemType, CommerceDomainAdapter> = {
  vehicle: specialEquipmentAdapter,
  special_equipment: specialEquipmentAdapter,
}

export const commerceAdapterFor = (type: CommerceItemType): CommerceDomainAdapter =>
  adapters[type] ?? specialEquipmentAdapter

export const isCommerceItemType = (value: unknown): value is CommerceItemType =>
  value === 'vehicle' || value === 'special_equipment'

export const commerceItemRef = (type: CommerceItemType, id: UUID): CommerceItemRef => ({ type, id })

export const commerceCheckoutLocation = (
  item: CommerceItemRef,
  intent: CommerceCheckoutIntent,
): RouteLocationRaw => ({
  path: intent === 'leasing' ? '/cart/conditions' : '/cart',
  query: {
    item_type: item.type,
    item_id: item.id,
    intent,
  },
})

export const commerceOrderLocation = (type: CommerceItemType, orderId: UUID): RouteLocationRaw => ({
  path: `/orders/${encodeURIComponent(type)}/${encodeURIComponent(orderId)}`,
})
