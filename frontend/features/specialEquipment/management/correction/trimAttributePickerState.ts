import type { UUID } from '~/types/ids'
import type {
  CatalogTrimAttributeAssignment,
  CatalogTrimAttributeCandidateGroup,
} from './types'

export interface TrimAttributeSelection {
  selectedGroupIds: string[]
  checkedAttributeIds: UUID[]
}

export const trimAttributeGroupKey = (groupId: UUID | null): string => groupId ?? 'ungrouped'

export const trimAttributeGroupSelectionDisabled = (
  group: CatalogTrimAttributeCandidateGroup,
  selection: TrimAttributeSelection,
): boolean => {
  const hasAvailableAttributes = group.attributes.some(attribute => attribute.is_available !== false)
  const checked = new Set(selection.checkedAttributeIds)
  const hasSelectedRequiredAttributes = group.attributes.some(attribute =>
    attribute.is_required && checked.has(attribute.attribute_id))
  return !hasAvailableAttributes
    || (selection.selectedGroupIds.includes(trimAttributeGroupKey(group.group_id))
      && hasSelectedRequiredAttributes)
}

export const toggleTrimAttributeGroupSelection = (
  groups: readonly CatalogTrimAttributeCandidateGroup[],
  selection: TrimAttributeSelection,
  groupId: UUID | null,
): TrimAttributeSelection => {
  const group = groups.find(candidate => candidate.group_id === groupId)
  if (!group || trimAttributeGroupSelectionDisabled(group, selection)) return selection
  const key = trimAttributeGroupKey(groupId)
  if (selection.selectedGroupIds.includes(key)) {
    const groupAttributeIds = new Set(group.attributes.map(attribute => attribute.attribute_id))
    return {
      selectedGroupIds: selection.selectedGroupIds.filter(selectedKey => selectedKey !== key),
      checkedAttributeIds: selection.checkedAttributeIds.filter(attributeId => !groupAttributeIds.has(attributeId)),
    }
  }
  const checked = new Set(selection.checkedAttributeIds)
  for (const attribute of group.attributes) {
    if (attribute.is_required && attribute.is_available !== false) checked.add(attribute.attribute_id)
  }
  return {
    selectedGroupIds: [...selection.selectedGroupIds, key],
    checkedAttributeIds: [...checked],
  }
}

export const initialTrimAttributeSelection = (
  groups: readonly CatalogTrimAttributeCandidateGroup[],
  assignedAttributes: readonly CatalogTrimAttributeAssignment[],
): TrimAttributeSelection => {
  const assignedIds = new Set(assignedAttributes.map(item => item.attribute_id))
  const selectedGroupIds: string[] = []
  const checkedAttributeIds: UUID[] = []
  for (const group of groups) {
    const selectedAttributes = group.attributes.filter(attribute =>
      assignedIds.has(attribute.attribute_id))
    if (selectedAttributes.length === 0) continue
    selectedGroupIds.push(trimAttributeGroupKey(group.group_id))
    checkedAttributeIds.push(...selectedAttributes.map(attribute => attribute.attribute_id))
  }
  return { selectedGroupIds, checkedAttributeIds }
}

export const selectedTrimAttributeCandidates = (
  groups: readonly CatalogTrimAttributeCandidateGroup[],
  selectedGroupIds: readonly string[],
  checkedAttributeIds: readonly UUID[],
  assignedAttributes: readonly CatalogTrimAttributeAssignment[] = [],
): CatalogTrimAttributeAssignment[] => {
  const selectedGroups = new Set(selectedGroupIds)
  const checked = new Set(checkedAttributeIds)
  const assignedById = new Map(assignedAttributes.map(item => [item.attribute_id, item]))
  const assignments = new Map<UUID, CatalogTrimAttributeAssignment>()
  for (const group of groups) {
    const groupKey = trimAttributeGroupKey(group.group_id)
    if (!selectedGroups.has(groupKey)) continue
    for (const attribute of group.attributes) {
      if (!checked.has(attribute.attribute_id) || assignments.has(attribute.attribute_id)) continue
      const assigned = assignedById.get(attribute.attribute_id)
      if (attribute.is_available === false && !assigned) continue
      const assignment: CatalogTrimAttributeAssignment = {
        attribute_id: attribute.attribute_id,
        group_id: group.group_id,
        attribute_code: attribute.attribute_code,
        attribute_name: attribute.attribute_name,
        data_type: attribute.data_type,
        unit: attribute.unit,
        is_required: attribute.is_required,
        is_filterable: attribute.is_filterable,
        sort_order: attribute.sort_order,
      }
      assignments.set(attribute.attribute_id, assigned
        ? {
            ...assignment,
            is_required: assignment.is_required || assigned.is_required,
            is_filterable: assigned.is_filterable,
            sort_order: assigned.sort_order,
          }
        : assignment)
    }
  }
  return [...assignments.values()]
}
