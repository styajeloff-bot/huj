import { ref } from 'vue'
import { useNotificationCompanyRequest } from '~/features/notifications'

export interface AccountingRow {
  code: string
  name: string
  values: Record<string, number | null>
}

export interface FinancialRatio {
  key: string
  name: string
  value: number | null
  band: 'good' | 'warn' | 'bad' | 'unknown'
  hint: string
  formula: string
}

export interface AuditReport {
  auditor_name: string | null
  auditor_inn: string | null
  auditor_ogrn: string | null
  pdf_url: string | null
}

export interface OrganizationInfo {
  inn: string
  kpp: string | null
  ogrn: string | null
  short_name: string | null
  full_name: string | null
  status: string | null
  okved2: string | null
  okopf: string | null
  address: string | null
  org_id: string | null
  registration_date?: string | null
  tax_authority_name?: string | null
  tax_authority_code?: string | null
}

export interface AccountingYearFile {
  year: number
  detail_id: string | null
  pdf_url: string | null
  audit_pdf_url: string | null
  clarification_pdf_url: string | null
}

export interface AccountingReport {
  inn: string
  company_id: number | null
  provider_name: string
  period_years: number[]
  organization: OrganizationInfo | null
  balance_sheet: AccountingRow[]
  financial_result: AccountingRow[]
  cash_flow: AccountingRow[]
  capital_change: AccountingRow[]
  audit_report: AuditReport | null
  clarification_url: string | null
  year_files: AccountingYearFile[]
  computed_ratios: FinancialRatio[]
  fetch_status: 'success' | 'not_found' | 'failed' | 'pending' | 'fetching'
  last_fetch_at: string | null
  cached: boolean
  stale: boolean
}

export type AccountingStatus = 'idle' | 'loading' | 'success' | 'not_found' | 'unavailable' | 'error'

export function useCheckoutAccounting() {
  const { request: notificationRequest } = useNotificationCompanyRequest()
  const config = useRuntimeConfig()
  const status = ref<AccountingStatus>('idle')
  const report = ref<AccountingReport | null>(null)
  const errorMessage = ref('')

  const fetchAccounting = async (inn: string): Promise<AccountingReport | null> => {
    status.value = 'loading'
    errorMessage.value = ''
    try {
      const data = await notificationRequest<AccountingReport>(`/api/v1/accounting/${inn}`, {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      report.value = data
      status.value = 'success'
      return data
    } catch (err: unknown) {
      const e = err as { statusCode?: number; status?: number; data?: { detail?: string } }
      const code = e.statusCode || e.status
      if (code === 404) {
        status.value = 'not_found'
      } else if (code === 503) {
        status.value = 'unavailable'
      } else {
        status.value = 'error'
      }
      errorMessage.value = e.data?.detail || 'Не удалось получить бухгалтерскую отчётность'
      report.value = null
      return null
    }
  }

  const refreshAccounting = async (inn: string): Promise<AccountingReport | null> => {
    status.value = 'loading'
    errorMessage.value = ''
    try {
      const data = await notificationRequest<AccountingReport>(`/api/v1/accounting/${inn}/refresh`, {
        method: 'POST',
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      report.value = data
      status.value = 'success'
      return data
    } catch (err: unknown) {
      const e = err as { statusCode?: number; status?: number; data?: { detail?: string } }
      const code = e.statusCode || e.status
      // Keep the previously loaded report visible on refresh failure so the
      // user doesn't lose charts/tables after hitting "Обновить".
      const hasPriorData = report.value !== null
      if (code === 404) {
        status.value = hasPriorData ? 'success' : 'not_found'
      } else if (code === 503) {
        status.value = hasPriorData ? 'success' : 'unavailable'
      } else {
        status.value = hasPriorData ? 'success' : 'error'
      }
      errorMessage.value = e.data?.detail || 'Не удалось обновить бухгалтерскую отчётность'
      return null
    }
  }

  return {
    status: status as import('vue').Ref<AccountingStatus>,
    report,
    errorMessage: errorMessage as import('vue').Ref<string>,
    fetchAccounting,
    refreshAccounting
  }
}
