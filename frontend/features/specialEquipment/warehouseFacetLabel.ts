import type { SpecialEquipmentWarehouseFacet } from './types'

const normalizedPart = (value: string | null | undefined): string => value?.trim() ?? ''

export const specialEquipmentWarehouseFacetLabel = (
  warehouse: SpecialEquipmentWarehouseFacet,
): string => {
  const primaryLabel = [warehouse.brand, warehouse.address]
    .map(normalizedPart)
    .filter(Boolean)
    .join(' · ') || 'Склад'
  const cityContext = normalizedPart(warehouse.city_name)

  return cityContext ? `${primaryLabel} (${cityContext})` : primaryLabel
}
