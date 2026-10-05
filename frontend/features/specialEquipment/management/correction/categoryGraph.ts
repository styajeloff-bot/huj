import type { UUID } from '~/types/ids'

export interface CategoryGraphNode {
  id: UUID
  parent_ids: UUID[]
}

/**
 * Returns the complete descendant closure for one category in a DAG.
 * Historical cycles are tolerated so the edit form remains usable; the
 * backend remains responsible for rejecting a newly submitted cycle.
 */
export const categoryDescendantIds = <T extends CategoryGraphNode>(
  categories: readonly T[],
  categoryId: UUID,
): Set<UUID> => {
  const childrenByParent = new Map<UUID, UUID[]>()
  for (const category of categories) {
    for (const parentId of category.parent_ids) {
      const children = childrenByParent.get(parentId) ?? []
      children.push(category.id)
      childrenByParent.set(parentId, children)
    }
  }

  const descendants = new Set<UUID>()
  const pending = [...(childrenByParent.get(categoryId) ?? [])]
  for (let index = 0; index < pending.length; index += 1) {
    const currentId = pending[index]!
    if (currentId === categoryId || descendants.has(currentId)) continue
    descendants.add(currentId)
    pending.push(...(childrenByParent.get(currentId) ?? []))
  }
  return descendants
}
