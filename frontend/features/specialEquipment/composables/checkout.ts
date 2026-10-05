import type { SpecialEquipmentProblemDetails } from '../types'

interface FetchFailure {
  status?: number
  statusCode?: number
  response?: { status?: number }
  data?: (SpecialEquipmentProblemDetails & { message?: string }) | { detail?: string; message?: string }
  message?: string
}

export const specialEquipmentFailureStatus = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined
  const failure = error as FetchFailure
  return failure.statusCode ?? failure.status ?? failure.response?.status
}

export const specialEquipmentFailureMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== 'object') return fallback
  const failure = error as FetchFailure
  return failure.data?.detail ?? failure.data?.message ?? failure.message ?? fallback
}

const randomIdempotencyKey = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export const getSpecialEquipmentIdempotencyKey = (operationKey: string): string => {
  if (!import.meta.client) return `server-${operationKey}`
  const storageKey = `carcraft:special-equipment:idempotency:${operationKey}`
  const existing = sessionStorage.getItem(storageKey)
  if (existing) return existing
  const created = randomIdempotencyKey()
  sessionStorage.setItem(storageKey, created)
  return created
}

export const clearSpecialEquipmentIdempotencyKey = (operationKey: string) => {
  if (!import.meta.client) return
  sessionStorage.removeItem(`carcraft:special-equipment:idempotency:${operationKey}`)
}
