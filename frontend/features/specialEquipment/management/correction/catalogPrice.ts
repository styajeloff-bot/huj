const CATALOG_PRICE_PATTERN = /^\d+(?:\.\d{1,2})?$/

export const normalizeCatalogPrice = (value: unknown): string | null => {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  if (!CATALOG_PRICE_PATTERN.test(normalized)) return null
  const digitCount = normalized.replace('.', '').replace(/^0+/, '').length
  return digitCount <= 15 ? normalized : null
}

export const isPositiveCatalogPrice = (value: unknown): boolean => {
  const normalized = normalizeCatalogPrice(value)
  return normalized !== null && /[1-9]/.test(normalized)
}
