import type {
  SpecialEquipmentCategoryNode,
  SpecialEquipmentCategoryPlacement,
} from './types'

export interface SpecialEquipmentHomepagePlacement {
  category: SpecialEquipmentCategoryNode
  path: string[]
  identity: string
  sortOrder: number
}

export interface SpecialEquipmentHomepageNavigation {
  roots: SpecialEquipmentHomepagePlacement[]
  activePath: string[]
  selected: SpecialEquipmentHomepagePlacement | null
  breadcrumbs: SpecialEquipmentHomepagePlacement[]
  backPath: string[] | null
  siblings: SpecialEquipmentHomepagePlacement[]
  standardChildren: SpecialEquipmentHomepagePlacement[]
  attachmentChildren: SpecialEquipmentHomepagePlacement[]
  isLeaf: boolean
}

const placementIdentity = (path: readonly string[]): string => path.join('/')

const compareHomepagePlacements = (
  left: SpecialEquipmentHomepagePlacement,
  right: SpecialEquipmentHomepagePlacement,
): number => left.sortOrder - right.sortOrder
  || left.category.id.localeCompare(right.category.id)

const homepagePlacement = (
  category: SpecialEquipmentCategoryNode,
  path: string[],
  sortOrder: number,
): SpecialEquipmentHomepagePlacement => ({
  category,
  path,
  identity: placementIdentity(path),
  sortOrder,
})

/**
 * Projects the homepage navigation from the category DAG and its ordered
 * parent-child placements. A placement is identified by its complete slug
 * path, so the same category UUID remains distinct under different parents.
 */
export const projectSpecialEquipmentHomepageNavigation = (
  categories: readonly SpecialEquipmentCategoryNode[],
  placements: readonly SpecialEquipmentCategoryPlacement[],
  requestedPath: readonly string[],
  rootItems: readonly SpecialEquipmentCategoryNode[],
): SpecialEquipmentHomepageNavigation => {
  const categoriesById = new Map(categories.map(category => [category.id, category]))
  const placementsByParent = new Map<string, SpecialEquipmentCategoryPlacement[]>()

  for (const placement of placements) {
    if (!categoriesById.has(placement.parent_id) || !categoriesById.has(placement.category_id)) {
      continue
    }
    const current = placementsByParent.get(placement.parent_id) ?? []
    current.push(placement)
    placementsByParent.set(placement.parent_id, current)
  }

  // Root membership and ordering belong exclusively to the API.
  const roots = rootItems
    .filter(category => categoriesById.has(category.id))
    .map(category => homepagePlacement(category, [category.slug], category.sort_order))

  const childrenOf = (
    parent: SpecialEquipmentHomepagePlacement,
  ): SpecialEquipmentHomepagePlacement[] => (placementsByParent.get(parent.category.id) ?? [])
    .flatMap((placement) => {
      const category = categoriesById.get(placement.category_id)
      return category
        ? [homepagePlacement(
            category,
            [...parent.path, category.slug],
            placement.sort_order,
          )]
        : []
    })
    .sort(compareHomepagePlacements)

  const breadcrumbs: SpecialEquipmentHomepagePlacement[] = []
  let candidates = roots
  for (const slug of requestedPath) {
    const selected = candidates.find(candidate => candidate.category.slug === slug)
    if (!selected) break
    breadcrumbs.push(selected)
    candidates = childrenOf(selected)
  }

  const selected = breadcrumbs.at(-1) ?? null
  const activePath = selected ? [...selected.path] : []
  const backPath = selected ? activePath.slice(0, -1) : null
  const children = selected ? childrenOf(selected) : []
  const standardChildren = children.filter(child => !child.category.is_attachment_category)
  const attachmentChildren = children.filter(child => child.category.is_attachment_category)

  let siblings: SpecialEquipmentHomepagePlacement[] = []
  if (selected) {
    const parent = breadcrumbs.at(-2)
    const peers = parent ? childrenOf(parent) : roots
    siblings = peers.filter(peer => (
      peer.category.is_attachment_category === selected.category.is_attachment_category
    ))
  }

  return {
    roots,
    activePath,
    selected,
    breadcrumbs,
    backPath,
    siblings,
    standardChildren,
    attachmentChildren,
    isLeaf: selected !== null && children.length === 0,
  }
}
