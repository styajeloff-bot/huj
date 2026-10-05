import type { UUID } from '~/types/ids'
import type { CatalogCategory, CatalogModification } from './types'

export const modificationCategoryIds = (
  modification: CatalogModification | null | undefined,
): UUID[] => modification ? [...modification.category_ids] : []

export const productSelectableCategoryIds = (
  categories: readonly Pick<CatalogCategory, 'id' | 'is_active'>[],
): UUID[] => categories
  .filter(category => category.is_active !== false)
  .map(category => category.id)

export const mergeProductCategoryDefaults = (
  currentCategoryIds: readonly UUID[],
  modification: CatalogModification | null | undefined,
): UUID[] => {
  const result = [...modificationCategoryIds(modification)]
  const seen = new Set(result)
  for (const categoryId of currentCategoryIds) {
    if (seen.has(categoryId)) continue
    seen.add(categoryId)
    result.push(categoryId)
  }
  return result
}

export const replaceProductCategoryDefaults = (
  currentCategoryIds: readonly UUID[],
  previousModification: CatalogModification | null | undefined,
  nextModification: CatalogModification | null | undefined,
): UUID[] => {
  const previousDefaults = new Set(modificationCategoryIds(previousModification))
  const manualCategoryIds = currentCategoryIds.filter(categoryId => !previousDefaults.has(categoryId))
  return mergeProductCategoryDefaults(manualCategoryIds, nextModification)
}

export const categoryIsInAttachmentBranch = (
  categoryId: UUID,
  categories: readonly Pick<CatalogCategory, 'id' | 'parent_ids' | 'is_attachment_category'>[],
): boolean => {
  const byId = new Map(categories.map(category => [category.id, category]))
  const visited = new Set<UUID>()
  const visit = (id: UUID): boolean => {
    if (visited.has(id)) return false
    visited.add(id)
    const category = byId.get(id)
    if (!category) return false
    return category.is_attachment_category || category.parent_ids.some(visit)
  }
  return visit(categoryId)
}

export const productCategoriesShareClassification = (
  categoryIds: readonly UUID[],
  categories: readonly Pick<CatalogCategory, 'id' | 'parent_ids' | 'is_attachment_category'>[],
): boolean => new Set(categoryIds.map(categoryId =>
  categoryIsInAttachmentBranch(categoryId, categories))).size <= 1
