// =====================================================
// Shared domain interfaces for the frontend application
// =====================================================

import type { CatalogId, UUID } from './ids'
import type { ApplicationSourceType } from '~/features/applications/sourceType'

// --- API / Fetch helpers ---

export interface ApiError {
  data?: { error?: string }
  message?: string
  status?: number
}

export interface ApiSuccessResponse {
  success: boolean
  error?: string
  message?: string
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  limit: number
  pages?: number
}

// --- Auth / User ---

export interface UserInfo {
  id: UUID
  role?: string
  name?: string
  email?: string
  phone?: string
  company_name?: string
  companyNameOrInn?: string
  [key: string]: unknown
}

// --- Applications ---

export interface Application {
  id: UUID
  display_number?: string | null
  source_type?: ApplicationSourceType | null
  status: string
  created_at: string
  updated_at?: string
  user_id?: UUID
  user_name?: string
  company_name?: string
  inn?: string
  total_amount?: number
  down_payment?: number
  lease_term_months?: number
  monthly_payment?: number
  total_cost?: number
  total_interest?: number
  markup?: number
  rate?: number
  buyout_amount?: number
  total_savings?: number
  vehicle_details?: ApplicationVehicle[]
  leasing_company_applications?: LeasingCompanyApplication[]
  workflow_stage?: string
  completion_percentage?: number
  next_required_action?: string
  total_vehicles?: number
  total_documents?: number
  approved_documents?: number
  total_leasing_apps?: number
  approved_leasing_apps?: number
  applications_count?: number
  applications?: Application[]
  [key: string]: unknown
}

export interface ApplicationVehicle {
  id: UUID
  [key: string]: unknown
}

export interface LeasingCompanyApplication {
  id?: UUID
  status?: string
  [key: string]: unknown
}

// --- Application overview (status page) ---

export interface ApplicationOverview {
  id: UUID
  display_number?: string | null
  source_type?: ApplicationSourceType | null
  status: string
  workflow_stage?: string
  completion_percentage?: number
  next_required_action?: string
  created_at: string
  user_name?: string
  total_amount?: number
  total_vehicles?: number
  total_documents?: number
  approved_documents?: number
  total_leasing_apps?: number
  approved_leasing_apps?: number
  user_id?: UUID
  [key: string]: unknown
}

export interface ApplicationDocument {
  id: UUID
  document_type: string
  description?: string
  status: string
  uploaded_at?: string
  file_size?: number
  [key: string]: unknown
}

export interface LeasingApplication {
  id: UUID
  company_name?: string
  requested_amount?: number
  created_at?: string
  external_status?: string
  internal_status?: string
  [key: string]: unknown
}

export interface TimelineEvent {
  id: UUID
  type: string
  title: string
  description: string
  created_at: string
}

// --- Vehicles / Cars ---

export interface Vehicle {
  purchase_pending?: boolean
  sale_completed?: boolean
  reserved_until?: string | null
  id: UUID
  vin?: string
  mark_id?: CatalogId
  model_id?: CatalogId
  mark_name?: string
  model_name?: string
  brand_name?: string
  year?: number
  color?: string
  base_price?: number
  special_price?: number | null
  price?: number
  price_from?: number
  discount_price?: number
  status?: string
  images?: string[]
  main_image?: string
  trim_name?: string
  [key: string]: unknown
}

// --- Brands / Models ---

export interface Brand {
  id: CatalogId
  name: string
  country?: string
  [key: string]: unknown
}

export interface CarModel {
  id: CatalogId
  name: string
  year_from?: number
  year_to?: number
  [key: string]: unknown
}

export interface BrandStats {
  carsCount: number
  modelsCount: number | Set<string>
  minPrice: number
  maxPrice: number
  prices?: number[]
}

// --- Warehouse ---

export interface WarehouseStats {
  total_vehicles: number
  available_vehicles: number
  reserved_vehicles: number
  total_value: number
}

export interface WarehouseFilters {
  search: string
  brand: string
  status: string
  year: string
}

