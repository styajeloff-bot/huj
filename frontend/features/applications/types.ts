import type { ApplicationSourceType } from '~/features/applications/sourceType'
/** Shared interfaces for application feature components */

import type { CatalogId, UUID } from '~/types/ids'
import type { SupportBadgeProgram } from '~/types/support'
import type { AdditionalOptionPrice } from './additionalOptionPrice'

export interface WarehouseInfo {
  id?: UUID | null
  address?: string | null
  brand?: string | null
  city?: string | null
  company_id?: UUID | null
  company_name?: string | null
}

export interface AssignableDealer {
  id: UUID
  name: string
  inn?: string | null
  brands: string[]
}

export interface DealerGroup {
  id: UUID
  name: string
  dealers: AssignableDealer[]
}

export interface EmployeeOption {
  id: UUID
  name?: string | null
  phone?: string | null
  sub_role?: string | null
}

export type AssignedEmployee = EmployeeOption

/** Document requirement used in wizard steps (matches DocumentRequirement.vue's DocRequirement) */
export interface DocRequirement {
  id?: UUID
  name?: string
  display_name: string
  description?: string
  document_type: string
  required?: boolean
  is_required?: boolean
  is_mandatory?: boolean
  validation_rules?: { max_files?: number }
  [key: string]: unknown
}

/** User document (matches DocumentRequirement.vue's UserDocument) */
export interface UserDocument {
  id: UUID
  file_name: string
  uploaded_at: string
  status?: string
  [key: string]: unknown
}

/** File upload event payload */
export interface FileUploadPayload {
  documentType: string
  files?: File | File[]
  file?: File
}

/** Map of document type -> uploaded file(s) or selected doc id */
export type DocumentFileMap = Record<string, File | File[] | null>
export type DocumentSelectionMap = Record<string, UUID | null>

/** Generic success/message response from API actions */
export interface ActionApiResponse {
  success?: boolean
  message?: string
  types?: RequestedDocument[]
  [key: string]: unknown
}

/** Status config entry for ApplicationStatusBadge */
export interface StatusConfigEntry {
  text: string
  class: string
  icon: boolean
}

/** Stage labels map for ApplicationCard */
export type StageKey = 'leasing_companies' | 'documents' | 'questionnaire' | 'pdf'

/** Badge size */
export type BadgeSize = 'xs' | 'sm' | 'md' | 'lg'

export interface VinItem {
  vehicle_id?: UUID
  vin?: string
}

export interface SupportBillOfLading {
  file_path?: string
  file_name?: string
  bill_date?: string
}

export interface SupportProgramInfo {
  name?: string
  bill_of_lading?: SupportBillOfLading
}

export interface DealerActionDocument {
  id?: UUID
  application_vehicle_id?: UUID
  action?: string
  file_url: string
  file_key?: string
  file_name: string
  file_type?: string | null
  uploaded_by?: UUID | null
  created_at?: string | null
}

export interface AdditionalEquipmentSelection {
  equipment_code: string
  price?: AdditionalOptionPrice
  comment?: string | null
}

export interface AdditionalServiceSelection {
  service_code: string
  price?: AdditionalOptionPrice
  comment?: string | null
}

export interface ApplicationVehicle {
  id?: UUID
  application_vehicle_id?: UUID
  vehicle_id?: UUID
  modification_id?: CatalogId
  complectation_id?: CatalogId
  mark_name?: string
  mark?: string
  model_name?: string
  model?: string
  group_name?: string
  configuration_name?: string
  color?: string
  vehicle_year?: number
  year?: number
  quantity?: number
  unit_price?: number
  total_price?: number
  price_from?: number
  base_price?: number
  discount_price?: number
  custom_price?: number
  vin?: string
  vins?: VinItem[]
  support_type?: string
  support_program_info?: SupportProgramInfo
  comment?: string
  equipments?: AdditionalEquipmentSelection[]
  services?: AdditionalServiceSelection[]
  leasing_purpose?: string | null
  leasing_purposes?: string[] | null
  regions?: string[] | null
  region?: string | null
  status?: string
  car_status?: string
  dealer_comment?: string | null
  reserve_expires_at?: string | null
  discount_type?: string | null
  discount_value?: number | null
  markup_type?: string | null
  markup_value?: number | null
  final_price?: number | null
  engine?: string | null
  engine_type?: string | null
  transmission?: string | null
  drive?: string | null
  catalog_price?: number | null
  catalog_price_from?: number | null
  catalog_price_to?: number | null
  dealer_name?: string | null
  dealer_company_id?: UUID | null
  assigned_dealer?: Omit<AssignableDealer, 'brands'> | null
  dealer_assigned_by_id?: UUID | null
  dealer_assigned_by?: { id: UUID; name?: string | null } | null
  dealer_assigned_at?: string | null
  primary_employee_id?: UUID | null
  primary_employee?: AssignedEmployee | null
  additional_employee_id?: UUID | null
  additional_employee?: AssignedEmployee | null
  employees_assigned_by_id?: UUID | null
  employees_assigned_by?: { id: UUID; name?: string | null } | null
  employees_assigned_at?: string | null
  warehouse?: WarehouseInfo | null
  warehouse_address?: string | null
  dealer_action_documents?: DealerActionDocument[]
}

