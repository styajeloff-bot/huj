/**
 * Formats a company phone for display only. Company API values remain unchanged.
 */
export function formatCompanyPhone(value: string): string {
  const digits = value.replace(/\D/g, '')
  const subscriberDigits = (digits.startsWith('7') || digits.startsWith('8') ? digits.slice(1) : digits).slice(0, 10)

  if (!subscriberDigits) return ''
  if (subscriberDigits.length <= 3) return `+7 (${subscriberDigits}`
  if (subscriberDigits.length <= 6) return `+7 (${subscriberDigits.slice(0, 3)}) ${subscriberDigits.slice(3)}`
  if (subscriberDigits.length <= 8) return `+7 (${subscriberDigits.slice(0, 3)}) ${subscriberDigits.slice(3, 6)}-${subscriberDigits.slice(6)}`

  return `+7 (${subscriberDigits.slice(0, 3)}) ${subscriberDigits.slice(3, 6)}-${subscriberDigits.slice(6, 8)}-${subscriberDigits.slice(8)}`
}
