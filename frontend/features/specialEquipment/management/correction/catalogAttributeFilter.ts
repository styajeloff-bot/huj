import type { CatalogDataType, CatalogFilterKind } from './types'

const FILTER_KINDS_BY_DATA_TYPE: Record<CatalogDataType, readonly CatalogFilterKind[]> = {
  number: ['exact', 'range'],
  text: ['exact', 'search'],
  boolean: ['exact'],
  select: ['exact'],
}

export const catalogAttributeFilterKinds = (dataType: unknown): readonly CatalogFilterKind[] =>
  typeof dataType === 'string' && dataType in FILTER_KINDS_BY_DATA_TYPE
    ? FILTER_KINDS_BY_DATA_TYPE[dataType as CatalogDataType]
    : []

export const isCatalogAttributeFilterCompatible = (
  dataType: unknown,
  filterKind: unknown,
): boolean => typeof filterKind === 'string'
  && catalogAttributeFilterKinds(dataType).includes(filterKind as CatalogFilterKind)
