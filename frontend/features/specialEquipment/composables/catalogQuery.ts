import type { LocationQuery, LocationQueryRaw } from 'vue-router'
import { isUuid, type UUID } from '~/types/ids'
import type {
  SpecialEquipmentCatalogQuery,
  SpecialEquipmentCondition,
  SpecialEquipmentDynamicFilters,
  SpecialEquipmentSort,
  SpecialEquipmentTrimFacet,
  SpecialEquipmentUsageMetric,
} from '../types'
import type {
  SpecialEquipmentFacetsParams,
  SpecialEquipmentProductsParams,
} from '../api/specialEquipmentApi'

export const SPECIAL_EQUIPMENT_PAGE_SIZE = 24

const SORT_VALUES = new Set<SpecialEquipmentSort>([
  'published_desc',
  'published_asc',
  'price_asc',
  'price_desc',
  'name_asc',
  'mileage_asc',
  'mileage_desc',
  'engine_hours_asc',
  'engine_hours_desc',
])
const CONDITION_VALUES = new Set<SpecialEquipmentCondition>(['', 'new', 'used'])
const AVAILABILITY_VALUES = ['available', 'on_order'] as const
const AVAILABILITY_VALUE_SET = new Set(AVAILABILITY_VALUES)

const queryValues = (value: LocationQuery[string]): string[] => {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string' && item.length > 0)
  }
  return typeof value === 'string' && value.length > 0 ? [value] : []
}

const firstQueryValue = (value: LocationQuery[string]): string => queryValues(value)[0] ?? ''

const positivePage = (value: string): number => {
  const parsed = Number.parseInt(value, 10)
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1
}

const cleanAmount = (value: string): string => {
  const normalized = value.trim().replace(',', '.')
  return /^\d+(?:\.\d{0,2})?$/.test(normalized) ? normalized : ''
}

const cleanUsage = (value: string): string => {
  const normalized = value.trim()
  return /^\d+$/.test(normalized) ? normalized : ''
}

const cleanStockCount = (value = ''): string => {
  const normalized = value.trim()
  return /^(?:0|[1-9]\d*)$/.test(normalized) && Number(normalized) <= 100_000
    ? normalized
    : ''
}

export const parseSpecialEquipmentCatalogQuery = (
  query: LocationQuery,
): SpecialEquipmentCatalogQuery => {
  const sortCandidate = firstQueryValue(query.sort) as SpecialEquipmentSort
  const conditionCandidate = firstQueryValue(query.condition) as SpecialEquipmentCondition
  const availability = queryValues(query.availability)
    .filter((value): value is 'available' | 'on_order' =>
      AVAILABILITY_VALUE_SET.has(value as 'available' | 'on_order'))

  return {
    markIds: queryValues(query.mark_id).filter(isUuid),
    modelIds: queryValues(query.model_id).filter(isUuid),
    modificationIds: queryValues(query.modification_id).filter(isUuid),
    trimIds: queryValues(query.trim_id).filter(isUuid),
    superstructureIds: queryValues(query.superstructure_id).filter(isUuid),
    bodyColorIds: queryValues(query.body_color_id).filter(isUuid),
    interiorColorIds: queryValues(query.interior_color_id).filter(isUuid),
    availability: availability.length > 0 ? availability : [...AVAILABILITY_VALUES],
    condition: CONDITION_VALUES.has(conditionCandidate) ? conditionCandidate : '',
    priceMin: cleanAmount(firstQueryValue(query.price_min)),
    priceMax: cleanAmount(firstQueryValue(query.price_max)),
    usageMin: cleanUsage(firstQueryValue(query.usage_min)),
    usageMax: cleanUsage(firstQueryValue(query.usage_max)),
    cityId: isUuid(firstQueryValue(query.city_id)) ? firstQueryValue(query.city_id) : '',
    warehouseId: isUuid(firstQueryValue(query.warehouse_id)) ? firstQueryValue(query.warehouse_id) : '',
    minInStock: cleanStockCount(firstQueryValue(query.min_in_stock)),
    search: firstQueryValue(query.search).trim().slice(0, 200),
    descriptionInclude: firstQueryValue(query.description_include).trim().slice(0, 500),
    descriptionExclude: firstQueryValue(query.description_exclude).trim().slice(0, 500),
    sort: SORT_VALUES.has(sortCandidate) ? sortCandidate : 'published_desc',
    page: positivePage(firstQueryValue(query.page)),
    attributeTokens: queryValues(query.attribute),
  }
}

