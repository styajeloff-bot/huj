export interface PurposeRegionVehicleLike {
  leasing_purpose?: unknown
  leasing_purpose_comment?: unknown
  region?: unknown
  regions?: unknown
  leasing_regions?: unknown
  region_names?: unknown
  leasing_region_names?: unknown
}

export interface ApplicationVehicleTitleLike {
  mark_name?: unknown
  mark_cyrillic_name?: unknown
  mark?: unknown
  brand?: unknown
  model_name?: unknown
  model_cyrillic_name?: unknown
  model?: unknown
  name?: unknown
  quantity?: unknown
}

const PURPOSE_LABELS: Record<string, string> = {
  business: 'Для предпринимательской деятельности',
  personal: 'Личное пользование',
  management: 'Для руководства',
  staff: 'Для служебных поездок',
  taxi: 'Для такси',
  carsharing: 'Каршеринг',
  special_equipment: 'Для операционной деятельности (спец. техника)',
  test_drive: 'Для тест-драйва',
  other: 'Прочее',
}

const hasValue = (value: unknown): value is string | number | boolean => {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  return true
}

const stringifyValue = (value: unknown): string => {
  if (!hasValue(value)) return ''
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    return String(
      record.region_label
      || record.region_display_name
      || record.display_name
      || record.name
      || record.title
      || record.label
      || '',
    ).trim()
  }
  return String(value).trim()
}

const appendRegionValue = (values: string[], value: unknown) => {
  if (Array.isArray(value)) {
    for (const item of value) appendRegionValue(values, item)
    return
  }

  if (typeof value === 'string' && value.includes(',')) {
    for (const item of value.split(',')) appendRegionValue(values, item)
    return
  }

  const label = stringifyValue(value)
  if (label && !values.includes(label)) values.push(label)
}

export const getVehicleRegionLabels = (vehicle: PurposeRegionVehicleLike): string[] => {
  const values: string[] = []

  appendRegionValue(values, vehicle.region)
  appendRegionValue(values, vehicle.regions)
  appendRegionValue(values, vehicle.leasing_regions)
  appendRegionValue(values, vehicle.region_names)
  appendRegionValue(values, vehicle.leasing_region_names)

  return values
}

export const formatLeasingPurpose = (vehicle: PurposeRegionVehicleLike, emptyLabel = 'Не указано'): string => {
  const rawPurpose = stringifyValue(vehicle.leasing_purpose)
  const comment = stringifyValue(vehicle.leasing_purpose_comment)

  if (!rawPurpose) return emptyLabel

  if (rawPurpose === 'other') {
    return comment ? `Прочее: ${comment}` : PURPOSE_LABELS.other
  }

  return PURPOSE_LABELS[rawPurpose] || rawPurpose
}

export const formatVehicleRegions = (vehicle: PurposeRegionVehicleLike, emptyLabel = 'Не указано'): string => {
  const values = getVehicleRegionLabels(vehicle)
  return values.length ? values.join(', ') : emptyLabel
}

export const hasPurposeOrRegion = (vehicle: PurposeRegionVehicleLike): boolean => {
  return formatLeasingPurpose(vehicle, '') !== '' || formatVehicleRegions(vehicle, '') !== ''
}

export const formatApplicationVehicleTitle = (
  vehicle: ApplicationVehicleTitleLike,
  emptyLabel = 'Автомобиль',
  includeQuantity = true,
): string => {
  const mark = stringifyValue(vehicle.mark_name)
    || stringifyValue(vehicle.mark)
    || stringifyValue(vehicle.brand)
    || stringifyValue(vehicle.mark_cyrillic_name)
  const model = stringifyValue(vehicle.model_name)
    || stringifyValue(vehicle.model)
    || stringifyValue(vehicle.model_cyrillic_name)
  const title = [mark, model].filter(Boolean).join(' ') || stringifyValue(vehicle.name) || emptyLabel
  const quantity = Number(vehicle.quantity)

  return includeQuantity && Number.isFinite(quantity) && quantity > 1 ? `${title} x ${quantity}` : title
}