export interface WarehousePagination {
  page: number
  limit: number
  total: number
  pages: number
}

// --- DataTable ---

export interface DataTableColumn {
  key: string
  label: string
  sortable?: boolean
  hidden?: boolean
  type?: 'status' | 'currency' | 'date' | string
  className?: string
  formatter?: (value: unknown) => string
  placeholder?: string
}

export interface DataTableFilter {
  key: string
  label: string
  type?: string
  options?: Array<{ value: string; label: string }>
  placeholder?: string
}

export interface DataTableAction {
  key: string
  label: string
  icon?: object
  className?: string
  visible?: (item: Record<string, unknown>) => boolean
}

// --- Notifications ---

export type { NotificationItem, NotificationType } from '~/features/notifications/types'

export interface NotificationFilters {
  is_read: string
  type: string
  period: string
  page?: number
  limit?: number
}

export interface NotificationPagination {
  page: number
  limit: number
  total: number
  pages: number
}

// --- Status Management ---

export interface StatusTransition {
  to_status: string
  to_status_name: string
}

export interface StatusDefinition {
  status_code: string
  status_name: string
  [key: string]: unknown
}

export interface StatusHistoryEntry {
  id: UUID
  old_status?: string
  new_status: string
  status_name?: string
  change_reason?: string
  change_date: string
  changed_by_name?: string
  system_generated?: boolean
  [key: string]: unknown
}

export interface StatusUpdateBody {
  changeReason: string
  status?: string
  externalStatus?: string
  workflowStage?: string
}

// --- Bulk Edit ---

export interface BulkEditVehicle {
  id: UUID
  vin?: string
  base_price: number
  special_price?: number | null
  [key: string]: unknown
}

export interface BulkEditPayload {
  vehicle_ids: UUID[]
  operation_type: string
  reason: string
  price_operation?: string
  price_value?: number
  new_status?: string
  new_availability?: boolean
}

// --- Email settings ---

export interface EmailPreferences {
  application_status_emails: boolean
  document_request_emails: boolean
  document_status_emails: boolean
  leasing_approval_emails: boolean
  exchange_emails: boolean
  system_emails: boolean
  weekly_digest: boolean
  marketing_emails: boolean
  email_frequency: string
  updated_at?: string
}

export interface EmailStats {
  total_emails: number
  delivery_rate: number
  sent_emails: number
  failed_emails: number
  skipped_emails: number
  week_emails: number
  subscribers: number
  frequency_breakdown: Record<string, number>
  today_emails: number
}

// --- Groups ---

// --- Company ---

export interface CompanyInfo {
  id?: UUID
  name: string
  inn?: string
  [key: string]: unknown
}

// --- Window extensions ---

declare global {
  interface Window {
    ym?: (id: number, action: string, ...args: unknown[]) => void
  }

  const AOS: {
    init: (config: Record<string, unknown>) => void
  } | undefined
}

// --- Document Requirement ---

export interface DocumentRequirement {
  id: UUID
  name: string
  description?: string
  required: boolean
  format?: string
  max_size?: number
  status?: string
  [key: string]: unknown
}

// --- Toast / SearchableDropdown / Generic ---

export type PriceOperation = 'set' | 'increase_amount' | 'decrease_amount' | 'increase_percent' | 'decrease_percent' | 'set_discount'

export interface DropdownItem {
  [key: string]: unknown
}

// --- File types ---

export interface UploadedFile {
  id?: UUID
  name: string
  size: number
  file_name?: string
  file_size?: number
  [key: string]: unknown
}

// --- Modal ---

export type ModalSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'full'

// --- Admin Stats ---

export interface AdminStats {
  total_users: number
  total_companies: number
  total_applications: number
  total_application_amount: number
  client_users: number
  dealer_users: number
  leasing_company_users: number
  distributor_users: number
  carcraft_employee_users: number
  dealer_companies: number
  leasing_companies: number
  distributor_companies: number
  submitted_applications: number
  approved_applications: number
  applications_last_30_days: number
}
