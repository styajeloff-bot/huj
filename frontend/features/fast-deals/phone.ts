/** Client phone of a fast deal: exactly `+7` and ten digits (the backend pattern is `^\+7\d{10}$`). */
export const CLIENT_PHONE_PATTERN = /^\+7\d{10}$/

const NATIONAL_DIGITS = 10
const COUNTRY_PREFIX = '+7'

export const isValidClientPhone = (value: string): boolean => CLIENT_PHONE_PATTERN.test(value)

/**
 * Live mask `+7XXXXXXXXXX`. The `+7` prefix is fixed and always present in the result; a pasted
 * number may carry its own `+7`, `7` or `8` prefix, which is dropped. Returns at most ten digits
 * after the prefix. An input that holds only the prefix means «nothing entered yet».
 */
export function maskClientPhone(raw: string): string {
  let national = raw.replace(/\D+/g, '')
  if (raw.trimStart().startsWith(COUNTRY_PREFIX)) national = national.slice(1)
  if (national.length > NATIONAL_DIGITS && /^[78]/.test(national)) national = national.slice(1)
  return `${COUNTRY_PREFIX}${national.slice(0, NATIONAL_DIGITS)}`
}