/**
 * Keep only trims that belong to the selected modifications.
 * Missing facets cannot prove ownership, so keep their selected trims until known.
 */
export const pruneTrimSelection = (
  query: SpecialEquipmentCatalogQuery,
  trimFacets: readonly SpecialEquipmentTrimFacet[],
): SpecialEquipmentCatalogQuery => {
  if (query.trimIds.length === 0) return query
  if (query.modificationIds.length === 0) return { ...query, trimIds: [] }
  const selected = new Set(query.modificationIds)
  const owner = new Map(trimFacets.map(trim => [trim.id, trim.modification_id]))
  const trimIds = query.trimIds.filter((id) => {
    const modificationId = owner.get(id)
    return modificationId === undefined || selected.has(modificationId)
  })
  return trimIds.length === query.trimIds.length ? query : { ...query, trimIds }
}

export const toggleSpecialEquipmentAvailability = (
  selectedAvailability: SpecialEquipmentCatalogQuery['availability'],
  availability: SpecialEquipmentCatalogQuery['availability'][number],
): SpecialEquipmentCatalogQuery['availability'] => {
  const selected = new Set(selectedAvailability)
  if (selected.has(availability)) selected.delete(availability)
  else selected.add(availability)
  if (selected.size === 0) return [...AVAILABILITY_VALUES]
  return AVAILABILITY_VALUES.filter(value => selected.has(value))
}

export const hasExplicitSpecialEquipmentAvailability = (
  availability: SpecialEquipmentCatalogQuery['availability'],
): boolean => availability.length === 1

export const serializeSpecialEquipmentCatalogQuery = (
  state: SpecialEquipmentCatalogQuery,
): LocationQueryRaw => {
  const query: LocationQueryRaw = {}

  if (state.markIds.length > 0) query.mark_id = state.markIds
  if (state.modelIds.length > 0) query.model_id = state.modelIds
  if (state.modificationIds.length > 0) query.modification_id = state.modificationIds
  if (state.trimIds.length > 0) query.trim_id = state.trimIds
  if (state.superstructureIds && state.superstructureIds.length > 0) query.superstructure_id = state.superstructureIds
  if (state.bodyColorIds.length > 0) query.body_color_id = state.bodyColorIds
  if (state.interiorColorIds.length > 0) query.interior_color_id = state.interiorColorIds
  if (state.availability.length > 0) query.availability = state.availability
  if (state.condition) query.condition = state.condition
  if (state.priceMin) query.price_min = state.priceMin
  if (state.priceMax) query.price_max = state.priceMax
  const usageMin = cleanUsage(state.usageMin)
  const usageMax = cleanUsage(state.usageMax)
  if (state.condition === 'used' && usageMin) query.usage_min = usageMin
  if (state.condition === 'used' && usageMax) query.usage_max = usageMax
  if (state.cityId) query.city_id = state.cityId
  if (state.warehouseId) query.warehouse_id = state.warehouseId
  const minInStock = cleanStockCount(state.minInStock)
  if (minInStock) query.min_in_stock = minInStock
  if (state.search) query.search = state.search
  if (state.descriptionInclude) query.description_include = state.descriptionInclude
  if (state.descriptionExclude) query.description_exclude = state.descriptionExclude
  if (state.sort !== 'published_desc') query.sort = state.sort
  if (state.page > 1) query.page = String(state.page)
  if (state.attributeTokens.length > 0) query.attribute = state.attributeTokens

  return query
}

