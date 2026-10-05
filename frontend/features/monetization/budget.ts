import type { ConditionPair, ConditionRow } from './types'
import { decimalString, decimalUnits } from './money'

// Fractions retain exact decimal arithmetic, including percentages of an expense.
// n/d is measured in kopecks, hundredths of a property percentage, or hundredths
// of an expense percentage according to the selected comparison mode.
type Fraction = { n: bigint; d: bigint }
const fraction = (n: bigint, d = BigInt(1)): Fraction => ({ n, d })
const add = (a: Fraction, b: Fraction) => fraction(a.n * b.d + b.n * a.d, a.d * b.d)
const subtract = (a: Fraction, b: Fraction) => fraction(a.n * b.d - b.n * a.d, a.d * b.d)
const multiply = (a: Fraction, b: Fraction) => fraction(a.n * b.n, a.d * b.d)
const compare = (a: Fraction, b: Fraction) => a.n * b.d - b.n * a.d
const zero = fraction(BigInt(0))
const roundedKopecks = (value: Fraction) => (value.n * BigInt(2) + value.d) / (BigInt(2) * value.d)
const bounded = (row: ConditionRow) => row.min !== null || row.max !== null
const validValue = (value: string) => /^\d+(\.\d{1,2})?$/.test(value)
const units = (value: string) => decimalUnits(value || '0')
const constantBounds = (row: ConditionRow) => row.min !== null && row.max !== null && units(row.min) === units(row.max)
function bounds(row: ConditionRow, amount: Fraction): Fraction {
  if (row.min !== null && compare(amount, fraction(units(row.min))) < BigInt(0)) amount = fraction(units(row.min))
  if (row.max !== null && compare(amount, fraction(units(row.max))) > BigInt(0)) amount = fraction(units(row.max))
  return amount
}
interface Calculation {
  capacity: Fraction
  rate: (row: ConditionRow) => Fraction
  amount: (row: ConditionRow) => Fraction
  money: boolean
}
function calculation(pair: ConditionPair): Calculation | null {
  const expense = pair.expense
  const incomes = pair.incomes
  if (!validValue(expense.value) || incomes.some(row => row.value !== '' && !validValue(row.value))) return null
  if ([expense, ...incomes].some(row => [row.min, row.max].some(value => value !== null && !validValue(value)))) return null
  if ((expense.calc_type === 'amount' || constantBounds(expense))
    && incomes.every(row => row.calc_type === 'amount' || row.base_type === 'expense_amount' || constantBounds(row))) {
    // Equal monetary bounds make either formula constant, regardless of its
    // percentage base. A constant income still requires an explicit minimum
    // change when it exceeds the available budget; changing value cannot help.
    const capacity = bounds(expense, fraction(units(expense.value)))
    const rate = (row: ConditionRow) => constantBounds(row) ? fraction(BigInt(0))
      : row.calc_type === 'amount' ? fraction(BigInt(1)) : multiply(capacity, fraction(BigInt(1), BigInt(10000)))
    return { capacity, rate, amount: row => bounds(row, multiply(fraction(units(row.value)), rate(row))), money: true }
  }
  if (incomes.every(row => row.calc_type === 'percent' && row.base_type === 'expense_amount' && !bounded(row))) {
    return { capacity: fraction(BigInt(10000)), rate: () => fraction(BigInt(1)), amount: row => fraction(units(row.value)), money: false }
  }
  if (expense.calc_type === 'percent' && expense.base_type === 'property_value' && !bounded(expense)
    && incomes.every(row => row.calc_type === 'percent' && !bounded(row) && row.base_type !== 'none')) {
    const capacity = fraction(units(expense.value))
    const rate = (row: ConditionRow) => row.base_type === 'expense_amount' ? multiply(capacity, fraction(BigInt(1), BigInt(10000))) : fraction(BigInt(1))
    return { capacity, rate, amount: row => multiply(fraction(units(row.value)), rate(row)), money: false }
  }
  return null
}
export function pairBudget(pair: ConditionPair): { deferred: boolean; error: string | null; exhausted: boolean } {
  if (!pair.incomes.length) return { deferred: false, error: null, exhausted: false }
  const calc = calculation(pair)
  if (!calc) return { deferred: true, error: null, exhausted: false }
  const total = pair.incomes.reduce((sum, row) => add(sum, calc.amount(row)), zero)
  const remaining = subtract(calc.capacity, total)
  const roundedTotal = calc.money ? pair.incomes.reduce((sum, row) => sum + roundedKopecks(calc.amount(row)), BigInt(0)) : BigInt(0)
  const minimumConflict = calc.money && pair.incomes.some(row => {
    if (row.min === null) return false
    const other = subtract(total, calc.amount(row))
    const minimum = fraction(units(row.min))
    const otherRounded = roundedTotal - roundedKopecks(calc.amount(row))
    return compare(minimum, subtract(calc.capacity, other)) > BigInt(0) || roundedKopecks(minimum) > roundedKopecks(calc.capacity) - otherRounded
  })
  return {
    deferred: false,
    error: minimumConflict ? 'Минимум дохода превышает остаток расхода. Измените минимум или распределение доходов.'
      : compare(total, calc.capacity) > BigInt(0) ? 'Доходы связки превышают её расход. Измените распределение.'
      : calc.money && roundedTotal > roundedKopecks(calc.capacity) ? 'После округления до копеек доходы превышают расход. Уменьшите доход.' : null,
    exhausted: remaining.n <= BigInt(0),
  }
}
/** Limit the edited income, or reduce incomes from last to first after expense changes. */
export function capPairIncomes(pair: ConditionPair, editedId?: string): boolean {
  const calc = calculation(pair)
  if (!calc) return false
  let changed = false
  const candidates = editedId ? pair.incomes.filter(row => row.local_id === editedId) : [...pair.incomes].reverse()
  for (const row of candidates) {
    if (!row.value || !validValue(row.value)) continue
    const otherRows = pair.incomes.filter(item => item !== row)
    const others = otherRows.reduce((sum, item) => add(sum, calc.amount(item)), zero)
    const roundedAvailable = calc.money ? roundedKopecks(calc.capacity) - otherRows.reduce((sum, item) => sum + roundedKopecks(calc.amount(item)), BigInt(0)) : null
    const available = subtract(calc.capacity, others)
    const limit = available.n < BigInt(0) ? zero : available
    if (compare(calc.amount(row), limit) <= BigInt(0) && (roundedAvailable === null || roundedKopecks(calc.amount(row)) <= roundedAvailable)) continue
    // A conflicting minimum needs an explicit user decision; do not silently
    // rewrite a minimum or pretend that changing the input fixes that constraint.
    if (calc.money && row.min !== null && (compare(fraction(units(row.min)), limit) > BigInt(0)
      || (roundedAvailable !== null && roundedKopecks(fraction(units(row.min))) > roundedAvailable))) continue
    const rate = calc.rate(row)
    let maximum = rate.n > BigInt(0) ? limit.n * rate.d / (limit.d * rate.n) : BigInt(0)
    if (roundedAvailable !== null && rate.n > BigInt(0)) {
      // ROUND_HALF_UP makes the upper boundary exclusive: a row rounding to
      // 4 kopecks must stay strictly below 4.5, even when the exact budget fits.
      const roundedMaximum = roundedAvailable < BigInt(0) ? BigInt(0) : ((roundedAvailable * BigInt(2) + BigInt(1)) * rate.d - BigInt(1)) / (BigInt(2) * rate.n)
      if (roundedMaximum < maximum) maximum = roundedMaximum
    }
    const value = decimalString(maximum).replace(/\.?0+$/, '')
    if (row.value !== value) { row.value = value; changed = true }
  }
  return changed
}
