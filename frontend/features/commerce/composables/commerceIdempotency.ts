const randomIdempotencyKey = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16)
    crypto.getRandomValues(bytes)
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  }
  return `commerce-${Date.now().toString(36)}`
}

const storageKey = (operationKey: string): string =>
  `carcraft:commerce:idempotency:${operationKey}`

export const getCommerceIdempotencyKey = (operationKey: string): string => {
  if (!import.meta.client) return randomIdempotencyKey()
  const key = storageKey(operationKey)
  const existing = sessionStorage.getItem(key)
  if (existing) return existing
  const created = randomIdempotencyKey()
  sessionStorage.setItem(key, created)
  return created
}

export const clearCommerceIdempotencyKey = (operationKey: string): void => {
  if (!import.meta.client) return
  sessionStorage.removeItem(storageKey(operationKey))
}
