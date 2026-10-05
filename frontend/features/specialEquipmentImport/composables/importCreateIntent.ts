import type { SpecialEquipmentImportCreateRequest } from '../types'

const CREATE_INTENT_KEY = 'carcraft:special-equipment:import-create-intent:v2'

export interface ImportCreateFileIdentity {
  name: string
  size: number
  lastModified: number
}

export interface ImportCreateIntentStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

type ImportCreateModePayload = Omit<SpecialEquipmentImportCreateRequest, 'filename' | 'size'>

interface PersistedCreateIntent {
  version: 1
  fingerprint: string
  idempotencyKey: string
}

const createIdempotencyKey = (): string => {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
}

const createFingerprint = async (
  file: ImportCreateFileIdentity,
  payload: ImportCreateModePayload,
): Promise<string> => {
  const canonicalIntent = JSON.stringify([
    file.name,
    file.size,
    file.lastModified,
    payload.mode,
    payload.templateVersion,
  ])
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(canonicalIntent),
  )
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

const readCreateIntent = (
  storage: ImportCreateIntentStorage,
): PersistedCreateIntent | null => {
  try {
    const raw: unknown = JSON.parse(storage.getItem(CREATE_INTENT_KEY) ?? 'null')
    if (!raw || typeof raw !== 'object') return null
    const value = raw as Record<string, unknown>
    if (
      value.version !== 1
      || typeof value.fingerprint !== 'string'
      || !/^[a-f0-9]{64}$/.test(value.fingerprint)
      || typeof value.idempotencyKey !== 'string'
      || value.idempotencyKey.length < 8
    ) return null
    return {
      version: 1,
      fingerprint: value.fingerprint,
      idempotencyKey: value.idempotencyKey,
    }
  } catch {
    return null
  }
}

/** Persist and reuse an idempotency key for one exact file/create intent. */
export const acquireImportCreateIdempotencyKey = async (
  storage: ImportCreateIntentStorage,
  file: ImportCreateFileIdentity,
  payload: ImportCreateModePayload,
): Promise<string> => {
  const fingerprint = await createFingerprint(file, payload)
  const persisted = readCreateIntent(storage)
  if (persisted?.fingerprint === fingerprint) return persisted.idempotencyKey

  const idempotencyKey = createIdempotencyKey()
  const next: PersistedCreateIntent = { version: 1, fingerprint, idempotencyKey }
  storage.setItem(CREATE_INTENT_KEY, JSON.stringify(next))
  return idempotencyKey
}

export const clearImportCreateIntent = (storage: ImportCreateIntentStorage): void => {
  storage.removeItem(CREATE_INTENT_KEY)
}
