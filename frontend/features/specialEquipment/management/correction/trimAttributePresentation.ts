import type {
  CatalogAttribute,
  CatalogTrimAttributeAssignment,
} from './types'

export interface ProductTrimAttributeSpec {
  attributeId: CatalogTrimAttributeAssignment['attribute_id']
  name: string
  displayValue: string
}

export const presentProductTrimAttribute = (
  assignment: CatalogTrimAttributeAssignment,
  attribute?: CatalogAttribute,
): ProductTrimAttributeSpec => {
  let displayValue = assignment.value_text?.trim() || 'Не задано'
  if (assignment.option_id) {
    displayValue = assignment.options?.find(option => option.id === assignment.option_id)?.name
      ?? attribute?.options.find(option => option.id === assignment.option_id)?.name
      ?? 'Не задано'
  } else if (assignment.value_boolean !== null && assignment.value_boolean !== undefined) {
    displayValue = assignment.value_boolean ? 'Да' : 'Нет'
  } else if (assignment.value_number !== null && assignment.value_number !== undefined) {
    const unit = assignment.unit ?? attribute?.unit
    displayValue = `${assignment.value_number}${unit ? ` ${unit}` : ''}`
  }
  return {
    attributeId: assignment.attribute_id,
    name: assignment.attribute_name ?? attribute?.name ?? 'Характеристика',
    displayValue,
  }
}
