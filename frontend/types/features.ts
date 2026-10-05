// ──────────────────────────────────────────────────────
// Shared interfaces for feature components
// ──────────────────────────────────────────────────────

import type { CatalogId, UUID } from './ids'

// ── Pagination ────────────────────────────────────────
export interface Pagination {
  page: number
  limit: number
  total: number
  pages: number
}

// ── Dealer ────────────────────────────��───────────────
export interface DealerClientStats {
  total_clients: number
  active_clients: number
  monthly_applications: number
  average_deal: number
}

export interface DealerClient {
  id: UUID
  name: string
  email: string
  phone?: string
  company_name?: string
  applications_count: number
  approved_applications_count: number
  total_amount: number
  last_activity_at: string
  is_active: boolean
}

export interface DealerProfile {
  dealership_name?: string
  contact_person?: string
  email?: string
  phone?: string
  inn?: string
  kpp?: string
  address?: string
  description?: string
  created_at?: string
  last_activity?: string
  working_hours?: Record<string, { enabled: boolean; open: string; close: string }>
  notification_settings?: Record<string, boolean>
  two_factor_enabled?: boolean
  [key: string]: unknown
}

export interface DealerReportsData {
  revenue: number
  revenue_change: number
  applications_count: number
  applications_change: number
  new_clients: number
  clients_change: number
  conversion_rate: number
  conversion_change: number
  top_models: DealerTopModel[]
  sales: DealerSale[]
  applications_stats: DealerApplicationStats
  applications: DealerApplication[]
  top_clients: DealerTopClient[]
  inventory_stats: DealerInventoryStats
}

export interface DealerTopModel {
  id: CatalogId
  rank: number
  brand: string
  model: string
  sales_count: number
  revenue: number
  percentage: number
}

export interface DealerSale {
  id: UUID
  brand: string
  model: string
  year: number
  client_name: string
  client_email: string
  amount: number
  sale_date: string
}

export interface DealerApplicationStats {
  active: number
  rejected: number
  issued: number
}

export type DealerApplicationStatus = 'active' | 'rejected' | 'issued'

export interface DealerApplication {
  id: UUID
  vehicles_count: number
  client_name: string
  client_email: string
  total_amount: number
  created_at: string
  status: DealerApplicationStatus
}

export interface DealerTopClient {
  id: UUID
  name: string
  applications_count: number
  total_amount: number
  average_deal: number
}

export interface DealerInventoryStats {
  total: number
  available: number
  reserved: number
  sold: number
  avg_sale_days: number
  fastest_sale: number
  slowest_sale: number
}

export interface DealerInventoryVehicle {
  id: UUID
  brand_name?: string
  model_name?: string
  year?: number
  vin?: string
  status?: string
  price?: number
  special_price?: number | null
  [key: string]: unknown
}

// ── Client ────────────────────────────────────────────
export interface ClientProfile {
  name?: string
  email?: string
  phone?: string
  birth_date?: string
  client_type?: string
  company_name?: string
  inn?: string
  kpp?: string
  ogrn?: string
  legal_address?: string
  address?: string
  created_at?: string
  last_activity?: string
  notification_settings?: Record<string, boolean>
  two_factor_enabled?: boolean
  [key: string]: unknown
}

export interface ClientProfileStats {
  total_applications: number
  approved_applications: number
  total_amount: number
  favorites_count: number
  saved_calculations: number
  documents_count: number
}

export interface LoginHistoryEntry {
  id: UUID
  ip_address: string
  user_agent: string
  login_at: string
  location: string
}

// ── Favorites ─────────────────────────────────────────
export interface FavoriteBrand {
  id: CatalogId
  name: string
}

export interface FavoriteItem {
  id?: UUID
  vehicle_id: UUID
  modification_id?: CatalogId
  brand_id?: CatalogId
  mark_id?: CatalogId
  model_id?: CatalogId
  brand_name?: string
  mark_name?: string
  model_name?: string
  main_image?: string | null
  images?: string[]
  price?: number
  base_price?: number
  special_price?: number | null
  discount_price?: number
  year?: number
  vehicle_year?: number
  engine_type?: string
  engine_capacity?: number
  horse_power?: number
  transmission?: string
  drive?: string
  configuration_name?: string
  group_name?: string
  color?: string
  added_at?: string
  [key: string]: unknown
}

// ── Notifications ─────────────────────────────────────
export type { NotificationItem as Notification, NotificationType } from '~/features/notifications/types'

// ── Admin: Companies ──────────────────────────────────
export type CompanyType = 'dealer' | 'leasing_company' | 'distributor' | 'other'

export interface Company {
  id: UUID
  name: string
  inn?: string
  kpp?: string
  ogrn?: string
  company_type: CompanyType
  phone?: string
  email?: string
  website?: string
  legal_address?: string
  actual_address?: string
  is_active: boolean
  can_manage_dealer_groups?: boolean
  user_count?: number
  application_count?: number
  created_at?: string
  [key: string]: unknown
}

export interface DealerGroup {
  id: UUID
  name: string
  description?: string | null
  distributor_company_id: UUID
  distributor?: DealerGroupCompany | null
  dealers: DealerGroupCompany[]
  dealer_company_ids: UUID[]
  dealers_count: number
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface DealerGroupCompany {
  id: UUID
  name: string
  inn?: string | null
}

// ─��� Admin: Users ──────────────────────────────────────
export type UserRole = 'client' | 'dealer' | 'leasing_company' | 'distributor' | 'carcraft_employee'

export interface AdminUser {
  id: UUID
  name: string
  email: string
  phone?: string
  role: UserRole
  company_name?: string
  company_inn?: string
  company_id?: UUID
  is_active: boolean
  created_at: string
}

// ── Admin: Leasing Companies ──────────────────────────
export interface LeasingCompany {
  id: UUID
  company_id?: UUID
  name: string
  inn?: string
  average_down_payment_percent?: number
  average_lease_term_months?: number
}

// ── Admin: Warehouses ─────────────────────────────────
export interface City {
  id: UUID
  name: string
}

export interface Warehouse {
  id: UUID
  name?: string
  owner_company_id?: string
  owner_company_type?: 'dealer' | 'distributor'
  owner_company_name?: string
  address: string
  brand?: string
  brand_ids?: string[]
  selected_brands?: { id: string; name: string }[]
  category_id?: string | null
  category_name?: string | null
  vehicle_marks?: string[]
  city_id?: UUID | null
  city_name?: string | null
  dealer_id?: UUID | null
  dealer_name?: string | null
  company_id?: UUID | null
  company_name?: string | null
  is_active?: boolean
  warehouse_access_type?: 'A' | 'B' | 'C'
  groups?: string[]
  vehicles_count?: number
  vehicle_types?: string[]
  sites?: string[]
  created_at?: string
  updated_at?: string
}

// ── Auth ──────────────────────────────────────────────
export interface UserFormData {
  name: string
  email: string
  phone: string
  role: string
  company_id: UUID | null
  is_active: boolean
}

export interface UserFormCompany {
  id: UUID
  name: string
  inn?: string
  company_type: CompanyType
}
