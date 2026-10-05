import type { CatalogId, UUID } from '~/types/ids'

export const normalizeDistributorMarkIds = (
  markIds: readonly CatalogId[],
  allowedMarkIds: readonly CatalogId[],
): CatalogId[] => {
  const allowedIds = new Set(allowedMarkIds)
  return Array.from(new Set(markIds.filter(markId => allowedIds.has(markId))))
}

export const emptyDistributorVehicleSelection = (): {
  mark_id: CatalogId | null
  mark_ids: CatalogId[]
  model_id: CatalogId | null
  model_ids: CatalogId[]
  complectation_ids: CatalogId[]
  vins: string[]
  dealer_group_ids: UUID[]
} => ({
  mark_id: null,
  mark_ids: [],
  model_id: null,
  model_ids: [],
  complectation_ids: [],
  vins: [],
  dealer_group_ids: [],
})
