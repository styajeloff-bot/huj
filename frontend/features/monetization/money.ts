/** Decimal strings remain exact even above Number.MAX_SAFE_INTEGER. */
export function decimalUnits(value: string): bigint {
  if (!/^-?\d+(\.\d{1,2}0*)?$/.test(value)) throw new Error('Укажите сумму с точностью до копеек')
  const negative = value.startsWith('-')
  const [whole = '0', fraction = ''] = value.replace('-', '').split('.')
  const units = BigInt(whole) * BigInt(100) + BigInt(fraction.slice(0, 2).padEnd(2, '0'))
  return negative ? -units : units
}
export function decimalString(units: bigint): string {
  const absolute = units < BigInt(0) ? -units : units
  return `${units < BigInt(0) ? '-' : ''}${absolute / BigInt(100)}.${String(absolute % BigInt(100)).padStart(2, '0')}`
}
/** HALF_UP display normalization, without Number conversion or changing stored values. */
export function roundToHundredths(value: string): string {
  if (!/^-?\d+(\.\d+)?$/.test(value)) return value
  const negative = value.startsWith('-')
  const [whole = '0', fraction = ''] = value.replace('-', '').split('.')
  let cents = BigInt(whole) * BigInt(100) + BigInt(fraction.slice(0, 2).padEnd(2, '0'))
  if ((fraction[2] ?? '0') >= '5') cents += BigInt(1)
  return decimalString(negative ? -cents : cents).replace(/\.?0+$/, '')
}
export function formatMoney(value: string, precision?: 2): string {
  if (precision === 2) value = roundToHundredths(value)
  if (!/^-?\d+(\.\d+)?$/.test(value)) return '—'
  const [whole = '0', rawFraction = ''] = value.split('.')
  const fraction = rawFraction.replace(/0+$/, '')
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}${fraction ? ',' + fraction : ''} ₽`
}
export function platformBalance(expenses: string[], incomes: { participant_type: string; amount: string }[]): string {
  const outgoing = expenses.reduce((total, amount) => total + decimalUnits(amount), BigInt(0))
  const incoming = incomes.filter(row => row.participant_type !== 'platform').reduce((total, row) => total + decimalUnits(row.amount), BigInt(0))
  return decimalString(outgoing - incoming)
}
export function formatPercent(value: string, precision?: 2): string {
  if (precision === 2) value = roundToHundredths(value)
  if (!/^-?\d+(\.\d+)?$/.test(value)) return '—'
  const [whole, rawFraction = ''] = value.split('.')
  const fraction = rawFraction.replace(/0+$/, '')
  return `${whole}${fraction ? ',' + fraction : ''}%`
}

export function roundMoneyToRubles(value: string): string {
  const units = decimalUnits(value)
  const halfRuble = units < BigInt(0) ? BigInt(-50) : BigInt(50)
  return String((units + halfRuble) / BigInt(100))
}