export interface VehicleCalculation {
  vehicle_id?: UUID
  modification_id?: CatalogId
  complectation_id?: CatalogId
  color?: string
  unit_price?: number
  total_amount?: number
  down_payment_percent?: number
  down_payment?: number
  lease_term_months?: number
  calculation?: {
    monthlyPayment?: number
    rate?: number
    totalCost?: number
    totalInterest?: number
    buyoutAmount?: number
    vatRefund?: number
    profitTaxSavings?: number
    totalSavings?: number
  }
}

export interface SupportData {
  vehicle_discount_support?: number
  dealer_commission_support?: number
  down_payment_support?: number
  interest_support?: number
}

export interface ApplicationDataExtra {
  support?: SupportData
  per_vehicle_calculations?: VehicleCalculation[]
}

export interface ApplicationCalculationData extends SupportData {
  support?: SupportData
  support_per_vehicle?: Array<{
    vehicle_id?: UUID
    base_price?: number
    applied_supports?: Array<{
      support_program_id?: UUID
      type?: string
      amount?: number
    }>
  }>
  support_per_program?: Array<{
    support_program_id?: UUID | null
    name?: string | null
    support_name?: string | null
    support_program_name?: string | null
    type?: string | null
    support_params?: Record<string, unknown> | null
    price_conditions?: string | null
    pricing_conditions?: string | null
    totals?: {
      amount?: string | number | null
    } | null
  }>
  support_program_details?: SupportBadgeProgram[]
  calculations_per_vehicle?: VehicleCalculation[]
}

export interface RequestedDocument {
  type_code?: string
  display_name?: string
  name?: string
  status?: string
  file_types?: string[]
}

export interface ApplicationDocument {
  id: UUID
  file_name: string
  document_type?: string
  uploaded_at?: string
  status?: string
  file_size?: number
}

export interface RequestedDocStatus {
  document_type?: string
  status?: string
  uploaded_file_name?: string
  uploaded_document_id?: UUID
}

export interface ApplicationData {
  id?: UUID
  display_number?: string | null
  source_type?: ApplicationSourceType | null
  status?: string
  application_status?: string | null
  application_status_label?: string | null
  group_status?: string | null
  group_status_label?: string | null
  created_at?: string
  client_visible_comment?: string
  client_comment_updated_at?: string
  name?: string
  phone?: string
  email?: string
  can_assign_dealer?: boolean
  dealer_company_id?: UUID | null
  assigned_dealer?: Omit<AssignableDealer, 'brands'> | null
  assigned_dealer_group_id?: UUID | null
  dealer_assigned_by_id?: UUID | null
  dealer_assigned_by?: { id: UUID; name?: string | null } | null
  dealer_assigned_at?: string | null
  primary_employee_id?: UUID | null
  primary_employee?: AssignedEmployee | null
  additional_employee_id?: UUID | null
  additional_employee?: AssignedEmployee | null
  employees_assigned_by_id?: UUID | null
  employees_assigned_by?: { id: UUID; name?: string | null } | null
  employees_assigned_at?: string | null
  vehicles?: ApplicationVehicle[]
  requested_documents?: RequestedDocument[]
  down_payment_percent?: number
  down_payment?: number
  lease_term_months?: number
  monthly_payment?: number
  rate?: number
  total_cost?: number
  total_interest?: number
  buyout_amount?: number
  vat_refund?: number
  profit_tax_savings?: number
  total_savings?: number
  application_data?: ApplicationDataExtra
  calculation?: ApplicationCalculationData | null
  vehicle_calculations?: VehicleCalculation[]
  [key: string]: unknown
}

export interface LeasingApplication {
  id: UUID
  company_name?: string
  external_status?: string
}

/** Application list item used in ApplicationManager table */
export interface ApplicationListItem {
  id: UUID
  status?: string
  user_name?: string
  vehicle_count?: number
  total_value?: number
  completion_percentage?: number
  workflow_stage?: string
  created_at?: string
  leasing_applications?: LeasingApplication[]
  [key: string]: unknown
}

export interface LeasingCompany {
  id: UUID
  name: string
}

export interface Dealer {
  id: UUID
  name: string
}

export interface TableColumn {
  key: string
  label: string
  type?: string
  sortable?: boolean
}

export interface TableAction {
  key: string
  label: string
  icon?: string
  className?: string
}

export interface ApiResponse {
  success?: boolean
  applications?: ApplicationListItem[]
  data?: ApplicationListItem[]
  companies?: LeasingCompany[]
  users?: Dealer[]
  updated?: number
  documents?: ApplicationDocument[]
  documentRequests?: RequestedDocStatus[]
  vehicles?: ApplicationVehicle[]
  download_url?: string
  [key: string]: unknown
}
