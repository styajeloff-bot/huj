import type { ConditionPair, ConditionRow, PairedSourceBlock, ProgramDraft, ProgramEditorDraft, SourceBlock } from './types'

export const sourceOptions = [
  { value: 'platform', label: 'Заявка с сайта платформы МЛ', disabled: false },
  { value: 'dealer_account', label: 'Заявка через аккаунт дилера', disabled: false },
  { value: 'exchange', label: 'Биржа ТС', disabled: false },
  { value: 'dealer_site', label: 'Заявка с сайта дилера', disabled: false },
  { value: 'distributor_site', label: 'Заявка с сайта дистрибьютора', disabled: false },
  { value: 'quick_deal_dealer', label: 'Регистрация сделки дилером', disabled: true },
  { value: 'quick_deal_distributor', label: 'Регистрация сделки дистрибьютором', disabled: true },
  { value: 'leasing_to_dealer', label: 'ЛК → дилер', disabled: true },
  { value: 'dealer_to_leasing', label: 'Дилер → ЛК', disabled: true },
] as const
export const participantLabels = { leasing: 'Лизинговая компания', dealer: 'Дилер', distributor: 'Дистрибьютор', platform: 'Платформа МЛ' }
export const sourceLabel = (value: string) => sourceOptions.find(option => option.value === value)?.label ?? value
export const newRow = (id: string): ConditionRow => ({ local_id: id, participant_type: 'leasing', base_type: 'property_value', expense_ref: null, calc_type: 'percent', value: '', min: null, max: null, vat_excluded: false })
export const newBlock = (id: string, expenseId: string): SourceBlock => ({ local_id: id, source_type: 'platform', expenses: [newRow(expenseId)], incomes: [] })
export function newPair(id: string, expenseId: string, incomeId: string): ConditionPair {
  return { local_id: id, expense: newRow(expenseId), incomes: [{ ...newRow(incomeId), participant_type: 'dealer', expense_ref: expenseId }] }
}
export function newPairedBlock(id: string, pairId: string, expenseId: string, incomeId: string): PairedSourceBlock {
  return { local_id: id, source_type: 'platform', pairs: [newPair(pairId, expenseId, incomeId)] }
}
export function removePair(block: PairedSourceBlock, id: string): PairedSourceBlock {
  return block.pairs.length > 1 ? { ...block, pairs: block.pairs.filter(pair => pair.local_id !== id) } : block
}
export function toProgramDraft(editor: ProgramEditorDraft): ProgramDraft {
  return {
    ...editor,
    sources: editor.sources.map(block => ({
      local_id: block.local_id,
      source_type: block.source_type,
      expenses: block.pairs.map(pair => ({ ...pair.expense, expense_ref: null })),
      incomes: block.pairs.flatMap(pair => pair.incomes.map(income => ({
        ...income, expense_ref: pair.expense.local_id,
      }))),
    })),
  }
}
export function validateDraft(draft: ProgramDraft): string | null {
  if (!draft.name.trim()) return 'Укажите название условий'
  if (!draft.leasing_company_id) return 'Выберите лизинговую компанию из результатов поиска'
  if (!draft.period_start) return 'Укажите начало действия'
  if (draft.period_end && draft.period_end < draft.period_start) return 'Окончание действия должно быть не раньше начала'
  if (!draft.sources.length) return 'Добавьте хотя бы один источник заявки'
  if (draft.support_program_id && draft.sources.some(block => block.source_type === 'exchange')) return 'Для биржи нельзя выбрать программу стимулирования'
  for (const block of draft.sources) {
    if (!sourceOptions.some(option => option.value === block.source_type && !option.disabled)) return 'Источник недоступен'
    if (!block.expenses.length) return 'Добавьте хотя бы один расход в каждый источник'
    for (const row of [...block.expenses, ...block.incomes]) {
      if (!(row.participant_type in participantLabels)) return 'Участник недоступен'
      if (!/^\d+(\.\d{1,2})?$/.test(row.value) || !/[1-9]/.test(row.value)) return 'Укажите положительное значение каждой строки'
      if (row.base_type === 'none' && row.calc_type !== 'amount') return 'Без базы допустима только фиксированная сумма'
      if (row.base_type === 'property_value' && row.calc_type !== 'percent') return 'От стоимости имущества допустим только процент'
      if (block.incomes.includes(row) && !block.expenses.some(expense => expense.local_id === row.expense_ref)) return 'Каждый доход должен относиться к расходу своей связки'
      if (block.expenses.includes(row) && row.base_type === 'expense_amount') return 'Расход нельзя рассчитывать от другого расхода'
      for (const bound of [row.min, row.max]) if (bound !== null && (!/^\d+(\.\d{1,2})?$/.test(bound) || !/[1-9]/.test(bound))) return 'Заполненные ограничения суммы должны быть положительными числами с точностью до копеек'
      if (row.min !== null && row.max !== null && decimalCompare(row.min, row.max) > 0) return 'Минимум не должен превышать максимум'
    }
  }
  return null
}
function decimalCompare(left: string, right: string): number {
  const [lw = '0', lf = ''] = left.split('.')
  const [rw = '0', rf = ''] = right.split('.')
  const l = BigInt(lw) * 100n + BigInt(lf.padEnd(2, '0'))
  const r = BigInt(rw) * 100n + BigInt(rf.padEnd(2, '0'))
  return l === r ? 0 : l < r ? -1 : 1
}
