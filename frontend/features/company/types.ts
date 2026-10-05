import type { UUID } from '~/types/ids'

/** A company suggestion returned from the /api/v1/company/search endpoint. */
export interface CompanySuggestion {
  inn: string
  name: string
  kpp?: string
  ogrn?: string
  legal_address?: string
  manager_name?: string
  entity_type?: string
  phone?: string
  email?: string
  [key: string]: unknown
}

/** Response wrapper for company search. */
export interface CompanySearchResult {
  items: CompanySuggestion[]
}

/** Company object as used in admin views (detail modal, list, etc.). */
export interface Company {
  id: UUID
  name: string
  inn?: string
  kpp?: string
  ogrn?: string
  company_type?: string
  legal_address?: string
  actual_address?: string
  phone?: string
  email?: string
  website?: string
  is_active?: boolean
  user_count?: number
  application_count?: number
  created_at?: string
  [key: string]: unknown
}

/** A user belonging to a company. */
export interface CompanyUser {
  id: UUID
  name: string
  email: string
  role: string
  is_active: boolean
  [key: string]: unknown
}

/** Response from the admin users endpoint filtered by company. */
export interface CompanyUsersResponse {
  users: CompanyUser[]
}

/** Known company types for label/color mapping. */
export type CompanyType = 'dealer' | 'leasing_company' | 'distributor' | 'other'

/** Known user roles for label/color mapping. */
export type UserRole = 'client' | 'dealer' | 'leasing_company' | 'distributor' | 'carcraft_employee'

/** Form data for creating a company via admin modal. */
export interface CompanyCreateForm {
  name: string
  inn: string
  kpp: string
  ogrn: string
  company_type: string
  legal_address: string
  phone: string
  email: string
}

/** Shape of the company profile form */
export interface CompanyProfileForm {
  name: string
  inn: string
  kpp: string
  ogrn: string
  company_type: string
  legal_address: string
  actual_address: string
  phone: string
  email: string
  website: string
  annual_revenue: number | null
  employee_count: string
  foundation_date: string
  business_activity: string
  bank_name: string
  account_number: string
  bic: string
}

/** Validation errors keyed by form field */
export type CompanyProfileErrors = Partial<Record<keyof CompanyProfileForm, string>>

/** DaData suggestion item */
export interface DadataSuggestion {
  value: string
  data: {
    inn: string
    kpp?: string
    address?: { value?: string }
    [key: string]: unknown
  }
}

/** Flat company profile payload returned by `GET /api/v1/companies[/:id]/profile`. */
export type CompanyProfileResponse = Record<string, unknown>
