import { normalizeCatalogInteger } from './catalogInteger'

export const CATALOG_YEAR_MIN = 1900
export const CATALOG_YEAR_MAX = 2200

export const catalogYearDraft = (value: unknown): string => {
  if (typeof value === 'number' && Number.isSafeInteger(value)) return String(value)
  return typeof value === 'string' ? value : ''
}

export const catalogYearDraftError = (value: unknown): string => {
  const draft = catalogYearDraft(value).trim()
  if (!draft) return ''
  if (!/^\d+$/.test(draft)) return 'Введите год целым числом.'
  if (normalizeCatalogInteger(draft, {
    min: CATALOG_YEAR_MIN,
    max: CATALOG_YEAR_MAX,
  }) === null) return `Введите год от ${CATALOG_YEAR_MIN} до ${CATALOG_YEAR_MAX}.`
  return ''
}

export const stepCatalogYearDraft = (value: unknown, direction: -1 | 1): string => {
  const normalized = normalizeCatalogInteger(catalogYearDraft(value), {
    min: CATALOG_YEAR_MIN,
    max: CATALOG_YEAR_MAX,
  })
  const start = normalized ?? (direction === 1 ? CATALOG_YEAR_MIN - 1 : CATALOG_YEAR_MAX + 1)
  return String(Math.min(CATALOG_YEAR_MAX, Math.max(CATALOG_YEAR_MIN, start + direction)))
}
