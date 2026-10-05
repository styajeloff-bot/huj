import type { MoneyString } from './types'

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/

/**
 * Display format of an exact decimal string: «1 250 000,00 ₽». The value is never converted to
 * a JS number, so no digit of the kopeck precision can be lost. Anything that is not a plain
 * decimal string is returned as is.
 */
export function formatMoney(value: MoneyString | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const match = DECIMAL.exec(value.trim())
  if (!match) return value
  const [, sign, integer, fraction = ''] = match
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  return `${sign}${grouped},${fraction.padEnd(2, '0')} ₽`
}
