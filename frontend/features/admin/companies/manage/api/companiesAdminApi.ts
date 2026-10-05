import type { Company, CompanyType, DealerGroup, Pagination } from '~/types/features'
import type { CatalogId, UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

const ADMIN_DISTRIBUTOR_DEALERS_LIMIT = 200

export interface CreateCompanyPayload {
  name: string
  inn: string
  kpp?: string
  ogrn?: string
  company_type: 'dealer' | 'leasing_company' | 'distributor' | 'other'
  legal_address?: string
  phone?: string
  email?: string
}

export interface UpdateCompanyPayload extends Partial<CreateCompanyPayload> {
  is_active?: boolean
  can_manage_dealer_groups?: boolean
}

export type AdminCompanyUpdateField =
  | 'name'
  | 'company_type'
  | 'inn'
  | 'kpp'
  | 'ogrn'
  | 'is_active'
  | 'phone'
  | 'email'
  | 'website'
  | 'legal_address'
  | 'actual_address'

/** PATCH body for the company editor. Every property is optional because only changed fields are sent. */
export interface AdminCompanyUpdatePayload {
  name?: string
  company_type?: 'dealer' | 'leasing_company' | 'distributor' | 'other'
  inn?: string
  kpp?: string
  ogrn?: string
  is_active?: boolean
  phone?: string | null
  email?: string | null
  website?: string | null
  legal_address?: string
  actual_address?: string | null
}

/** Strict response and editor contract for an admin company detail. */
export interface AdminCompanyDetail {
  id: UUID
  name: string
  inn?: string
  kpp?: string
  ogrn?: string
  company_type: CompanyType
  phone?: string | null
  email?: string | null
  website?: string | null
  legal_address?: string | null
  actual_address?: string | null
  is_active?: boolean | null
  user_count?: number
  application_count?: number
  created_at?: string
}

export interface AdminCompanyValidationError {
  field: string
  code: string
  message: string
  blockers?: AdminCompanyTypeTransitionBlocker[]
}

/** User-safe details returned when a company type cannot be changed. */
export interface AdminCompanyTypeTransitionBlocker {
  label: string
  count: number
  resolution_hint: string
}

export interface AdminCompanyTypeTransitionConflict {
  detail: string
  code: string
  field_errors: AdminCompanyValidationError[]
  blockers: AdminCompanyTypeTransitionBlocker[]
}

export interface AdminCompanyUpdateResponse {
  company: AdminCompanyDetail
}

export type AdminCompanyChangeHistoryAction =
  | 'company_profile_saved'
  | 'company_status_changed'
  | 'distributor_brands_saved'
  | 'leasing_contractors_saved'

export interface AdminCompanyChangeHistorySnapshot {
  name: string | null
  company_type: string | null
  inn: string | null
  kpp: string | null
  ogrn: string | null
  is_active: boolean | null
  phone: string | null
  email: string | null
  website: string | null
  legal_address: string | null
  actual_address: string | null
  distributor_brands?: Array<{ id: string; name: string }>
  leasing_contractors?: Array<{ id: UUID; name: string; inn: string }>
}

export interface AdminCompanyChangeHistoryRecord {
  id: UUID
  changed_at: string
  actor_display_name: string
  action: AdminCompanyChangeHistoryAction
  snapshot: AdminCompanyChangeHistorySnapshot
}

export interface AdminCompanyChangeHistoryResponse {
  items: AdminCompanyChangeHistoryRecord[]
  pagination: { next_cursor: string | null; has_more: boolean }
}

export interface AdminCompanyChangeHistoryComparison {
  base: AdminCompanyChangeHistoryRecord
  target: AdminCompanyChangeHistoryRecord
  diffs: Array<{ field: string; old_value: unknown; new_value: unknown }>
}

export interface CreateDealerGroupPayload {
  name: string
  description?: string | null
  distributor_company_id: UUID
  dealer_company_ids: UUID[]
}

export type UpdateDealerGroupPayload = Partial<CreateDealerGroupPayload>

export interface DealerGroupFilters {
  distributor_id?: UUID | null
  dealer_id?: UUID | null
  search?: string | null
  is_active?: string | boolean | null
  page?: string | number | null
  limit?: string | number | null
}

export interface ContractorLinkItem {
  id: UUID
  leasing_company_id: UUID
  leasing_company_company_id?: UUID | null
  leasing_company_name?: string | null
  leasing_company_inn?: string | null
  contractor_id: UUID
  contractor_name: string
  contractor_inn: string
  created_at: string
  updated_at: string
}

export interface ContractorItem {
  id: UUID
  name: string
  inn: string
  created_at: string
  updated_at: string
}

export interface ContractorsResponse {
  items: ContractorItem[]
  pagination: {
    page: number
    limit: number
    total: number
    pages: number
  }
}

export interface ContractorLinksResponse {
  items: ContractorLinkItem[]
  pagination: {
    page: number
    limit: number
    total: number
    pages: number
  }
}

export interface CreateContractorLinkPayload {
  leasing_company_id: UUID
  contractor_name: string
  contractor_inn: string
}

export interface CreateContractorPayload {
  contractor_name: string
  contractor_inn: string
}

export interface UpdateContractorPayload {
  name: string
}

export interface ContractorImportResponse {
  rows_total: number
  links_created: number
  links_skipped: number
  contractors_created: number
  errors: Array<{ row: number; message: string }>
}

export interface LeasingCompanyOption {
  id: UUID
  company_id?: UUID | null
  name?: string | null
  inn?: string | null
  is_active?: boolean
}

export interface CurrentDistributorDealer {
  id: UUID
  name?: string | null
  inn?: string | null
}

export interface MyCompanyProfile {
  id: UUID
  name: string
  inn?: string | null
  company_type: Company['company_type']
  is_active?: boolean | null
  distributor?: {
    can_manage_dealer_groups?: boolean
  } | null
}

export interface DistributorBrandItem {
  id: CatalogId
  name: string
}

export interface DistributorBrandsResponse {
  available_brands: DistributorBrandItem[]
  selected_brand_ids: CatalogId[]
}

export interface UpdateDistributorBrandsPayload {
  brand_ids: CatalogId[]
}

export const createCompaniesAdminApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  const withQuery = (url: string, params?: Record<string, string | number | boolean | null | undefined>) => {
    const query = new URLSearchParams()
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') return
      query.set(key, String(value))
    })
    const suffix = query.toString()
    return suffix ? `${url}?${suffix}` : url
  }

  return {
    // Companies
    getCompanies: (params?: Record<string, string>) => {
      const query = params ? new URLSearchParams(params).toString() : ''
      return request<{ companies: Company[]; pagination: Pagination }>(`/api/v1/companies${query ? `?${query}` : ''}`)
    },
    createCompany: (payload: CreateCompanyPayload) =>
      request('/api/v1/admin/companies', { method: 'POST', body: payload }),
    updateCompany: (id: UUID, payload: UpdateCompanyPayload) =>
      request(`/api/v1/companies/${id}`, { method: 'PUT', body: payload }),
    patchAdminCompany: (id: UUID, payload: AdminCompanyUpdatePayload) =>
      request<AdminCompanyUpdateResponse>(`/api/v1/admin/companies/${id}`, {
        method: 'PATCH',
        body: payload
      }),
    getCompanyChangeHistory: (companyId: UUID, cursor?: string) =>
      request<AdminCompanyChangeHistoryResponse>(
        withQuery(`/api/v1/admin/companies/${companyId}/change-history`, { cursor })
      ),
    compareCompanyChangeHistory: (companyId: UUID, baseId: UUID, targetId: UUID) =>
      request<AdminCompanyChangeHistoryComparison>(
        withQuery(`/api/v1/admin/companies/${companyId}/change-history/compare`, {
          base_id: baseId,
          target_id: targetId
        })
      ),
    getCompanyById: (id: UUID) => request(`/api/v1/companies/${id}`),
    getMyCompanyProfile: () =>
      request<MyCompanyProfile>('/api/v1/companies/profile'),
    getAdminDistributors: () =>
      request<{ distributors: Company[] }>('/api/v1/admin/distributors'),
    getDistributorBrands: (companyId: UUID) =>
      request<DistributorBrandsResponse>(
        `/api/v1/admin/companies/${companyId}/distributor-brands`
      ),
    setDistributorBrands: (
      companyId: UUID,
      payload: UpdateDistributorBrandsPayload
    ) =>
      request<DistributorBrandsResponse>(
        `/api/v1/admin/companies/${companyId}/distributor-brands`,
        {
          method: 'PUT',
          body: payload
        }
      ),

    // Dealer Groups
    getDealerGroups: (params?: DealerGroupFilters) =>
      request<{ dealer_groups: DealerGroup[]; pagination: Pagination }>(
        withQuery('/api/v1/admin/dealer-groups', { limit: 200, ...params })
      ),
    getDealerGroup: (id: UUID) =>
      request<{ dealer_group: DealerGroup }>(`/api/v1/admin/dealer-groups/${id}`),
    getDealerCompanies: () =>
      request<{ companies: Company[]; pagination: Pagination }>(
        withQuery('/api/v1/companies', { company_type: 'dealer', limit: 500 })
      ),
    getDistributorCompanies: () =>
      request<{ companies: Company[]; pagination: Pagination }>(
        withQuery('/api/v1/companies', { company_type: 'distributor', limit: 500 })
      ),
    getCurrentDistributorDealers: () =>
      request<{ dealers: CurrentDistributorDealer[]; pagination: Pagination }>(
        withQuery('/api/v1/distributor/dealers', { limit: ADMIN_DISTRIBUTOR_DEALERS_LIMIT })
      ),
    getLeasingCompanies: () =>
      request<{ companies: LeasingCompanyOption[] }>('/api/v1/admin/leasing-companies'),
    createDealerGroup: (payload: CreateDealerGroupPayload) =>
      request('/api/v1/admin/dealer-groups', { method: 'POST', body: payload }),
    updateDealerGroup: (id: UUID, payload: UpdateDealerGroupPayload) =>
      request(`/api/v1/admin/dealer-groups/${id}`, { method: 'PATCH', body: payload }),
    deleteDealerGroup: (id: UUID) =>
      request(`/api/v1/admin/dealer-groups/${id}`, { method: 'DELETE' }),

    // Contractors
    getContractors: (params?: Record<string, string>) => {
      const query = params ? new URLSearchParams(params).toString() : ''
      return request<ContractorsResponse>(
        `/api/v1/admin/companies/contractors${query ? `?${query}` : ''}`
      )
    },
    createContractor: (payload: CreateContractorPayload) =>
      request<{ contractor: ContractorItem; created: boolean }>('/api/v1/admin/companies/contractors', {
        method: 'POST',
        body: payload
      }),
    getContractorLinks: (params?: Record<string, string>) => {
      const query = params ? new URLSearchParams(params).toString() : ''
      return request<ContractorLinksResponse>(
        `/api/v1/admin/companies/contractors/links${query ? `?${query}` : ''}`
      )
    },
    createContractorLink: (payload: CreateContractorLinkPayload) =>
      request('/api/v1/admin/companies/contractors/links', {
        method: 'POST',
        body: payload
      }),
    updateContractor: (contractorId: UUID, payload: UpdateContractorPayload) =>
      request(`/api/v1/admin/companies/contractors/${contractorId}`, {
        method: 'PATCH',
        body: payload
      }),
    unlinkContractor: (linkId: UUID) =>
      request(`/api/v1/admin/companies/contractors/links/${linkId}`, {
        method: 'DELETE'
      }),
    getLeasingCompanyContractors: (leasingCompanyId: UUID) =>
      request<{ items: ContractorLinkItem[] }>(
        `/api/v1/admin/companies/leasing-companies/${leasingCompanyId}/contractors`
      ),
    setLeasingCompanyContractors: (leasingCompanyId: UUID, contractorIds: UUID[]) =>
      request<{ items: ContractorLinkItem[] }>(
        `/api/v1/admin/companies/leasing-companies/${leasingCompanyId}/contractors`,
        {
          method: 'PUT',
          body: { contractor_ids: contractorIds }
        }
      ),
    getContractorLeasingCompanies: (contractorId: UUID) =>
      request<{ items: ContractorLinkItem[] }>(
        `/api/v1/admin/companies/contractors/${contractorId}/leasing-companies`
      ),
    setContractorLeasingCompanies: (contractorId: UUID, leasingCompanyIds: UUID[]) =>
      request<{ items: ContractorLinkItem[] }>(
        `/api/v1/admin/companies/contractors/${contractorId}/leasing-companies`,
        {
          method: 'PUT',
          body: { leasing_company_ids: leasingCompanyIds }
        }
      ),
    importContractorLinks: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<ContractorImportResponse>(
        '/api/v1/admin/companies/contractors/import',
        {
          method: 'POST',
          body: formData
        }
      )
    },

    // Distributor-Dealer Links
    getDistributorDealers: (
      distributorId: UUID,
      params?: { page?: number; limit?: number }
    ) =>
      request<{ dealers: Company[]; pagination: Pagination }>(
        withQuery(`/api/v1/admin/companies/distributors/${distributorId}/dealers`, {
          limit: ADMIN_DISTRIBUTOR_DEALERS_LIMIT,
          ...params
        })
      ),
    linkDistributorDealer: (distributorId: UUID, dealerCompanyId: UUID) =>
      request(`/api/v1/admin/companies/distributors/${distributorId}/dealers`, {
        method: 'POST',
        body: { dealer_company_id: dealerCompanyId }
      }),
    unlinkDistributorDealer: (distributorId: UUID, dealerCompanyId: UUID) =>
      request(`/api/v1/admin/companies/distributors/${distributorId}/dealers/${dealerCompanyId}`, {
        method: 'DELETE'
      })
  }
}
