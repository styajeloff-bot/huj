import type { CommerceMoney, CommercePurchaseLine } from './types'

const DECIMAL_PATTERN = /^(-?)(\d+)(?:[.,](\d{1,2}))?$/
const BIGINT_ZERO = BigInt(0)
const BIGINT_ONE = BigInt(1)
const BASIS_POINTS_SCALE = BigInt(100)
const PERCENT_DENOMINATOR = BigInt(10000)
const ROUNDING_HALF = BigInt(5000)

interface MinorAmount {
  value: bigint
  scale: number
}

const toMinorAmount = (raw: CommerceMoney): MinorAmount | null => {
  const match = raw.trim().match(DECIMAL_PATTERN)
  if (!match) return null
  const sign = match[1] === '-' ? -BIGINT_ONE : BIGINT_ONE
  const fraction = (match[3] ?? '').padEnd(2, '0')
  return {
    value: sign * BigInt(`${match[2]}${fraction}`),
    scale: 2,
  }
}

const fromMinorAmount = (minor: bigint, scale = 2): CommerceMoney => {
  const isNegative = minor < BIGINT_ZERO
  const absolute = isNegative ? -minor : minor
  const padded = absolute.toString().padStart(scale + 1, '0')
  const integer = padded.slice(0, -scale)
  const fraction = padded.slice(-scale)
  return `${isNegative ? '-' : ''}${integer}.${fraction}`
}

export const normalizeMoney = (value: unknown): CommerceMoney | null => {
  if (typeof value !== 'string') return null
  const minor = toMinorAmount(value)
  return minor ? fromMinorAmount(minor.value, minor.scale) : null
}

export const sumMoney = (values: Array<CommerceMoney | null>): CommerceMoney | null => {
  let total = BIGINT_ZERO
  for (const value of values) {
    if (value === null) return null
    const minor = toMinorAmount(value)
    if (!minor) return null
    total += minor.value
  }
  return fromMinorAmount(total)
}

export const multiplyMoney = (
  value: CommerceMoney | null,
  quantity: number,
): CommerceMoney | null => {
  if (value === null || !Number.isSafeInteger(quantity) || quantity < 1) return null
  const amount = toMinorAmount(value)
  return amount ? fromMinorAmount(amount.value * BigInt(quantity)) : null
}

export const sumCommercePurchaseLines = (
  lines: readonly CommercePurchaseLine[],
): CommerceMoney | null => sumMoney(
  lines.map(line => multiplyMoney(line.item.price, line.quantity)),
)

export const percentageOfMoney = (
  value: CommerceMoney | null,
  percent: string,
): CommerceMoney | null => {
  if (value === null) return null
  const amount = toMinorAmount(value)
  const normalizedPercent = percent.trim().match(DECIMAL_PATTERN)
  if (!amount || !normalizedPercent || normalizedPercent[1] === '-') return null
  const fraction = (normalizedPercent[3] ?? '').padEnd(2, '0')
  const basisPoints = BigInt(`${normalizedPercent[2]}${fraction}`)
  const numerator = amount.value * basisPoints
  const rounded = numerator >= BIGINT_ZERO
    ? (numerator + ROUNDING_HALF) / PERCENT_DENOMINATOR
    : (numerator - ROUNDING_HALF) / PERCENT_DENOMINATOR
  return fromMinorAmount(rounded)
}

export const isPositiveMoney = (value: CommerceMoney | null | undefined): boolean => {
  if (!value) return false
  const minor = toMinorAmount(value)
  return Boolean(minor && minor.value > BIGINT_ZERO)
}

export const isValidPercent = (
  value: string,
  options: { maxInclusive?: boolean } = {},
): boolean => {
  const normalized = value.trim().match(DECIMAL_PATTERN)
  if (!normalized || normalized[1] === '-') return false
  const whole = BigInt(normalized[2])
  const fraction = BigInt((normalized[3] ?? '').padEnd(2, '0'))
  const basisPoints = whole * BASIS_POINTS_SCALE + fraction
  const withinMaximum = options.maxInclusive === false
    ? basisPoints < PERCENT_DENOMINATOR
    : basisPoints <= PERCENT_DENOMINATOR
  return basisPoints >= BASIS_POINTS_SCALE && withinMaximum
}

export const formatCommerceMoney = (
  value: CommerceMoney | number | null | undefined,
  currencyCode = 'RUB',
): string => {
  if (value === null || value === undefined) return 'По запросу'
  const rawValue = typeof value === 'number'
    ? (Number.isFinite(value) ? String(value) : '')
    : value
  const normalized = normalizeMoney(rawValue)
  if (!normalized) return String(value)
  const [integer, fraction = '00'] = normalized.split('.')
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00A0')
  const decimals = fraction === '00' ? '' : `,${fraction}`
  return currencyCode === 'RUB'
    ? `${grouped}${decimals}\u00A0₽`
    : `${grouped}${decimals}\u00A0${currencyCode}`
}
