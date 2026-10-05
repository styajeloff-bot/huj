import { isUuid, type UUID } from '~/types/ids'
import type {
  SpecialEquipmentCategoryNode,
  SpecialEquipmentCategoryRef,
} from './types'

export type SpecialEquipmentContextRoute =
  | { kind: 'category'; categoryPath: string[] }
  | { kind: 'product'; categoryPath: string[]; productId: UUID; productSlug: string }
  | { kind: 'invalid' }

export interface SpecialEquipmentCategoryNavigationState {
  selected: SpecialEquipmentCategoryNode | null
  path: SpecialEquipmentCategoryRef[]
  visibleCategories: Array<{
    category: SpecialEquipmentCategoryNode
    path: string[]
  }>
  attachmentCategories: Array<{
    category: SpecialEquipmentCategoryNode
    path: string[]
  }>
}

const cleanSegments = (segments: unknown): string[] => {
  const values = Array.isArray(segments)
    ? segments
    : typeof segments === 'string'
      ? [segments]
      : []
  return values.flatMap((value) => {
    if (typeof value !== 'string') return []
    const normalized = value.trim()
    return normalized && !normalized.includes('/') ? [normalized] : []
  })
}

export const parseSpecialEquipmentContextRoute = (
  rawSegments: unknown,
): SpecialEquipmentContextRoute => {
  const segments = cleanSegments(rawSegments)
  if (segments.length === 0) return { kind: 'invalid' }

  const productMarker = segments.at(-3)
  if (productMarker !== 'products') {
    return { kind: 'category', categoryPath: segments }
  }

  const productId = segments.at(-2) ?? ''
  const productSlug = segments.at(-1) ?? ''
  const categoryPath = segments.slice(0, -3)
  if (categoryPath.length === 0 || !isUuid(productId) || !productSlug) {
    return { kind: 'invalid' }
  }
  return { kind: 'product', categoryPath, productId, productSlug }
}

export const specialEquipmentCategoryPath = (path: string[]): string =>
  `/special-equipment/categories/${path.map(encodeURIComponent).join('/')}`

export const specialEquipmentProductPath = (
  productId: UUID,
  productSlug: string,
  categoryPath: string[] = [],
): string => categoryPath.length > 0
  ? `${specialEquipmentCategoryPath(categoryPath)}/products/${encodeURIComponent(productId)}/${encodeURIComponent(productSlug)}`
  : `/special-equipment/products/${encodeURIComponent(productId)}/${encodeURIComponent(productSlug)}`

export const categoryGraphRoots = (
  categories: SpecialEquipmentCategoryNode[],
): SpecialEquipmentCategoryNode[] => {
  const categoryIds = new Set(categories.map(category => category.id))
  return categories
    .filter(category => category.parent_ids.every(parentId => !categoryIds.has(parentId)))
    .sort(compareCategories)
}

const compareCategories = (
  left: SpecialEquipmentCategoryNode,
  right: SpecialEquipmentCategoryNode,
): number => left.sort_order - right.sort_order
  || left.name.localeCompare(right.name, 'ru')
  || left.id.localeCompare(right.id)

export const categoryGraphChildren = (
  categories: SpecialEquipmentCategoryNode[],
  categoryId: UUID,
): SpecialEquipmentCategoryNode[] => {
  const category = categories.find(item => item.id === categoryId)
  if (!category) return []
  const childIds = new Set(category.child_ids)
  return categories.filter(item => childIds.has(item.id)).sort(compareCategories)
}

export const effectiveAttachmentCategoryIds = (
  categories: SpecialEquipmentCategoryNode[],
): ReadonlySet<UUID> => {
  const categoryIds = new Set(categories.map(category => category.id))
  const effectiveIds = new Set<UUID>()
  const pending = categories
    .filter(category => category.is_attachment_category)
    .map(category => category.id)

  for (let index = 0; index < pending.length; index += 1) {
    const categoryId = pending[index]
    if (!categoryId || effectiveIds.has(categoryId)) continue
    effectiveIds.add(categoryId)
    const category = categories.find(item => item.id === categoryId)
    if (!category) continue
    for (const childId of category.child_ids) {
      if (categoryIds.has(childId) && !effectiveIds.has(childId)) pending.push(childId)
    }
  }
  return effectiveIds
}

/**
 * Builds path-aware placements. A category may occur under several parents,
 * therefore the placement key is the complete slug path rather than its UUID.
 */
export const createSpecialEquipmentCategoryNavigation = (
  categories: SpecialEquipmentCategoryNode[],
  resolvedPath: SpecialEquipmentCategoryRef[],
): SpecialEquipmentCategoryNavigationState => {
  const selectedRef = resolvedPath.at(-1) ?? null
  const selected = selectedRef
    ? categories.find(category => category.id === selectedRef.id) ?? null
    : null
  const parentPath = resolvedPath.map(category => category.slug)
  const visible = selected
    ? categoryGraphChildren(categories, selected.id)
    : categoryGraphRoots(categories)
  const attachmentIds = effectiveAttachmentCategoryIds(categories)
  const selectedIsAttachment = selected ? attachmentIds.has(selected.id) : false
  const ordinary = selected && !selectedIsAttachment
    ? visible.filter(category => !attachmentIds.has(category.id))
    : visible
  const attachments = selected && !selectedIsAttachment
    ? visible.filter(category => attachmentIds.has(category.id))
    : []
  const placement = (category: SpecialEquipmentCategoryNode) => ({
    category,
    path: [...parentPath, category.slug],
  })

  return {
    selected,
    path: resolvedPath,
    visibleCategories: ordinary.map(placement),
    attachmentCategories: attachments.map(placement),
  }
}

/**
 * Keeps the public active-category graph intact. Stock and announcement
 * counts describe the current assortment; they do not control navigation.
 */
export const pruneUnavailableSpecialEquipmentCategories = (
  categories: SpecialEquipmentCategoryNode[],
  _selectedPath: SpecialEquipmentCategoryRef[],
): SpecialEquipmentCategoryNode[] => categories
