import type { UUID } from '~/types/ids'
import type { CatalogCategoryAttributeLink } from './types'

export const appendCategoryAttributeLinks = (
  links: readonly CatalogCategoryAttributeLink[],
  attributeIds: readonly UUID[],
): CatalogCategoryAttributeLink[] => {
  const linkedIds = new Set(links.map(link => link.attribute_id))
  const uniqueNewIds = attributeIds.filter((attributeId) => {
    if (linkedIds.has(attributeId)) return false
    linkedIds.add(attributeId)
    return true
  })
  const nextSortOrder = links.reduce(
    (maximum, link) => Math.max(maximum, link.sort_order),
    -10,
  ) + 10

  return [
    ...links,
    ...uniqueNewIds.map((attributeId, index) => ({
      attribute_id: attributeId,
      group_id: null,
      is_required: false,
      is_filterable: true,
      is_visible: true,
      sort_order: nextSortOrder + index * 10,
    })),
  ]
}
