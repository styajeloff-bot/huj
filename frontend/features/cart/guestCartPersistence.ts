import { isUuid, type UUID } from '../../types/ids'

export type GuestCartRecord = Record<string, unknown>

export interface ValidGuestCartEntry {
  index: number
  raw: GuestCartRecord
  vehicleId: UUID
  transferId?: UUID
}

export interface PreparedGuestCartEntry extends ValidGuestCartEntry {
  transferId: UUID
}

export interface GuestCartSnapshot {
  entries: unknown[]
  validEntries: ValidGuestCartEntry[]
  invalidEntries: unknown[]
  malformed: boolean
}

export interface GuestCartTransferFailure {
  entry: PreparedGuestCartEntry
  error: unknown
}

export interface GuestCartTransferResult {
  remainingEntries: unknown[]
  failures: GuestCartTransferFailure[]
}

export interface GuestCartTransferSteps {
  transferCartEntry: (entry: PreparedGuestCartEntry) => Promise<void>
  persistRemaining: (entries: unknown[]) => void | Promise<void>
  createTransferId?: () => UUID
}

export type GuestCartTransferOptionCodeKey = 'equipment_code' | 'service_code'

export type GuestCartTransferOption<CodeKey extends GuestCartTransferOptionCodeKey> =
  Record<CodeKey, string> & { price?: number }

const isRecord = (value: unknown): value is GuestCartRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

export const normalizeGuestCartTransferOptions = <
  CodeKey extends GuestCartTransferOptionCodeKey,
>(
  value: unknown,
  codeKey: CodeKey,
): Array<GuestCartTransferOption<CodeKey>> => {
  if (!Array.isArray(value)) return []

  return value.flatMap((option) => {
    if (!isRecord(option) || typeof option[codeKey] !== 'string') return []

    const normalized = {
      [codeKey]: option[codeKey],
    } as GuestCartTransferOption<CodeKey>
    if (typeof option.price === 'number' && Number.isFinite(option.price)) {
      normalized.price = option.price
    }
    return [normalized]
  })
}

export const createSingleFlight = <T>(task: () => Promise<T>): (() => Promise<T>) => {
  let active: Promise<T> | null = null

  return () => {
    if (active) return active

    active = task().finally(() => {
      active = null
    })
    return active
  }
}

export const parseGuestCartStorage = (serialized: string | null): GuestCartSnapshot => {
  if (!serialized) {
    return { entries: [], validEntries: [], invalidEntries: [], malformed: false }
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(serialized)
  } catch {
    return { entries: [], validEntries: [], invalidEntries: [], malformed: true }
  }

  if (!Array.isArray(parsed)) {
    return { entries: [], validEntries: [], invalidEntries: [], malformed: true }
  }

  const validEntries: ValidGuestCartEntry[] = []
  const invalidEntries: unknown[] = []

  parsed.forEach((raw, index) => {
    if (
      !isRecord(raw)
      || !isUuid(raw.vehicle_id)
      || (raw.transfer_id !== undefined && !isUuid(raw.transfer_id))
    ) {
      invalidEntries.push(raw)
      return
    }

    validEntries.push({
      index,
      raw,
      vehicleId: raw.vehicle_id,
      transferId: raw.transfer_id,
    })
  })

  return {
    entries: parsed,
    validEntries,
    invalidEntries,
    malformed: false,
  }
}

export const entriesForGuestCartSave = (
  currentEntries: readonly unknown[],
  serialized: string | null,
): unknown[] => {
  const snapshot = parseGuestCartStorage(serialized)
  return snapshot.malformed
    ? [...currentEntries]
    : [...currentEntries, ...snapshot.invalidEntries]
}

const prepareTransferEntry = (
  entry: ValidGuestCartEntry,
  createTransferId: () => UUID,
): PreparedGuestCartEntry => {
  const transferId = entry.transferId ?? createTransferId()
  const {
    _guest_cart_transfer_stage: _legacyStage,
    _guest_cart_transfer_user_id: _legacyUserId,
    ...raw
  } = entry.raw

  return {
    ...entry,
    raw: { ...raw, transfer_id: transferId },
    transferId,
  }
}

export const transferGuestCartEntries = async (
  snapshot: GuestCartSnapshot,
  steps: GuestCartTransferSteps,
): Promise<GuestCartTransferResult> => {
  const createTransferId = steps.createTransferId ?? (() => crypto.randomUUID())
  const preparedEntries = snapshot.validEntries.map(entry =>
    prepareTransferEntry(entry, createTransferId),
  )
  let remaining = snapshot.entries.map((raw, index) => ({ index, raw }))
  let mustPersistPreparedEntries = false

  for (const entry of preparedEntries) {
    const original = snapshot.validEntries.find(item => item.index === entry.index)
    if (
      original?.transferId === undefined
      || (original && '_guest_cart_transfer_stage' in original.raw)
      || (original && '_guest_cart_transfer_user_id' in original.raw)
    ) {
      mustPersistPreparedEntries = true
    }
    remaining = remaining.map(item =>
      item.index === entry.index ? { ...item, raw: entry.raw } : item,
    )
  }

  if (mustPersistPreparedEntries) {
    await steps.persistRemaining(remaining.map(item => item.raw))
  }

  const failures: GuestCartTransferFailure[] = []
  for (const entry of preparedEntries) {
    try {
      await steps.transferCartEntry(entry)
      const nextRemaining = remaining.filter(item => item.index !== entry.index)
      await steps.persistRemaining(nextRemaining.map(item => item.raw))
      remaining = nextRemaining
    } catch (error) {
      failures.push({ entry, error })
    }
  }

  return {
    remainingEntries: remaining.map(item => item.raw),
    failures,
  }
}
