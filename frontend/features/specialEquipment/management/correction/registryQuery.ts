import { isUuid, type UUID } from '~/types/ids'

export type CategoryRegistrySort = 'updated_desc' | 'hierarchy'
export type ProductNormalizationState = '' | 'normalized' | 'legacy' | 'conflict'

export interface CategoryCascadeNode {
  id: UUID
  parent_ids: readonly UUID[]
}

const CATEGORY_LEVEL_COUNT = 5

export const categorySortFromQuery = (value: unknown): CategoryRegistrySort =>
  value === 'hierarchy' || value === 'updated_desc' ? value : 'updated_desc'

export const categoryLevelsFromQuery = (query: Record<string, unknown>): UUID[] => {
  const levels: UUID[] = []
  for (let level = 1; level <= CATEGORY_LEVEL_COUNT; level += 1) {
    const value = query[`level_${level}_id`]
    if (!isUuid(value)) break
    levels.push(value)
  }
  return levels
}

export const visibleCategoryLevelCount = (levels: readonly UUID[]): number =>
  Math.min(levels.length + 1, CATEGORY_LEVEL_COUNT)

export const categoryOptionsForLevel = <T extends CategoryCascadeNode>(
  categories: readonly T[],
  levels: readonly UUID[],
  index: number,
): T[] => {
  if (index === 0) return categories.filter(category => category.parent_ids.length === 0)
  const parentId = levels[index - 1]
  if (!parentId) return []
  return categories.filter(category => category.parent_ids.includes(parentId))
}

export const visibleProductCategoryLevelCount = (
  levels: readonly UUID[],
  categories: readonly CategoryCascadeNode[],
): number => {
  const selectedCount = Math.min(levels.length, CATEGORY_LEVEL_COUNT)
  if (selectedCount === 0) return 1
  if (selectedCount === CATEGORY_LEVEL_COUNT) return CATEGORY_LEVEL_COUNT
  const hasDirectChildren = categoryOptionsForLevel(
    categories,
    levels,
    selectedCount,
  ).length > 0
  return selectedCount + (hasDirectChildren ? 1 : 0)
}

export const replaceCategoryLevel = (
  levels: readonly UUID[],
  index: number,
  selectedId: UUID | null,
): UUID[] => {
  const ancestors = levels.slice(0, index)
  return selectedId ? [...ancestors, selectedId] : ancestors
}

export const buildCategoryRegistryQuery = (
  levels: readonly UUID[],
  sort: CategoryRegistrySort,
): Record<string, string | undefined> => ({
  level_1_id: levels[0],
  level_2_id: levels[1],
  level_3_id: levels[2],
  level_4_id: levels[3],
  level_5_id: levels[4],
  sort,
})

export const buildProductRegistryQuery = (
  levels: readonly UUID[],
  normalizationState: ProductNormalizationState,
): Record<string, string | undefined> => ({
  level_1_id: levels[0],
  level_2_id: levels[1],
  level_3_id: levels[2],
  level_4_id: levels[3],
  level_5_id: levels[4],
  normalization_state: normalizationState || undefined,
})
