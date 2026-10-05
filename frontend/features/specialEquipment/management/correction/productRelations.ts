import type {
  CatalogProductAttachmentLink,
} from './types'

export type CatalogProductRelation = CatalogProductAttachmentLink

export const normalizeCatalogProductRelations = <T extends CatalogProductRelation>(
  items: readonly T[],
): T[] => items.map((item, position) => ({ ...item, position }))

export const removeCatalogProductRelation = <T extends CatalogProductRelation>(
  items: readonly T[],
  index: number,
): T[] => normalizeCatalogProductRelations(items.filter((_, position) => position !== index))
