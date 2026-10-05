import type { UUID } from '~/types/ids'
import type {
  CatalogTrimAttributeAssignment,
  CatalogTrimAttributeValue,
} from './types'

export interface TrimAttributeSyncPlan {
  remove: UUID[]
  add: CatalogTrimAttributeAssignment[]
  values: CatalogTrimAttributeValue[]
}

export interface TrimAttributeSyncCheckpoint {
  assignments: CatalogTrimAttributeAssignment[]
  values: CatalogTrimAttributeValue[]
}

export type TrimAttributeSyncMutation =
  | { type: 'remove', attributeId: UUID }
  | { type: 'add', assignment: CatalogTrimAttributeAssignment }
  | { type: 'values', values: CatalogTrimAttributeValue[] }

const valueFromAssignment = (
  assignment: CatalogTrimAttributeAssignment,
): CatalogTrimAttributeValue => ({
  attribute_id: assignment.attribute_id,
  value_number: assignment.value_number ?? null,
  value_text: assignment.value_text ?? null,
  value_boolean: assignment.value_boolean ?? null,
  option_id: assignment.option_id ?? null,
})

/**
 * Advance the confirmed server snapshot after each successful trim mutation.
 * A retry then resumes after the last acknowledged step instead of blindly
 * repeating a POST, DELETE or PUT whose response may already be durable.
 */
export const advanceTrimAttributeCheckpoint = (
  checkpoint: TrimAttributeSyncCheckpoint,
  mutation: TrimAttributeSyncMutation,
): TrimAttributeSyncCheckpoint => {
  if (mutation.type === 'remove') {
    return {
      assignments: checkpoint.assignments.filter(
        item => item.attribute_id !== mutation.attributeId,
      ),
      values: checkpoint.values.filter(
        item => item.attribute_id !== mutation.attributeId,
      ),
    }
  }

  if (mutation.type === 'add') {
    return {
      assignments: [
        ...checkpoint.assignments.filter(
          item => item.attribute_id !== mutation.assignment.attribute_id,
        ),
        mutation.assignment,
      ],
      values: [
        ...checkpoint.values.filter(
          item => item.attribute_id !== mutation.assignment.attribute_id,
        ),
        valueFromAssignment(mutation.assignment),
      ],
    }
  }

  const savedById = new Map(mutation.values.map(item => [item.attribute_id, item]))
  const savedIds = new Set(savedById.keys())
  return {
    assignments: checkpoint.assignments.map((assignment) => {
      const saved = savedById.get(assignment.attribute_id)
      return saved
        ? {
            ...assignment,
            value_number: saved.value_number,
            value_text: saved.value_text,
            value_boolean: saved.value_boolean,
            option_id: saved.option_id,
          }
        : assignment
    }),
    values: [
      ...checkpoint.values.filter(item => !savedIds.has(item.attribute_id)),
      ...mutation.values,
    ],
  }
}

const assignmentState = (item: CatalogTrimAttributeAssignment) => ({
  attribute_id: item.attribute_id,
  group_id: item.group_id,
  is_required: item.is_required,
  is_filterable: item.is_filterable,
  sort_order: item.sort_order,
})

const valueState = (item: CatalogTrimAttributeValue | undefined): CatalogTrimAttributeValue | null => {
  if (!item) return null
  const value = {
    attribute_id: item.attribute_id,
    value_number: item.value_number ?? null,
    value_text: item.value_text ?? null,
    value_boolean: item.value_boolean ?? null,
    option_id: item.option_id ?? null,
  }
  return value.value_number !== null
    || (typeof value.value_text === 'string' && value.value_text.length > 0)
    || value.value_boolean !== null
    || value.option_id !== null
    ? value
    : null
}

/** Build the sequential mutation plan required by the trim subresource API. */
export const planTrimAttributeSync = ({
  initialAssignments,
  assignments,
  initialValues,
  values,
}: {
  initialAssignments: readonly CatalogTrimAttributeAssignment[]
  assignments: readonly CatalogTrimAttributeAssignment[]
  initialValues: readonly CatalogTrimAttributeValue[]
  values: readonly CatalogTrimAttributeValue[]
}): TrimAttributeSyncPlan => {
  const initialById = new Map(initialAssignments.map(item => [item.attribute_id, item]))
  const nextById = new Map(assignments.map(item => [item.attribute_id, item]))
  const initialValuesById = new Map(initialValues.map(item => [item.attribute_id, item]))
  const valuesById = new Map(values.map(item => [item.attribute_id, item]))
  const reassign = new Set<UUID>()

  for (const assignment of assignments) {
    const initialValue = valueState(initialValuesById.get(assignment.attribute_id))
    const nextValue = valueState(valuesById.get(assignment.attribute_id))
    if (initialValue && !nextValue && assignment.data_type !== 'text') {
      reassign.add(assignment.attribute_id)
    }
  }

  const remove = initialAssignments.flatMap((item) => {
    const next = nextById.get(item.attribute_id)
    const changed = next
      && JSON.stringify(assignmentState(item)) !== JSON.stringify(assignmentState(next))
    return !next || changed || reassign.has(item.attribute_id) ? [item.attribute_id] : []
  })
  const add = assignments.filter((item) => {
    const initial = initialById.get(item.attribute_id)
    return !initial
      || JSON.stringify(assignmentState(initial)) !== JSON.stringify(assignmentState(item))
      || reassign.has(item.attribute_id)
  })
  const addedIds = new Set(add.map(item => item.attribute_id))
  const changedValues = assignments.flatMap((assignment) => {
    const initialValue = valueState(initialValuesById.get(assignment.attribute_id))
    const nextValue = valueState(valuesById.get(assignment.attribute_id))
    if (nextValue && (addedIds.has(assignment.attribute_id)
      || JSON.stringify(initialValue) !== JSON.stringify(nextValue))) return [nextValue]
    if (initialValue && !nextValue && assignment.data_type === 'text') {
      return [{
        attribute_id: assignment.attribute_id,
        value_number: null,
        value_text: '',
        value_boolean: null,
        option_id: null,
      }]
    }
    return []
  })

  return { remove, add, values: changedValues }
}
