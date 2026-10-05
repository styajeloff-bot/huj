import type { Deal, DealAdjustmentItem, TermsInputMode } from './types'
import { roundToHundredths } from './money'

const SCALE = BigInt('1000000000000000000')
const CENT = SCALE / BigInt(100)
const RATE_SCALE = BigInt(100)
const MONEY_LIMIT = BigInt('10000000000000000') * SCALE
export interface TermDraft { inputMode: TermsInputMode; value: string; dirty: boolean }
export interface TermPreview {
  inputMode: TermsInputMode
  amount: string
  percent: string
  effectivePercent: string | null
  finalAmount: string
  base: string | null
  error: string | null
  changed: boolean
  raw: bigint | null
  rounded: bigint | null
}
export interface DealTermsPreview {
  rows: Record<string, TermPreview>
  items: DealAdjustmentItem[]
  budgetErrors: Record<string, string>
  remainders: Record<string, string>
  valid: boolean
}

function compact(value: string): string {
  const [whole = '0', fraction = ''] = value.replace(',', '.').split('.')
  const trimmed = fraction.replace(/0+$/, '')
  return whole.replace(/^0+(?=\d)/, '') + (trimmed ? '.' + trimmed : '')
}
function decimal(value: string, places: number, wholeDigits = 16): bigint {
  const normalized = value.replace(',', '.')
  if (!/^\d+(\.\d+)?$/.test(normalized)) throw new Error('Введите неотрицательное число')
  const [whole = '', fraction = ''] = normalized.split('.')
  if (fraction.replace(/0+$/, '').length > places) {
    throw new Error('Допустимо не более ' + places + ' знаков после запятой')
  }
  if (whole.replace(/^0+/, '').length > wholeDigits) throw new Error('Значение слишком велико')
  return BigInt(whole) * SCALE + BigInt(fraction.slice(0, 18).padEnd(18, '0'))
}
function fractionText(value: bigint, scale = SCALE): string {
  const places = scale.toString().length - 1
  const remainder = String(value % scale).padStart(places, '0').replace(/0+$/, '')
  return String(value / scale) + (remainder ? '.' + remainder : '')
}
function rounded(value: bigint): bigint { return (value + CENT / BigInt(2)) / CENT }
function normalizedInput(draft: TermDraft): bigint {
  const digits = draft.inputMode === 'percent' ? 30 : 16
  const entered = rounded(decimal(draft.value, 8, digits)) * CENT
  if (entered <= BigInt(0)) throw new Error('Значение после округления должно быть больше нуля')
  if (entered >= BigInt('1' + '0'.repeat(digits)) * SCALE) throw new Error('Значение слишком велико')
  return entered
}
function equivalentPercent(amount: bigint, base: bigint | null): string | null {
  if (base === null || base === BigInt(0)) return null
  const numerator = amount * CENT * BigInt(100) * RATE_SCALE
  const percent = (numerator + base / BigInt(2)) / base
  if (percent >= BigInt('1000000000000000000000000000000') * RATE_SCALE) throw new Error('Процент слишком велик')
  return fractionText(percent, RATE_SCALE)
}
function equalDecimal(left: string | null, right: string | null): boolean {
  return left === null || right === null ? left === right : compact(left) === compact(right)
}
export function createTermsDraft(deal: Deal): Record<string, TermDraft> {
  return Object.fromEntries([...deal.expenses, ...deal.incomes].map(row => [row.id, {
    inputMode: row.input_mode,
    value: compact(row.input_mode === 'percent' ? row.percent ?? '' : row.amount),
    dirty: false,
  }]))
}
/** Normalize only actual input; focus and blur must not rewrite historical terms. */
export function normalizeTermDraft(draft: TermDraft): TermDraft {
  if (!draft.dirty) return draft
  try { return { ...draft, value: fractionText(normalizedInput(draft)) } } catch { return draft }
}

