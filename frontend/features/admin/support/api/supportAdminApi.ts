import type { CatalogId, UUID } from '~/types/ids'
import type { SupportProgram } from '~/types/admin'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export interface DistributorInventoryBrand {
  id: CatalogId
  name: string
}

export interface BillOfLadingPayload {
  bill_date?: string | null
  file_name?: string | null
  file_path?: string | null
  file_size?: number | null
}

export interface CreateSupportPayload {
  name: string
  mark_id: string
  mark_ids?: string[]
  model_id: string | null
  model_ids?: string[] | null
  complectation_ids?: string[] | null
  production_date_from?: string | null
  production_date_to?: string | null
  production_year_from?: number | null
  production_year_to?: number | null
  delivery_date_from?: string | null
  delivery_date_to?: string | null
  bill_of_lading?: BillOfLadingPayload | null
  vin: string | null
  vins?: string[] | null
  dealer_group_id?: UUID | null
  dealer_group_ids?: UUID[]
  distributor_id: UUID | null
  distributor_ids?: UUID[]
  leasing_company_ids: UUID[]
  compensation_templates?: Array<{
    payer: 'distributor' | 'dealer' | 'carcraft' | 'minpromtorg' | 'client'
    recipient: 'leasing_company' | 'dealer' | 'carcraft' | 'client'
    calculation_base: 'base_price' | 'special_price' | 'dealer_cost' | 'application_price' | 'down_payment' | 'support_amount'
    value_type: 'percent' | 'sum'
    value: number
    min_amount?: number | null
    max_amount?: number | null
    min_percent?: number | null
    max_percent?: number | null
    payment_schedule_type?: 'fixed_date' | 'days_count' | 'weekly' | 'quarterly' | 'reporting_period'
    payment_schedule_period?: 'week' | 'month' | 'two_months' | 'quarter' | 'half_year' | 'year' | null
    payment_schedule_value?: string | null
    comment?: string
  }>
  support_type: string
  support_params: {
    value_type: 'amount' | 'percent'
    value: number
    min_amount: number | null
    max_amount: number | null
    min_percent: number | null
    max_percent: number | null
    compensation_period_months: number | null
    start_month: number | null
  }
  starts_at: string | null
  ends_at: string | null
  is_active: boolean
  is_compatible: boolean
  compatible_support_ids: UUID[]
  show_to_leasing_company?: boolean
  show_to_client?: boolean
  comment?: string | null
}

export const createSupportAdminApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  return {
    getMarks: async (_params?: { specialOffer?: string }) => {
      const response = await request<{ marks?: any[] }>('/api/v1/cars/facets?fields=marks')
      return response.marks || []
    },
    getModels: async (markId: string) => {
      const response = await request<{ models?: any[] }>(
        `/api/v1/cars/facets?fields=models&mark_id=${encodeURIComponent(markId)}`,
      )
      return response.models || []
    },
    getTrims: async (params?: { mark?: string; models?: string[] }) => {
      const fetchTrims = async (modelId?: string) => {
        const search = new URLSearchParams({ fields: 'trims' })
        if (params?.mark) search.set('mark_id', params.mark)
        if (modelId) search.set('model_id', modelId)
        const response = await request<{ trims?: any[] }>(`/api/v1/cars/facets?${search}`)
        return response.trims || []
      }
      const modelIds = Array.from(new Set((params?.models || []).filter(Boolean)))
      if (!modelIds.length) return fetchTrims()
      const trims = (await Promise.all(modelIds.map((modelId) => fetchTrims(modelId)))).flat()
      const uniqueTrims = new Map<string, any>()
      for (const trim of trims) {
        uniqueTrims.set(String(trim?.id ?? JSON.stringify(trim)), trim)
      }
      return Array.from(uniqueTrims.values())
    },
    getDealerGroups: () => request<{ dealer_groups: any[] }>('/api/v1/admin/dealer-groups?limit=200&is_active=true'),
    getDistributors: () => request<{ distributors: any[] }>('/api/v1/admin/distributors'),
    getDistributorInventoryBrands: (distributorId: UUID) =>
      request<{ brands: DistributorInventoryBrand[] }>(
        `/api/v1/admin/companies/${distributorId}/distributor-inventory-brands`,
      ),
    getLeasingCompanies: () => request<{ companies: any[] }>('/api/v1/admin/leasing-companies'),
    getSupportPrograms: async (params?: Record<string, string>) => {
      const query = params ? new URLSearchParams(params).toString() : ''
      const response = await request<{ support_programs: SupportProgram[]; pagination: any }>(
        `/api/v1/admin/support-programs${query ? `?${query}` : ''}`,
      )
      return {
        items: response.support_programs,
        pagination: response.pagination,
      }
    },
    getSupportProgramById: (id: UUID) => request<{ support_program: SupportProgram }>(`/api/v1/admin/support-programs/${id}`),
    deactivateSupportProgram: (id: UUID) =>
      request<{ support_program: SupportProgram; message: string }>(`/api/v1/admin/support-programs/${id}`, {
        method: 'PATCH',
        body: { active: false }
      }),
    activateSupportProgram: (id: UUID) =>
      request<{ support_program: SupportProgram; message: string }>(`/api/v1/admin/support-programs/${id}`, {
        method: 'PATCH',
        body: { active: true }
      }),
    deleteSupportProgram: (id: UUID) =>
      request<{ message: string }>(`/api/v1/admin/support-programs/${id}`, { method: 'DELETE' }),
    createSupportProgram: (payload: CreateSupportPayload) =>
      request<{ support_program: SupportProgram }>('/api/v1/admin/support-programs', { method: 'POST', body: payload }),
    updateSupportProgram: (id: UUID, payload: CreateSupportPayload) =>
      request<{ support_program: SupportProgram }>(`/api/v1/admin/support-programs/${id}`, { method: 'PUT', body: payload }),
    uploadBillOfLading: (supportProgramId: UUID, file: File, billDate?: string | null, comment?: string | null) => {
      const form = new FormData()
      form.append('file', file)
      if (billDate) form.append('bill_date', billDate)
      if (comment != null && comment !== '') form.append('comment', comment)
      return request<{ support_program: SupportProgram }>(`/api/v1/admin/support-programs/${supportProgramId}/bill-of-lading/upload`, {
        method: 'POST',
        body: form
      })
    },
    deleteBillOfLadingFile: (supportProgramId: UUID, fileId: UUID) =>
      request<{ support_program: SupportProgram }>(`/api/v1/admin/support-programs/${supportProgramId}/bill-of-lading/${fileId}`, {
        method: 'DELETE'
      })
  }
}
