import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export type CompensationStatus = 'under_review' | 'accepted' | 'rejected' | 'paid' | 'overdue' | 'cancelled'
export type CompensationSource = 'platform' | 'exchange'
export type CompensationSchedulePeriod = 'week' | 'month' | 'two_months' | 'quarter' | 'half_year' | 'year'
export type CompensationPayer =
  | 'distributor'
  | 'dealer'
  | 'carcraft'
  | 'minpromtorg'
  | 'client'
export type CompensationRecipient = 'leasing_company' | 'dealer' | 'carcraft' | 'client'
export type CompensationCalculationBase =
  | 'base_price'
  | 'special_price'
  | 'dealer_cost'
  | 'application_price'
  | 'down_payment'
  | 'support_amount'

export interface CompensationDocument {
  id?: UUID
  name?: string
  path?: string
  file_name?: string
  content_type?: string
  size?: number
  purpose?: 'acceptance' | 'rejection' | 'payment'
  uploaded_at?: string
  [key: string]: unknown
}

export interface CompensationRecord {
  id: UUID
  compensation_id: UUID
  applied_support_id: UUID
  applied_support_name?: string | null
  support_program_id?: UUID | null
  application_id: UUID | null
  application_display_number?: string | null
  exchange_request_id: UUID | null
  exchange_request_display_number?: string | null
  source: CompensationSource
  vehicle_id: UUID | null
  payer: CompensationPayer
  recipient: CompensationRecipient
  calculation_base: CompensationCalculationBase
  calculation_base_amount: number
  value_type: 'percent' | 'sum'
  value: number
  min_amount: number | null
  max_amount: number | null
  min_percent: number | null
  max_percent: number | null
  amount: number
  status: CompensationStatus
  payment_schedule_type: string
  payment_schedule_period: CompensationSchedulePeriod | null
  payment_schedule_value: string | null
  due_date: string | null
  paid_at: string | null
  documents: CompensationDocument[]
  acceptance_comment?: string | null
  rejection_comment?: string | null
  comment: string
  created_by: UUID | null
  created_at: string | null
  updated_at: string | null
}

export interface CompensationPagination {
  page: number
  limit: number
  total: number
  pages: number
  total_pages?: number
}

export interface CompensationFilters {
  page?: string
  limit?: string
  application_query?: string
  support_query?: string
  status?: CompensationStatus | ''
  payer?: CompensationPayer | ''
  recipient?: CompensationRecipient | ''
  source?: CompensationSource | ''
  due_date_from?: string
  due_date_to?: string
}

export interface UpdateCompensationStatusPayload {
  status: 'accepted' | 'rejected' | 'paid' | 'cancelled'
  paid_at?: string | null
  documents?: CompensationDocument[] | null
  reason?: string | null
}

export type CompensationDocumentPurpose = 'acceptance' | 'rejection' | 'payment'

export interface UploadCompensationDocumentResponse {
  document: CompensationDocument
}

export interface CompensationCreateItem {
  payer: CompensationPayer
  recipient: CompensationRecipient
  calculation_base: CompensationCalculationBase
  calculation_base_amount?: number | null
  value_type: 'percent' | 'sum'
  value: number
  min_amount?: number | null
  max_amount?: number | null
  min_percent?: number | null
  max_percent?: number | null
  payment_schedule_type?: 'fixed_date' | 'days_count' | 'weekly' | 'quarterly' | 'reporting_period'
  payment_schedule_period?: CompensationSchedulePeriod | null
  payment_schedule_value?: string | null
  comment?: string
}

export interface CancelSupportCompensationsResponse {
  cancelled_count: number
  already_paid_count: number
  warnings: unknown[]
}

export const createCompensationApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  return {
    list: (params?: CompensationFilters) => {
      const query = params
        ? new URLSearchParams(
            Object.fromEntries(
              Object.entries(params).filter(([, value]) => value != null && value !== '')
            )
          ).toString()
        : ''

      return request<{
        compensations: CompensationRecord[]
        pagination: CompensationPagination
      }>(`/api/v1/compensations${query ? `?${query}` : ''}`)
    },

    getById: (id: UUID) =>
      request<{ compensation: CompensationRecord }>(`/api/v1/compensations/${id}`),

    updateStatus: (compensationId: UUID, payload: UpdateCompensationStatusPayload) =>
      request<{ compensation: CompensationRecord }>(
        `/api/v1/compensations/${compensationId}/status`,
        {
          method: 'PATCH',
          body: payload
        }
      ),

    uploadDocument: (
      compensationId: UUID,
      file: File,
      purpose: CompensationDocumentPurpose
    ) => {
      const form = new FormData()
      form.append('file', file)
      form.append('purpose', purpose)
      return request<UploadCompensationDocumentResponse>(
        `/api/v1/compensations/${compensationId}/documents`,
        {
          method: 'POST',
          body: form
        }
      )
    },

    cancelForSupport: (appliedSupportId: UUID) =>
      request<CancelSupportCompensationsResponse>(
        `/api/v1/compensations/support/${appliedSupportId}`,
        { method: 'DELETE' }
      )
  }
}
