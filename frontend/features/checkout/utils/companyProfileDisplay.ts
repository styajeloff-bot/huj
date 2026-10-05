export interface CompanyFounderDisplay {
  name: string
  inn: string
  share: string
  needsPassport: boolean
}

type UnknownRecord = Record<string, unknown>

const FOUNDER_COLLECTION_KEYS = ['founders', 'items', 'data', 'values', 'result'] as const
const FOUNDER_MARKER_KEYS = [
  'name',
  'full_name',
  'fio',
  'surname',
  'first_name',
  'inn',
  'share',
  'share_percentage',
  'percent',
] as const

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function decodeJsonValue(value: unknown): unknown {
  let current = value

  for (let i = 0; i < 2; i += 1) {
    if (typeof current !== 'string') return current

    const trimmed = current.trim()
    if (!trimmed) return null
    if (!['[', '{', '"'].includes(trimmed[0])) return current

    try {
      current = JSON.parse(trimmed)
    } catch {
      return current
    }
  }

  return current
}

function extractFounderRecords(value: unknown): UnknownRecord[] {
  const decoded = decodeJsonValue(value)

  if (Array.isArray(decoded)) {
    return decoded.filter(isRecord)
  }

  if (!isRecord(decoded)) return []

  for (const key of FOUNDER_COLLECTION_KEYS) {
    const nested = extractFounderRecords(decoded[key])
    if (nested.length > 0) return nested
  }

  if (FOUNDER_MARKER_KEYS.some((key) => decoded[key] !== undefined)) return [decoded]

  const recordValues = Object.values(decoded).filter(isRecord)
  if (recordValues.some((record) => FOUNDER_MARKER_KEYS.some((key) => record[key] !== undefined))) {
    return recordValues
  }

  return []
}

function firstString(record: UnknownRecord, keys: string[]): string {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return ''
}

function founderName(record: UnknownRecord): string {
  const direct = firstString(record, ['name', 'full_name', 'fio'])
  if (direct) return direct

  return [
    firstString(record, ['surname', 'last_name']),
    firstString(record, ['first_name', 'name_first']),
    firstString(record, ['patronymic', 'middle_name']),
  ].filter(Boolean).join(' ')
}

function shareRawValue(record: UnknownRecord): unknown {
  for (const key of ['share', 'share_percentage', 'percent', 'share_percent', 'ownership_percent']) {
    const value = record[key]
    if (value !== null && value !== undefined && value !== '') return value
  }
  return null
}

function parseShareNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null

  if (typeof value === 'string') {
    const normalized = value.replace('%', '').replace(',', '.').trim()
    if (!normalized) return null
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  }

  if (isRecord(value)) {
    const direct = parseShareNumber(value.value ?? value.percent ?? value.percentage)
    if (direct !== null) return direct

    const numerator = parseShareNumber(value.numerator)
    const denominator = parseShareNumber(value.denominator)
    if (numerator !== null && denominator !== null && denominator !== 0) {
      return (numerator / denominator) * 100
    }
  }

  return null
}

function formatShare(value: unknown): string {
  const parsed = parseShareNumber(value)
  if (parsed === null) return ''

  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 4,
  }).format(parsed)
}

export function normalizeCompanyFounders(
  rawFounders: unknown,
  directorInn: string | null | undefined,
): CompanyFounderDisplay[] {
  const normalizedDirectorInn = (directorInn || '').trim()

  return extractFounderRecords(rawFounders)
    .map((record) => {
      const inn = firstString(record, ['inn'])
      const rawShare = shareRawValue(record)
      const shareValue = parseShareNumber(rawShare)
      const isNotDirector = !normalizedDirectorInn || inn !== normalizedDirectorInn

      return {
        name: founderName(record),
        inn,
        share: formatShare(rawShare),
        needsPassport: inn.length === 12 && (shareValue ?? 0) >= 25 && isNotDirector,
      }
    })
    .filter((founder) => founder.name || founder.inn || founder.share)
}

export function resolveCompanyRegistrationDate(
  companyData: UnknownRecord | null | undefined,
  orgInfo: UnknownRecord | null | undefined,
): string | null {
  return firstString(companyData || {}, ['registration_date', 'registrationDate', 'registered_at'])
    || firstString(orgInfo || {}, ['registration_date', 'registrationDate', 'registered_at'])
    || null
}
