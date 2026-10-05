export const MIN_LEASE_TERM_MONTHS = 12
export const MAX_LEASE_TERM_MONTHS = 84

export function clampLeaseTermMonths(value: number): number
export function clampLeaseTermMonths(value: null): null
export function clampLeaseTermMonths(value: number | null): number | null {
  if (value === null || !Number.isInteger(value)) return value
  return Math.min(MAX_LEASE_TERM_MONTHS, Math.max(MIN_LEASE_TERM_MONTHS, value))
}

export const isEligibleLeaseTermMonths = (value: unknown): value is number =>
  typeof value === 'number' &&
  Number.isInteger(value) &&
  value >= MIN_LEASE_TERM_MONTHS &&
  value <= MAX_LEASE_TERM_MONTHS
