import type {
  SpecialEquipmentAttributeSource,
  SpecialEquipmentProductAttribute,
  SpecialEquipmentProductAttributeGroup,
} from './types'

const EMPTY_DISPLAY_VALUES = new Set(['none', 'null', 'undefined'])
const DECIMAL_VALUE = /^(-?\d+)(?:[.,](\d+))?$/

const cleanText = (value: unknown): string | null => {
  if (value === null || value === undefined) return null
  const text = String(value).trim()
  if (!text || EMPTY_DISPLAY_VALUES.has(text.toLocaleLowerCase('en-US'))) return null
  return text
}

export const trimSpecialEquipmentDecimal = (value: string): string => {
  const match = DECIMAL_VALUE.exec(value.trim())
  if (!match) return value.trim()
  const fraction = (match[2] ?? '').replace(/0+$/, '')
  return fraction ? `${match[1]}.${fraction}` : match[1]!
}

export const formatSpecialEquipmentAttribute = (
  attribute: Pick<SpecialEquipmentProductAttribute, 'data_type' | 'unit' | 'value' | 'option_label'>
    & Partial<Pick<SpecialEquipmentProductAttribute, 'display_value'>>,
): string | null => {
  const rawValue = attribute.value
  let display = attribute.data_type === 'select'
    ? cleanText(attribute.option_label) ?? cleanText(attribute.display_value)
    : attribute.data_type === 'number'
      ? cleanText(rawValue) ?? cleanText(attribute.display_value)
      : cleanText(attribute.display_value) ?? cleanText(rawValue)

  if (!display) return null
  if (attribute.data_type === 'boolean') {
    if (rawValue === true || display.toLocaleLowerCase('ru-RU') === 'true') display = 'Да'
    if (rawValue === false || display.toLocaleLowerCase('ru-RU') === 'false') display = 'Нет'
  }
  if (attribute.data_type === 'number') {
    const [numberPart, ...suffixParts] = display.split(/\s+/)
    const suffix = suffixParts
      .filter(part => !EMPTY_DISPLAY_VALUES.has(part.toLocaleLowerCase('en-US')))
      .join(' ')
    display = [trimSpecialEquipmentDecimal(numberPart ?? ''), suffix].filter(Boolean).join(' ')
  }

  const unit = cleanText(attribute.unit)
  if (!unit || display.toLocaleLowerCase('ru-RU').endsWith(unit.toLocaleLowerCase('ru-RU'))) {
    return display
  }
  return `${display} ${unit}`
}

type SpecialEquipmentDetailAttribute = Pick<
  SpecialEquipmentProductAttribute,
  'data_type' | 'unit' | 'value' | 'option_label'
> & Partial<Pick<SpecialEquipmentProductAttribute, 'display_value'>>

export const presentSpecialEquipmentDetailAttribute = <T extends SpecialEquipmentDetailAttribute>(
  attribute: T,
): (T & { formatted_value: string | null }) | null => {
  if (attribute.data_type === 'boolean') {
    return attribute.value === true ? { ...attribute, formatted_value: null } : null
  }

  const formattedValue = formatSpecialEquipmentAttribute(attribute)
  return formattedValue ? { ...attribute, formatted_value: formattedValue } : null
}

export const presentSpecialEquipmentModificationAttribute = <T extends SpecialEquipmentDetailAttribute>(
  attribute: T,
): (T & { formatted_value: string | null }) | null => {
  if (attribute.data_type === 'boolean') {
    if (attribute.value === true) return { ...attribute, formatted_value: 'Да' }
    if (attribute.value === false) return { ...attribute, formatted_value: 'Нет' }
    return null
  }
  return presentSpecialEquipmentDetailAttribute(attribute)
}

export interface DisplayableSpecialEquipmentAttributeGroup
  extends Omit<SpecialEquipmentProductAttributeGroup, 'attributes'> {
  source_product: SpecialEquipmentAttributeSource | null
  attributes: Array<SpecialEquipmentProductAttribute & { formatted_value: string | null }>
}

export const displayableSpecialEquipmentAttributeGroups = (
  groups: readonly SpecialEquipmentProductAttributeGroup[],
): DisplayableSpecialEquipmentAttributeGroup[] => groups.flatMap(group => {
  const attributes = group.attributes.flatMap(attribute => {
    const presentedAttribute = presentSpecialEquipmentDetailAttribute(attribute)
    return presentedAttribute ? [presentedAttribute] : []
  })

  const sourceGroups = new Map<string, {
    source_product: SpecialEquipmentAttributeSource | null
    attributes: Array<SpecialEquipmentProductAttribute & { formatted_value: string | null }>
  }>()
  for (const attribute of attributes) {
    const source = attribute.source_product
    const sourceKey = source?.id ?? 'base-product'
    const sourceGroup = sourceGroups.get(sourceKey) ?? { source_product: source, attributes: [] }
    sourceGroup.attributes.push(attribute)
    sourceGroups.set(sourceKey, sourceGroup)
  }

  return [...sourceGroups.values()]
    .sort((left, right) => {
      if (left.source_product === null) return right.source_product === null ? 0 : -1
      if (right.source_product === null) return 1
      return left.source_product.id.localeCompare(right.source_product.id)
    })
    .map(sourceGroup => ({ ...group, ...sourceGroup }))
}).sort((left, right) => {
  if (left.id === null && right.id !== null) return 1
  if (left.id !== null && right.id === null) return -1
  return 0
})
