/**
 * Pluralization and naming helpers for Russian special equipment catalog entities.
 */

export function pluralizeRussian(count: number, one: string, two: string, five: string): string {
  const abs = Math.abs(Math.trunc(count)) % 100
  const rem = abs % 10
  if (abs > 10 && abs < 20) return five
  if (rem > 1 && rem < 5) return two
  if (rem === 1) return one
  return five
}

export function formatPlural(count: number, one: string, two: string, five: string): string {
  return `${count} ${pluralizeRussian(count, one, two, five)}`
}

export interface EntityPluralForms {
  singular: string // Именительный падеж ед.ч.: "марка", "категория"
  accusative: string // Винительный падеж ед.ч.: "марку", "категорию"
  genitiveSingular: string // Родительный ед.ч. (для 2, 3, 4): "марки", "категории"
  genitivePlural: string // Родительный мн.ч. (для 5..): "марок", "категорий"
  nominativePlural: string // Именительный мн.ч.: "марки", "категории"
}

export const CATALOG_ENTITY_NAMES: Record<string, EntityPluralForms> = {
  marks: {
    singular: 'марка',
    accusative: 'марку',
    genitiveSingular: 'марки',
    genitivePlural: 'марок',
    nominativePlural: 'марки',
  },
  mark: {
    singular: 'марка',
    accusative: 'марку',
    genitiveSingular: 'марки',
    genitivePlural: 'марок',
    nominativePlural: 'марки',
  },
  models: {
    singular: 'модель',
    accusative: 'модель',
    genitiveSingular: 'модели',
    genitivePlural: 'моделей',
    nominativePlural: 'модели',
  },
  model: {
    singular: 'модель',
    accusative: 'модель',
    genitiveSingular: 'модели',
    genitivePlural: 'моделей',
    nominativePlural: 'модели',
  },
  modifications: {
    singular: 'модификация',
    accusative: 'модификацию',
    genitiveSingular: 'модификации',
    genitivePlural: 'модификаций',
    nominativePlural: 'модификации',
  },
  modification: {
    singular: 'модификация',
    accusative: 'модификацию',
    genitiveSingular: 'модификации',
    genitivePlural: 'модификаций',
    nominativePlural: 'модификации',
  },
  trims: {
    singular: 'комплектация',
    accusative: 'комплектацию',
    genitiveSingular: 'комплектации',
    genitivePlural: 'комплектаций',
    nominativePlural: 'комплектации',
  },
  trim: {
    singular: 'комплектация',
    accusative: 'комплектацию',
    genitiveSingular: 'комплектации',
    genitivePlural: 'комплектаций',
    nominativePlural: 'комплектации',
  },
  categories: {
    singular: 'категория',
    accusative: 'категорию',
    genitiveSingular: 'категории',
    genitivePlural: 'категорий',
    nominativePlural: 'категории',
  },
  category: {
    singular: 'категория',
    accusative: 'категорию',
    genitiveSingular: 'категории',
    genitivePlural: 'категорий',
    nominativePlural: 'категории',
  },
  'attribute-groups': {
    singular: 'группа характеристик',
    accusative: 'группу характеристик',
    genitiveSingular: 'группы характеристик',
    genitivePlural: 'групп характеристик',
    nominativePlural: 'группы характеристик',
  },
  attribute_groups: {
    singular: 'группа характеристик',
    accusative: 'группу характеристик',
    genitiveSingular: 'группы характеристик',
    genitivePlural: 'групп характеристик',
    nominativePlural: 'группы характеристик',
  },
  attribute_group: {
    singular: 'группа характеристик',
    accusative: 'группу характеристик',
    genitiveSingular: 'группы характеристик',
    genitivePlural: 'групп характеристик',
    nominativePlural: 'группы характеристик',
  },
  'attribute-group': {
    singular: 'группа характеристик',
    accusative: 'группу характеристик',
    genitiveSingular: 'группы характеристик',
    genitivePlural: 'групп характеристик',
    nominativePlural: 'группы характеристик',
  },
  attributes: {
    singular: 'характеристика',
    accusative: 'характеристику',
    genitiveSingular: 'характеристики',
    genitivePlural: 'характеристик',
    nominativePlural: 'характеристики',
  },
  attribute: {
    singular: 'характеристика',
    accusative: 'характеристику',
    genitiveSingular: 'характеристики',
    genitivePlural: 'характеристик',
    nominativePlural: 'характеристики',
  },
  'attribute-options': {
    singular: 'вариант характеристики',
    accusative: 'вариант характеристики',
    genitiveSingular: 'варианта характеристики',
    genitivePlural: 'вариантов характеристик',
    nominativePlural: 'варианты характеристик',
  },
  attribute_options: {
    singular: 'вариант характеристики',
    accusative: 'вариант характеристики',
    genitiveSingular: 'варианта характеристики',
    genitivePlural: 'вариантов характеристик',
    nominativePlural: 'варианты характеристик',
  },
  attribute_option: {
    singular: 'вариант характеристики',
    accusative: 'вариант характеристики',
    genitiveSingular: 'варианта характеристики',
    genitivePlural: 'вариантов характеристик',
    nominativePlural: 'варианты характеристик',
  },
  options: {
    singular: 'вариант характеристики',
    accusative: 'вариант характеристики',
    genitiveSingular: 'варианта характеристики',
    genitivePlural: 'вариантов характеристик',
    nominativePlural: 'варианты характеристик',
  },
  option: {
    singular: 'вариант характеристики',
    accusative: 'вариант характеристики',
    genitiveSingular: 'варианта характеристики',
    genitivePlural: 'вариантов характеристик',
    nominativePlural: 'варианты характеристик',
  },
  colors: {
    singular: 'цвет',
    accusative: 'цвет',
    genitiveSingular: 'цвета',
    genitivePlural: 'цветов',
    nominativePlural: 'цвета',
  },
  color: {
    singular: 'цвет',
    accusative: 'цвет',
    genitiveSingular: 'цвета',
    genitivePlural: 'цветов',
    nominativePlural: 'цвета',
  },
  products: {
    singular: 'объявление',
    accusative: 'объявление',
    genitiveSingular: 'объявления',
    genitivePlural: 'объявлений',
    nominativePlural: 'объявления',
  },
  product: {
    singular: 'объявление',
    accusative: 'объявление',
    genitiveSingular: 'объявления',
    genitivePlural: 'объявлений',
    nominativePlural: 'объявления',
  },
}

export function getEntityForms(type: string): EntityPluralForms {
  const normalized = type.toLowerCase().trim()
  return (
    CATALOG_ENTITY_NAMES[normalized] ?? {
      singular: normalized,
      accusative: normalized,
      genitiveSingular: normalized,
      genitivePlural: normalized,
      nominativePlural: normalized,
    }
  )
}

export function getEntityAccusative(type: string): string {
  return getEntityForms(type).accusative
}

export function getEntityLabel(type: string, count?: number): string {
  const forms = getEntityForms(type)
  if (count === undefined) return forms.singular
  return pluralizeRussian(count, forms.singular, forms.genitiveSingular, forms.genitivePlural)
}

export function formatEntityCount(type: string, count: number): string {
  const forms = getEntityForms(type)
  return formatPlural(count, forms.singular, forms.genitiveSingular, forms.genitivePlural)
}