export const toSpecialEquipmentProductsParams = (
  state: SpecialEquipmentCatalogQuery,
  categoryPath: string[] = [],
  usageMetric: SpecialEquipmentUsageMetric | null = null,
): SpecialEquipmentProductsParams => {
  const usageMin = cleanUsage(state.usageMin)
  const usageMax = cleanUsage(state.usageMax)
  return {
    category_path: categoryPath.length > 0 ? categoryPath.join('/') : undefined,
    mark_id: state.markIds.length > 0 ? state.markIds : undefined,
    model_id: state.modelIds.length > 0 ? state.modelIds : undefined,
    modification_id: state.modificationIds.length > 0 ? state.modificationIds : undefined,
    trim_id: state.trimIds.length > 0 ? state.trimIds : undefined,
    superstructure_id: state.superstructureIds && state.superstructureIds.length > 0 ? state.superstructureIds : undefined,
    body_color_id: state.bodyColorIds.length > 0 ? state.bodyColorIds : undefined,
    interior_color_id: state.interiorColorIds.length > 0 ? state.interiorColorIds : undefined,
    availability: state.availability.length > 0 ? state.availability : undefined,
    condition: state.condition || undefined,
    price_min: state.priceMin || undefined,
    price_max: state.priceMax || undefined,
    mileage_min: state.condition === 'used' && usageMetric === 'mileage_km' ? usageMin || undefined : undefined,
    mileage_max: state.condition === 'used' && usageMetric === 'mileage_km' ? usageMax || undefined : undefined,
    engine_hours_min: state.condition === 'used' && usageMetric === 'engine_hours' ? usageMin || undefined : undefined,
    engine_hours_max: state.condition === 'used' && usageMetric === 'engine_hours' ? usageMax || undefined : undefined,
    city_id: state.cityId || undefined,
    warehouse_id: state.warehouseId || undefined,
    min_in_stock: cleanStockCount(state.minInStock) || undefined,
    search: state.search || undefined,
    description_include: state.descriptionInclude || undefined,
    description_exclude: state.descriptionExclude || undefined,
    sort: state.sort,
    page: state.page,
    page_size: SPECIAL_EQUIPMENT_PAGE_SIZE,
    attribute: state.attributeTokens.length > 0 ? state.attributeTokens : undefined,
  }
}

export const toSpecialEquipmentFacetsParams = (
  state: SpecialEquipmentCatalogQuery,
  categoryPath: string[] = [],
  usageMetric: SpecialEquipmentUsageMetric | null = null,
): SpecialEquipmentFacetsParams => {
  const { sort: _sort, page: _page, page_size: _pageSize, ...params } =
    toSpecialEquipmentProductsParams(state, categoryPath, usageMetric)
  return params
}

export const resetSpecialEquipmentCategorySpecificFilters = (
  state: SpecialEquipmentCatalogQuery,
): SpecialEquipmentCatalogQuery => ({
  ...state,
  page: 1,
  attributeTokens: [],
  usageMin: '',
  usageMax: '',
})

export const hasSpecialEquipmentCategoryFilterContext = (
  categoryPath: readonly string[],
  modificationIds: readonly UUID[],
  implicitUsageMetric: SpecialEquipmentUsageMetric | null,
): boolean => categoryPath.length > 0
  || (modificationIds.length === 1 && implicitUsageMetric !== null)

export const catalogQueryForCategoryContext = (
  state: SpecialEquipmentCatalogQuery,
  hasCategoryContext: boolean,
): SpecialEquipmentCatalogQuery => hasCategoryContext
  ? state
  : {
      ...state,
      attributeTokens: [],
      usageMin: '',
      usageMax: '',
    }

interface ParsedAttributeToken {
  attributeId: UUID
  operator: 'eq' | 'gte' | 'lte' | 'search'
  value: string
}

const parseAttributeToken = (token: string): ParsedAttributeToken | null => {
  const parts = token.split(':')
  const attributeId = parts[0]
  if (!isUuid(attributeId)) return null

  const operator = parts[1]
  if (operator !== 'eq' && operator !== 'gte' && operator !== 'lte' && operator !== 'search') return null

  const value = parts.slice(2).join(':').trim()
  return value ? { attributeId, operator, value } : null
}

export const parseDynamicFilters = (tokens: string[]): SpecialEquipmentDynamicFilters => {
  const filters: SpecialEquipmentDynamicFilters = {}

  for (const rawToken of tokens) {
    const token = parseAttributeToken(rawToken)
    if (!token) continue

    const current = filters[token.attributeId] ?? { values: [], min: '', max: '', search: '' }
    if (token.operator === 'eq' && !current.values.includes(token.value)) {
      current.values.push(token.value)
    } else if (token.operator === 'gte') {
      current.min = token.value
    } else if (token.operator === 'lte') {
      current.max = token.value
    } else if (token.operator === 'search') {
      current.search = token.value
    }
    filters[token.attributeId] = current
  }

  return filters
}

export const serializeDynamicFilters = (
  filters: SpecialEquipmentDynamicFilters,
): string[] => Object.entries(filters).flatMap(([attributeId, filter]) => {
  if (!isUuid(attributeId)) return []
  const exact = filter.values.map((value) => `${attributeId}:eq:${value}`)
  const min = filter.min ? [`${attributeId}:gte:${filter.min}`] : []
  const max = filter.max ? [`${attributeId}:lte:${filter.max}`] : []
  const search = filter.search?.trim()
    ? [`${attributeId}:search:${filter.search.trim().slice(0, 200)}`]
    : []
  return [...exact, ...min, ...max, ...search]
})
