import type { UUID } from '~/types/ids'
import type { CatalogActiveWarehouse, CatalogDraft } from './types'

export type ProductWarehouseOwner =
  | { kind: 'owned'; companyId: UUID }
  | { kind: 'unowned' }
  | { kind: 'conflict' }

export interface ProductWarehouseDraftChange {
  draft: CatalogDraft
  message: string
}

export const productWarehouseOwner = (
  warehouse: CatalogActiveWarehouse,
): ProductWarehouseOwner => {
  const companyId = warehouse.company_id
  const dealerId = warehouse.dealer_id

  if (companyId && dealerId && companyId !== dealerId) return { kind: 'conflict' }
  if (companyId) return { kind: 'owned', companyId }
  if (dealerId) return { kind: 'owned', companyId: dealerId }
  return { kind: 'unowned' }
}

export const productWarehouseConflictMessage = (
  warehouses: CatalogActiveWarehouse[],
): string => {
  const conflicts = warehouses.filter(warehouse =>
    productWarehouseOwner(warehouse).kind === 'conflict')
  if (conflicts.length === 0) return ''
  if (conflicts.length === 1) {
    return `Склад «${conflicts[0]!.address}» скрыт: владельцы указаны неконсистентно.`
  }
  return `Скрыто складов с неконсистентными владельцами: ${conflicts.length}.`
}

export const applyProductWarehouseSelection = (
  draft: CatalogDraft,
  warehouse: CatalogActiveWarehouse | null,
): ProductWarehouseDraftChange => {
  if (!warehouse) {
    return {
      draft: { ...draft, warehouse_id: '', warehouse_id_touched: true },
      message: '',
    }
  }

  const owner = productWarehouseOwner(warehouse)
  if (owner.kind === 'conflict') {
    return {
      draft: { ...draft, warehouse_id: '', warehouse_id_touched: true },
      message: 'Склад недоступен: его владельцы указаны неконсистентно.',
    }
  }

  return {
    draft: {
      ...draft,
      warehouse_id: warehouse.id,
      warehouse_id_touched: true,
      ...(owner.kind === 'owned' ? { seller_company_id: owner.companyId } : {}),
    },
    message: '',
  }
}

export const applyProductSellerSelection = (
  draft: CatalogDraft,
  sellerCompanyId: UUID | null,
  warehouses: CatalogActiveWarehouse[],
): ProductWarehouseDraftChange => {
  const nextDraft: CatalogDraft = {
    ...draft,
    seller_company_id: sellerCompanyId ?? '',
  }
  const warehouseId = typeof draft.warehouse_id === 'string' ? draft.warehouse_id : ''
  const warehouse = warehouses.find(item => item.id === warehouseId)
  if (!warehouse) return { draft: nextDraft, message: '' }

  const owner = productWarehouseOwner(warehouse)
  if (owner.kind === 'conflict') {
    return {
      draft: { ...nextDraft, warehouse_id: '', warehouse_id_touched: true },
      message: 'Склад очищен: его владельцы указаны неконсистентно.',
    }
  }
  if (owner.kind !== 'owned' || owner.companyId === sellerCompanyId) {
    return { draft: nextDraft, message: '' }
  }
  return {
    draft: { ...nextDraft, warehouse_id: '', warehouse_id_touched: true },
    message: 'Склад очищен: он принадлежит другой компании.',
  }
}
