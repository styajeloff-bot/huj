import type { CatalogCorrectionApi } from './api'
import type { CatalogSectionCounts } from './types'

type CatalogCountsApi = Pick<CatalogCorrectionApi, 'getSectionCounts'>

export const loadCatalogSectionCounts = async (
  api: CatalogCountsApi,
  signal?: AbortSignal,
): Promise<CatalogSectionCounts> => {
  const response = await api.getSectionCounts(signal)
  return {
    products: response.products,
    categories: response.categories,
    marks: response.marks,
    models: response.models,
    modifications: response.modifications,
    trims: response.trims,
    attributes: response.attributes,
    'attribute-groups': response.attribute_groups,
    colors: response.colors ?? 0,
    units: response.units ?? 0,
    superstructures: response.superstructures ?? 0,
  }
}
