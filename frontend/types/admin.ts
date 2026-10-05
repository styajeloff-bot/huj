import type { ApplicationSourceType } from '~/features/applications/sourceType'
import type { UUID } from './ids'
import type { CommerceApplicationItem } from '~/features/commerce/types'

// ── Support Programs ──

export interface SupportParams {
  value_type: 'amount' | 'percent'
  value: number
  min_amount: number | null
  max_amount: number | null
  min_percent: number | null
  max_percent: number | null
  compensation_period_months: number | null
  start_month: number | null
}

export interface SupportDealerGroup {
  id: UUID
  name: string
}

export interface SupportLeasingCompany {
  id: UUID
  name: string
}

export interface BillOfLadingFile {
  id: UUID
  file_name?: string
  file_path?: string
  file_size?: number
  bill_date?: string
}

export interface BillOfLading {
  id: UUID | null
  bill_date?: string
  comment?: string
  file_name?: string
  file_path?: string
  file_size?: number
  files: BillOfLadingFile[]
}

export interface SupportProgram {
  id: UUID
  name: string
  comment?: string | null
  mark_id?: string | null
  mark_ids?: string[]
  mark_name?: string | null
  model_id?: string | null
  model_ids?: string[]
  model_name?: string | null
  complectation_ids?: string[]
  production_date_from?: string | null
  production_date_to?: string | null
  delivery_date_from?: string | null
  delivery_date_to?: string | null
  production_year_from?: number | null
  production_year_to?: number | null
  vin?: string | null
  vins?: string[]
  dealer_group_id?: UUID | null
  dealer_group_ids?: UUID[]
  dealer_group_name?: string | null
  dealer_groups?: SupportDealerGroup[]
  distributor_id?: UUID | null
  distributor_ids?: UUID[]
  distributor_name?: string | null
  distributors?: Array<{ id: UUID; name: string }>
  leasing_companies?: SupportLeasingCompany[]
  leasing_company_ids?: UUID[]
  support_type: string
  support_params: SupportParams
  starts_at?: string | null
  ends_at?: string | null
  is_active: boolean
  is_compatible: boolean
  compatible_support_ids: UUID[]
  status?: 'active' | 'inactive' | 'completed' | string
  show_to_leasing_company?: boolean
  show_to_client?: boolean
  bill_of_lading?: BillOfLading | null
  created_at?: string | null
  updated_at?: string | null
  compensation_templates?: Array<{
    id?: UUID
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
}


// ── Catalog Upload ──

export interface CatalogPreviewData {
  totalRows: number
  uniqueMarks: number
  uniqueModels: number
  vehiclesCount: number
  rowsWithoutVin: number
  gdriveImages?: { unique: number } | null
  sampleData?: Array<{
    vin?: string
    mark?: string
    model?: string
    generation?: string
    price?: number
    hasVin?: boolean
  }>
  errors?: string[]
  warnings?: string[]
  hasErrors?: boolean
}

// ── Featured Items ──

export interface FeaturedItem {
  id: UUID
  model_id: string
  mark_name: string
  model_name: string
  is_active?: boolean
  is_eligible: boolean
}

export interface FeaturedMark {
  id: string
  name: string
}

export interface FeaturedModel {
  model_id: string
  mark_name: string
  model_name: string
  available_count: number
  min_price?: number | null
  is_featured: boolean
}

// ── Vehicles ──

export interface AdminVehicle {
  purchase_pending?: boolean
  sale_completed?: boolean
  reserved_until?: string | null
  id: UUID
  vin?: string
  mark_id?: string
  mark_name?: string
  mark_cyrillic?: string
  mark_cyrillic_name?: string
  model_id?: string
  model_name?: string
  model_cyrillic?: string
  model_cyrillic_name?: string
  generation_name?: string
  year?: number
  vehicle_year?: number
  color?: string
  status?: string
  base_price?: number
  special_price?: number | null
  discount_price?: number | null
  body_type?: string
  doors_count?: number
  engine_volume?: number
  engine_power?: number
  fuel_type?: string
  transmission?: string
  drive_type?: string
  is_available?: boolean
  distributor_name?: string
  distributor_company_name?: string
  images?: string[]
  created_at?: string
  updated_at?: string
  current_warehouse_address?: string
  bound_at?: string
  complectation_name?: string
  group_name?: string
  total_price?: number
  unit_price?: number
  quantity?: number
  assigned_vin?: string
  vehicle_vin?: string
  dealer_name?: string
  dealer_id?: UUID | null
  distributor_id?: UUID | null
  vehicle_id?: UUID | null
  support_type?: string | null
  support_amount?: number | null
  support_program_id?: UUID | null
  support_program_ids?: UUID[]
  support_program_info?: {
    name?: string | null
    bill_of_lading?: unknown
  } | null
  price?: number
  generation_id?: string
  configuration_id?: string
  complectation_id?: string
}

export interface VehicleHistoryRecord {
  id: number
  action: string
  created_at: string
  user_name?: string
}

export interface VehicleMark {
  id: string
  name: string
  cyrillic_name?: string
}

export interface VehicleModel {
  id: string
  name: string
  cyrillic_name?: string
}

export interface VehicleTrim {
  id: string
  name?: string
  trim_name?: string
}

// ── Warehouses ──

export interface Warehouse {
  id: UUID
  address: string
  brand: string
  company_name: string
  dealer_id?: UUID | null
  dealer_name?: string | null
  vehicles_count?: number
}

export interface AvailableDealer {
  id: UUID
  name: string
  email: string
  company_name?: string
  inn?: string
}

// ── Applications ──

export interface ApplicationCompanyInfo {
  company_id: UUID
  company_name: string
}

export interface AdminApplication {
  id: UUID
  display_number?: string
  source_type?: ApplicationSourceType | null
  company_id?: UUID
  name: string
  email?: string
  phone?: string
  company_name?: string
  company_inn?: string
  status: string
  total_amount?: number | null
  down_payment?: number | null
  total_vehicles_price?: number | null
  vehicles_count?: number | null
  items_count?: number | null
  total_items_price?: number | null
  down_payment_percent?: number | null
  lease_term_months?: number | null
  monthly_payment?: number | null
  current_stage?: string | null
  selected_companies_info?: ApplicationCompanyInfo[]
  selected_leasing_companies?: string[]
  pending_price_items_count?: number
  can_assign_leasing_companies?: boolean
  created_at?: string
  updated_at?: string
}

export interface AdminApplicationDetailApplication extends AdminApplication {
  selected_companies_info?: ApplicationCompanyInfo[]
  selected_leasing_companies?: string[]
  items_count?: number | null
  total_items_price?: number | null
  vehicle_price_items?: AdminApplicationVehiclePriceItem[]
  items?: CommerceApplicationItem[]
}

export interface AdminApplicationPriceChange {
  id: UUID
  item_id: UUID
  item_title?: string | null
  old_price: string | null
  new_price: string
  changed_by: UUID
  changed_by_name?: string | null
  changed_at: string
  source: 'dealer_ui' | 'api' | string
}

export interface AdminApplicationPriceChangesResponse {
  items: AdminApplicationPriceChange[]
  total: number
}

export interface AdminApplicationVehiclePriceItem {
  type: 'vehicle'
  id: UUID
  item_id?: UUID | null
  vehicle_id?: UUID | null
  title: string
  image_url?: string | null
  detail_url?: string | null
  quantity: number
  unit_price?: number | null
  catalog_price?: number | null
  show_catalog_price?: boolean | null
  discount_type?: string | null
  discount_value?: number | null
  discount_amount?: number | null
  markup_type?: string | null
  markup_value?: number | null
  markup_amount?: number | null
  final_price?: number | null
  total_price?: number | null
  dealer_comment?: string | null
  currency_code?: string
  status?: string | null
  snapshot?: Record<string, unknown> | null
}

export interface AdminApplicationDetailLeasingCompany {
  id?: UUID | null
  name?: string | null
  inn?: string | null
}

export interface AdminApplicationDetailProposal {
  id: UUID
  leasing_company_application_id: UUID
  kind?: string | null
  position?: number | null
  total_amount?: number | null
  down_payment?: number | null
  down_payment_percent?: number | null
  lease_term_months?: number | null
  monthly_payment?: number | null
  total_cost?: number | null
  markup?: number | null
  rate?: number | null
  total_interest?: number | null
  buyout_amount?: number | null
  vat_refund?: number | null
  profit_tax_savings?: number | null
  total_savings?: number | null
  client_decision_action?: string | null
  client_decision_at?: string | null
  client_decision_comment?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface AdminApplicationDetailLeasingCompanyApplication {
  id: UUID
  application_id?: UUID | null
  leasing_company_id?: UUID | null
  status?: string | null
  review_notes?: string | null
  decision_comment?: string | null
  response_pdf_file_name?: string | null
  response_pdf_size?: number | null
  response_pdf_uploaded_at?: string | null
  submitted_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  leasing_company?: AdminApplicationDetailLeasingCompany | null
  proposals?: AdminApplicationDetailProposal[]
}

export interface AdminApplicationDetailResponse {
  application: AdminApplicationDetailApplication
  leasing_company_applications: AdminApplicationDetailLeasingCompanyApplication[]
}

// ── Users ──

export interface AdminUser {
  id: UUID
  name: string
  email?: string
  role: string
  company_name?: string
  company_inn?: string
  is_active: boolean
  created_at: string
}

// ── Companies ──

export type CompanyType = 'dealer' | 'leasing_company' | 'distributor' | 'other'

export interface AdminCompany {
  id: UUID
  name: string
  inn?: string
  company_type: CompanyType
  phone?: string
  email?: string
  is_active: boolean
  user_count?: number
}

// ── Dealer Groups ──

export interface DealerCompanyRef {
  id: UUID
  name: string
  inn?: string | null
}

export interface DealerGroup {
  id: UUID
  name: string
  description?: string | null
  distributor_company_id: UUID
  distributor?: DealerCompanyRef | null
  dealers: DealerCompanyRef[]
  dealer_company_ids: UUID[]
  dealers_count: number
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

// ── Stats ──

export interface AdminStats {
  total_users: number
  total_companies: number
  total_applications: number
  total_application_amount: number
  client_users: number
  dealer_users: number
  leasing_company_users: number
  distributor_users: number
  carcraft_employee_users?: number
  dealer_companies: number
  leasing_companies: number
  distributor_companies: number
  submitted_applications: number
  approved_applications: number
  applications_last_30_days: number
}

// ── Leasing Companies ──

export interface LeasingCompany {
  id: UUID
  company_id: UUID
  name: string
  inn: string
  average_down_payment_percent?: number
  average_lease_term_months?: number
}

// ── Import Vehicles ──

export interface ImportUploadResult {
  success: boolean
  message: string
  stats?: {
    inserted: number
    updated: number
    skipped: number
  }
}

// ── Inventory Check ──

export interface InventoryDiscrepancy {
  id: number
  vin: string
  issue: string
}

export interface InventoryResults {
  checked: number
  confirmed: number
  discrepancies: number
  updated: number
  discrepancyDetails?: InventoryDiscrepancy[]
}

export interface LastInventory {
  date: string
  checked: number
  discrepancies: number
  responsible: string
}

// ── Pagination ──

export interface Pagination {
  page: number
  limit: number
  total: number
  pages: number
}

// ── Bind Stats ──

export interface BindStats {
  bound: number
  moved: number
  skipped?: number
}

export interface BulkBindVehiclesResponse {
  bound: number
  skipped: number
}

// ── Support View Modal type labels map ──

export type SupportType =
  | 'down_payment_compensation'
  | 'vehicle_discount_dealer_compensation'
  | 'vehicle_discount_dealer_invoice'
  | 'leasing_interest_compensation'

export type ApplicationStatus = 'active' | 'rejected' | 'issued'

// ── VIN Vehicle (used in support create) ──

export interface VinVehicle {
  id: UUID
  vin: string
  mark_name?: string
  model_name?: string
  year?: number
}
