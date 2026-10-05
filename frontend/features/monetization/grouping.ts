import type { Participant } from './types'

type FinancialRow = { id: string; participant_type: Participant }

export function groupIncomes<T extends FinancialRow>(
  expenses: readonly T[],
  incomes: readonly T[],
  expenseKey: (row: T) => string | null,
  incomeReference: (row: T) => string | null,
) {
  const platformFirst = (rows: readonly T[]) => [...rows].sort((left, right) =>
    (left.participant_type === 'platform' ? 0 : 1) - (right.participant_type === 'platform' ? 0 : 1))
  const visibleExpenses = new Set(expenses.map(expenseKey).filter(key => key !== null))
  const orderedIncomes = platformFirst(incomes)
  const groups: { id: string; label: string; expense: T | null; incomes: T[] }[] = platformFirst(expenses).map((expense, index) => ({
    id: expense.id,
    label: `Расход ${index + 1} и связанные доходы`,
    expense,
    incomes: orderedIncomes.filter(income => expenseKey(expense) !== null && incomeReference(income) === expenseKey(expense)),
  }))
  const standalone = orderedIncomes.filter(income => incomeReference(income) === null)
  if (standalone.length) groups.push({ id: 'standalone-incomes', label: 'Самостоятельные доходы', expense: null, incomes: standalone })
  // An authorized income may reference an expense filtered out by the server.
  // Keep that income visible without reconstructing the other party's row.
  const available = orderedIncomes.filter(income => {
    const reference = incomeReference(income)
    return reference !== null && !visibleExpenses.has(reference)
  })
  if (available.length) groups.push({ id: 'available-incomes', label: 'Доступные доходы', expense: null, incomes: available })
  return groups
}