/** Saved values are the baseline; only explicit input or a changed base recalculates them. */
export function previewDealTerms(deal: Deal, drafts: Record<string, TermDraft>): DealTermsPreview {
  const rows: Record<string, TermPreview> = {}
  const items: DealAdjustmentItem[] = []
  const budgetErrors: Record<string, string> = {}
  const remainders: Record<string, string> = {}
  for (const row of [...deal.expenses, ...deal.incomes]) {
    const draft = drafts[row.id]!
    let base: bigint | null = null
    let baseError = false
    try {
      if (row.base_type === 'expense_amount' && row.expense_ref_amount_id) {
        const expense = rows[row.expense_ref_amount_id]
        if (expense) {
          base = expense.rounded === null ? null : expense.rounded * CENT
          baseError = expense.error !== null
        } else if (row.calculation_base_amount !== null) base = decimal(row.calculation_base_amount, 8)
      } else if (row.calculation_base_amount !== null) base = decimal(row.calculation_base_amount, 8)
    } catch { baseError = true }
    const view: TermPreview = {
      inputMode: draft.inputMode,
      amount: draft.dirty && draft.inputMode === 'amount' ? draft.value : roundToHundredths(row.amount),
      percent: draft.dirty && draft.inputMode === 'percent' ? draft.value : row.percent === null ? '' : roundToHundredths(row.percent),
      effectivePercent: row.percent, finalAmount: row.amount,
      base: base === null ? null : fractionText(base), error: null, changed: false, raw: null, rounded: null,
    }
    rows[row.id] = view
    try {
      if (baseError) throw new Error('Сначала исправьте сумму связанного расхода')
      const savedAmount = decimal(row.amount, 8)
      const baseChanged = !equalDecimal(view.base, row.calculation_base_amount)
      const entered = draft.dirty ? normalizedInput(draft) : null
      const sameAmountInput = draft.dirty && draft.inputMode === 'amount' && row.input_mode === 'amount'
        && entered === savedAmount && !baseChanged
      const recalculate = !sameAmountInput && (draft.dirty || (baseChanged && savedAmount !== BigInt(0)))
      let raw = savedAmount
      let percent = row.percent
      if (recalculate) {
        if (draft.inputMode === 'percent') {
          if (base === null || base === BigInt(0)) throw new Error('Процент недоступен без положительной базы. Укажите сумму.')
          const rate = entered ?? decimal(row.percent ?? '', 8, 30)
          percent = fractionText(rate)
          raw = base * rate / (SCALE * BigInt(100))
        } else raw = entered ?? savedAmount
      }
      const final = rounded(raw)
      if (final * CENT >= MONEY_LIMIT) throw new Error('Итоговая сумма слишком велика')
      if (recalculate && draft.inputMode === 'amount') percent = equivalentPercent(final, base)
      view.raw = raw
      view.rounded = final
      view.finalAmount = fractionText(final, RATE_SCALE)
      view.effectivePercent = percent
      if (draft.inputMode === 'percent') {
        view.amount = view.finalAmount
        if (!draft.dirty) view.percent = percent === null ? '' : roundToHundredths(percent)
      } else view.percent = percent === null ? '' : roundToHundredths(percent)
      view.changed = savedAmount !== final * CENT || row.input_mode !== draft.inputMode || !equalDecimal(row.percent, percent)
      if (recalculate && final <= BigInt(0)) throw new Error('Изменённая сумма после округления должна быть больше нуля')
      // Omitted dependent rows keep their exact historical rate on the server.
      if (draft.dirty && view.changed) {
        items.push(draft.inputMode === 'percent'
          ? { deal_participant_amount_id: row.id, input_mode: 'percent', new_percent: compact(draft.value) }
          : { deal_participant_amount_id: row.id, input_mode: 'amount', new_value: compact(draft.value) })
      }
    } catch (failure) {
      view.error = failure instanceof Error ? failure.message : 'Проверьте значение'
    }
  }
  for (const expense of deal.expenses) {
    const incomes = deal.incomes.filter(income => income.expense_ref_amount_id === expense.id)
    const expenseView = rows[expense.id]!
    const views = incomes.map(income => rows[income.id]!)
    if (expenseView.error || views.some(view => view.error)) continue
    const effectiveRaw = (id: string, amount: string, previousBase: string | null) => {
      const view = rows[id]!
      const recalculated = view.inputMode === 'percent' && !equalDecimal(view.base, previousBase)
      return view.changed || recalculated ? view.raw! : decimal(amount, 8)
    }
    const exactIncome = incomes.reduce((sum, income) => sum + effectiveRaw(income.id, income.amount, income.calculation_base_amount), BigInt(0))
    const finalIncome = views.reduce((sum, income) => sum + income.rounded!, BigInt(0))
    if (exactIncome > effectiveRaw(expense.id, expense.amount, expense.calculation_base_amount)) {
      budgetErrors[expense.id] = 'Сумма связанных доходов превышает расход до округления.'
    } else if (finalIncome > expenseView.rounded!) {
      budgetErrors[expense.id] = 'После округления сумма связанных доходов превышает расход.'
    } else if (finalIncome < expenseView.rounded!) {
      remainders[expense.id] = fractionText(expenseView.rounded! - finalIncome, RATE_SCALE)
    }
  }
  return { rows, items, budgetErrors, remainders, valid: !Object.values(rows).some(row => row.error) && !Object.keys(budgetErrors).length }
}
