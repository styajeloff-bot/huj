import type { SpecialEquipmentSort, SpecialEquipmentUsageMetric } from './types'

export interface SpecialEquipmentSortOption {
  value: SpecialEquipmentSort
  label: string
}

const GENERAL_OPTIONS: SpecialEquipmentSortOption[] = [
  { value: 'published_desc', label: 'Сначала новые' },
  { value: 'published_asc', label: 'Сначала старые' },
  { value: 'price_asc', label: 'Сначала дешевле' },
  { value: 'price_desc', label: 'Сначала дороже' },
  { value: 'name_asc', label: 'По названию' },
]

const USAGE_OPTIONS: Record<SpecialEquipmentUsageMetric, SpecialEquipmentSortOption[]> = {
  mileage_km: [
    { value: 'mileage_asc', label: 'Пробег: по возрастанию' },
    { value: 'mileage_desc', label: 'Пробег: по убыванию' },
  ],
  engine_hours: [
    { value: 'engine_hours_asc', label: 'Моточасы: по возрастанию' },
    { value: 'engine_hours_desc', label: 'Моточасы: по убыванию' },
  ],
}

export const specialEquipmentSortOptions = (
  usageMetric: SpecialEquipmentUsageMetric | null,
): SpecialEquipmentSortOption[] => [
  ...GENERAL_OPTIONS,
  ...(usageMetric ? USAGE_OPTIONS[usageMetric] : [
    ...USAGE_OPTIONS.mileage_km,
    ...USAGE_OPTIONS.engine_hours,
  ]),
]

export const isSpecialEquipmentSortAvailable = (
  sort: SpecialEquipmentSort,
  usageMetric: SpecialEquipmentUsageMetric | null,
): boolean => specialEquipmentSortOptions(usageMetric).some(option => option.value === sort)
