import type { UUID } from '~/types/ids'
import type { Company } from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Request interfaces
// ---------------------------------------------------------------------------

export interface CompanySearchQuery {
  q: string
  limit?: number
}

export interface CompanyProfileRequest {
  inn?: string
  kpp?: string
  ogrn?: string
  name?: string
  legal_address?: string
  actual_address?: string
  phone?: string
  email?: string
  manager_name?: string
  entity_type?: string
  [key: string]: unknown
}

export interface ExternalDataPayload {
  egrul_data?: Record<string, unknown> | null
  nalog_data?: Record<string, unknown> | null
  fssp_data?: Record<string, unknown> | null
  fetch_attempts?: number
  last_fetch_error?: string | null
  website?: string | null
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface CompanySearchItem {
  inn: string
  name: string
  kpp?: string
  ogrn?: string
  address?: string
  [key: string]: unknown
}

export interface CompanySearchResponse {
  suggestions: CompanySearchItem[]
}

export type CompanyProfileResponse = Company

export interface UpsertCompanyProfileResponse {
  message: string
  company_id: UUID
  company: Company
}

export interface CompaniesListResponse {
  companies: Company[]
}

export interface LeasingCompaniesResponse {
  success: boolean
  companies: Company[]
}

export type CompanySubRole = 'administrator' | 'manager' | 'employee'

export interface UserCompany {
  id: UUID
  name: string
  inn?: string | null
  sub_role?: CompanySubRole | null
  can_view_applications?: boolean
  can_create_applications?: boolean
  canViewApplications?: boolean
  canCreateApplications?: boolean
}

export interface UserCompaniesResponse {
  companies: UserCompany[]
}

export interface AddMyCompanyResponse {
  message: string
  company_id: UUID
  companies: UserCompany[]
}

export interface CompanySelectHistoryResponse {
  company_id: UUID | null
  updated_at?: string | null
}

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createCompanyApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    /** Search companies via DaData (public, used during registration). */
    search: (query: CompanySearchQuery) =>
      request<CompanySearchResponse>('/api/v1/company/search', {
        method: 'GET',
        params: query,
      }),

    /** Get the current user's company profile. */
    getProfile: () =>
      request<CompanyProfileResponse>('/api/v1/companies/profile'),

    /** Create or update the current user's company profile. */
    saveProfile: (body: CompanyProfileRequest) =>
      request<UpsertCompanyProfileResponse>('/api/v1/companies/profile', {
        method: 'POST',
        body,
      }),

    /** List all companies (used for admin user-form dropdowns). */
    listCompanies: () =>
      request<CompaniesListResponse>('/api/v1/companies'),

    /** List leasing companies for application filters. */
    listLeasingCompanies: () =>
      request<LeasingCompaniesResponse>('/api/v1/companies?type=leasing'),

    /** List companies belonging to the current user. */
    getMyCompanies: () =>
      request<UserCompaniesResponse>('/api/v1/users/me/companies'),

    /** Add a company to the current user's profile. */
    addMyCompany: (company: Record<string, unknown>) =>
      request<AddMyCompanyResponse>('/api/v1/users/me/companies', {
        method: 'POST',
        body: { company },
      }),

    getCompanySelectHistory: () =>
      request<CompanySelectHistoryResponse>('/api/v1/users/me/company-select-history'),

    setCompanySelectHistory: (companyId: UUID) =>
      request<CompanySelectHistoryResponse>('/api/v1/users/me/company-select-history', {
        method: 'PUT',
        body: { company_id: companyId },
      }),

    /** Update external data for a specific company. */
    updateExternalData: (companyId: UUID, body: ExternalDataPayload) =>
      request<void>(`/api/v1/companies/${companyId}/external-data`, {
        method: 'PUT',
        body,
      }),
  }
}
