import type {
  SpecialEquipmentCatalogQuery,
  SpecialEquipmentCategoryNode,
  SpecialEquipmentCategoryPlacement,
} from './types'
import { parseSpecialEquipmentCatalogQuery } from './composables/catalogQuery'

export const resetHomepageCatalogQueryForBranch = (
  state: SpecialEquipmentCatalogQuery,
): SpecialEquipmentCatalogQuery => ({
  ...parseSpecialEquipmentCatalogQuery({}),
  sort: state.sort,
})

export const directHomepageChildCount = (
  category: SpecialEquipmentCategoryNode,
  categories: SpecialEquipmentCategoryNode[],
  placements: SpecialEquipmentCategoryPlacement[],
): number => {
  const visibleIds = new Set(categories.map(item => item.id))
  return placements.filter(item =>
    item.parent_id === category.id && visibleIds.has(item.category_id)).length
}

export const russianCountNoun = (
  count: number,
  one: string,
  few: string,
  many: string,
): string => {
  const mod100 = count % 100
  const mod10 = count % 10
  if (mod100 >= 11 && mod100 <= 14) return many
  if (mod10 === 1) return one
  if (mod10 >= 2 && mod10 <= 4) return few
  return many
}

export const homepageCategoryAction = (
  category: SpecialEquipmentCategoryNode,
  categories: SpecialEquipmentCategoryNode[],
  placements: SpecialEquipmentCategoryPlacement[],
): string => {
  const children = directHomepageChildCount(category, categories, placements)
  if (children > 0) {
    return `Показать ${children} ${russianCountNoun(children, 'категорию', 'категории', 'категорий')}`
  }
  const products = category.product_count ?? 0
  return `Показать ${products} ${russianCountNoun(products, 'объявление', 'объявления', 'объявлений')}`
}
