export interface BankStatementAnalyticsCompany {
  id: string
  name: string
  inn: string
}

export interface BankStatementAnalyticsAccount {
  account_number: string
  bank_name: string
}

export interface BankStatementAnalyticsPeriod {
  start: string
  end: string
}

export interface BankStatementAnalyticsKpi {
  income: number | null
  expense: number | null
  turnover: number | null
  average_monthly_turnover: number | null
  external_revenue: number | null
  opening_balance: number | null
  closing_balance: number | null
  balance_change: number | null
}

export interface BankStatementCashflowPoint {
  month: string
  income: number
  expense: number
  closing_balance: number
}

export interface BankStatementExpenseSlice {
  operation_kind: string
  amount: number
  share: number
}

export interface BankStatementCounterparty {
  display_name: string
  inn?: string | null
  amount: number
  is_self_transfer: boolean
}

export interface BankStatementAnalytics {
  company: BankStatementAnalyticsCompany
  accounts: BankStatementAnalyticsAccount[]
  period: BankStatementAnalyticsPeriod | null
  kpi: BankStatementAnalyticsKpi
  cashflow: BankStatementCashflowPoint[]
  expense_structure: BankStatementExpenseSlice[]
  top_clients: BankStatementCounterparty[]
  top_suppliers: BankStatementCounterparty[]
  empty: boolean
}
