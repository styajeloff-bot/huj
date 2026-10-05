export type AdditionalOptionPrice = string | number | null

const GROUP_SEPARATOR_PATTERN = /[\s\u00a0\u202f]/g
const UNSIGNED_DECIMAL_PATTERN = /^(\d+)(?:[.,](\d+))?$/

/**
 * Keeps the API value unformatted while accepting the grouped representation
 * shown by the editor. A string is intentional: converting a large price via
 * Number would lose integer precision before the PATCH request is sent.
 */
export const normalizeAdditionalOptionPriceInput = (value: string): string | null => {
  const compact = value.replace(GROUP_SEPARATOR_PATTERN, '')
  if (!compact) return null
  const match = compact.match(UNSIGNED_DECIMAL_PATTERN)
  if (!match) return null
  return match[2] === undefined ? match[1] : `${match[1]}.${match[2]}`
}

export const formatAdditionalOptionPriceInput = (
  value: AdditionalOptionPrice | undefined,
): string => {
  if (value === null || value === undefined || value === '') return ''
  const compact = String(value).replace(GROUP_SEPARATOR_PATTERN, '')
  const match = compact.match(UNSIGNED_DECIMAL_PATTERN)
  if (!match) return String(value)
  const integer = match[1].replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  return match[2] === undefined ? integer : `${integer},${match[2]}`
}
