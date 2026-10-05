export interface CatalogIntegerBounds {
  min?: number
  max?: number
}

export const normalizeCatalogInteger = (
  value: unknown,
  { min = 0, max = Number.MAX_SAFE_INTEGER }: CatalogIntegerBounds = {},
): number | null => {
  const normalized = typeof value === 'string' ? value.trim() : value
  if (typeof normalized === 'string' && !/^\d+$/.test(normalized)) return null
  if (typeof normalized !== 'string' && typeof normalized !== 'number') return null
  const parsed = typeof normalized === 'number' ? normalized : Number(normalized)
  return Number.isSafeInteger(parsed) && parsed >= min && parsed <= max ? parsed : null
}
