import type { UUID } from '~/types/ids'

/** Exact decimal string with kopeck precision, e.g. "1250000.00". Never a JS number. */
export type MoneyString = string

export type FastDealSource = 'dealer_to_leasing' | 'leasing_to_dealer'

export type FastDealStatus =
  | 'draft'
  | 'pending_lc_confirmation'
  | 'pending_lc_final_confirmation'
  | 'pending_dealer_confirmation'
  | 'pending_lc_changes_confirmation'
  | 'confirmed'
  | 'rejected'
  | 'cancelled'

export type LcApplicationStatus =
  | 'pending_review'
  | 'offer_sent'
  | 'selected_by_dealer'
  | 'confirmed'
  | 'rejected'
  | 'closed_not_selected'

export type FastDealParty = 'initiator' | 'leasing' | 'dealer' | 'distributor' | 'platform'

/** Actions that the server allows to the caller; the UI never derives them itself. */
export type FastDealAction =
  | 'edit'
  | 'delete'
  | 'cancel'
  | 'send_to_leasing_companies'
  | 'send_to_dealers'
  | 'submit_offer'
  | 'reject_as_leasing'
  | 'select_offer'
  | 'withdraw_selection'
  | 'confirm_as_leasing'
  | 'confirm_as_dealer'
  | 'reject_as_dealer'
  | 'send_changes'
  | 'accept_changes'
  | 'reject_changes'
  | 'upload_files'
  | 'assign_employees'
  | 'request_support'
  | 'apply_support'
  | 'decide_support'

export type FastDealFileKind = 'deal_main' | 'deal_additional' | 'lc_offer_pdf' | 'vehicle_offer'

export interface CompanyBrief {
  id: UUID
  name: string
  inn?: string | null
  kpp?: string | null
}

/** The company object selected in `CompanyAutocomplete` (`@select`), sent unchanged. */
export interface SelectedCompany {
  name: string
  inn: string
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  manager_name?: string | null
  [key: string]: unknown
}

export interface AssigneeOut {
  company_id: UUID
  user_id: UUID
  user_name?: string | null
  role: 'primary' | 'additional'
}

export interface OptionItem {
  code: string
  name?: string
  price: MoneyString
  comment?: string | null
}

export interface AppliedSupport {
  id: UUID
  name: string
  support_type: string
  support_amount: MoneyString
  base_amount?: MoneyString | null
  support_program_id?: UUID | null
  comment?: string | null
  /** Only a price-reducing program (vehicle discount) lowers the price; others drive compensations. */
  affects_price?: boolean
}

export interface SupportRequest {
  id: UUID
  status: 'requested' | 'pre_approved' | 'approved' | 'cancelled'
  requested_amount: MoneyString
  decided_amount?: MoneyString | null
  accounted_amount?: MoneyString
  comment?: string | null
  decision_comment?: string | null
  distributor_company_id?: UUID
  distributor_name?: string | null
  created_at?: string | null
  decided_at?: string | null
}

export interface FastDealVehicle {
  id: UUID
  position: number
  vehicle_source_type: 'product' | 'manual'
  vin: string
  vin_entered_manually: boolean
  mark_name: string
  model_name: string
  modification_name?: string | null
  trim_name?: string | null
  category_name?: string | null
  body_color_name?: string | null
  dealer_company_id?: UUID | null
  final_price: MoneyString
  equipments: OptionItem[]
  services: OptionItem[]
  purposes: string[]
  regions: string[]
  item_status: 'active' | 'removed' | 'replaced'
  replaced_by_id?: UUID | null
  // Directory ids: only the initiator and the DL dealer receive them (to prefill edit forms).
  product_id?: UUID | null
  category_id?: UUID | null
  mark_id?: UUID | null
  model_id?: UUID | null
  modification_id?: UUID | null
  trim_id?: UUID | null
  body_color_id?: UUID | null
  // Present for the dealer / platform projection only. A leasing company never gets them.
  is_reservable?: boolean
  reserved?: boolean
  base_price?: MoneyString | null
  adjustment_type?: 'discount' | 'markup' | null
  adjustment_amount?: MoneyString | null
  options_amount?: MoneyString | null
  support_amount?: MoneyString | null
  unaccounted_support?: MoneyString | null
  applied_supports?: AppliedSupport[] | null
  support_request?: SupportRequest | null
  can_request_support?: boolean | null
  support_hint?: string | null
}

export interface FastDealOffer {
  id: UUID
  financing_amount: MoneyString
  down_payment: MoneyString
  down_payment_percent?: MoneyString | null
  lease_term_months: number
  monthly_payment: MoneyString
  total_cost: MoneyString
  buyout_amount: MoneyString
  rate?: MoneyString | null
  markup?: MoneyString | null
  total_interest?: MoneyString | null
  vat_refund?: MoneyString | null
  profit_tax_savings?: MoneyString | null
  total_savings?: MoneyString | null
  optional_financial_terms?: Record<string, unknown>
  pdf_file_id?: UUID | null
  created_at: string
}

export interface FastDealLcApplication {
  id: UUID
  leasing_company: CompanyBrief
  status: LcApplicationStatus
  offer?: FastDealOffer | null
  rejection_reason?: string | null
  selected: boolean
}

export interface FastDealTerms {
  down_payment_mode?: 'amount' | 'percent' | null
  down_payment?: MoneyString | null
  down_payment_percent?: MoneyString | null
  lease_term_months?: number | null
  monthly_payment?: MoneyString | null
  monthly_payment_is_manual?: boolean
  calculated_monthly_payment?: MoneyString | null
  buyout_amount?: MoneyString | null
  total_cost?: MoneyString | null
  /** Vehicles total minus the advance (requested terms) / the financed amount of the final terms. */
  financing_amount?: MoneyString | null
}

export interface FastDealFile {
  id: UUID
  kind: FastDealFileKind
  filename: string
  content_type: string
  size_bytes: number
  fast_deal_vehicle_id?: UUID | null
  addressee_company_id?: UUID | null
  uploaded_by_company_id: UUID
  created_at: string
}

export interface FastDealHistoryItem {
  id: UUID
  event_type: string
  from_status?: string | null
  to_status?: string | null
  actor_name?: string | null
  actor_company_name?: string | null
  reason?: string | null
  changes?: Record<string, unknown> | null
  created_at: string
  /** Dealer side only: the invitation the event belongs to. */
  lc_application_id?: UUID | null
  lc_company_name?: string | null
  review_cycle?: number | null
  deal_version?: number | null
}

export interface PendingChange {
  vehicle_id: UUID
  vin?: string | null
  field: string
  before: unknown
  after: unknown
}

export interface FastDealCard {
  id: UUID
  display_number: string
  source_type: FastDealSource
  status: FastDealStatus
  version: number
  etag: string
  review_cycle: number
  group_id?: UUID | null
  client: CompanyBrief
  client_phone: string
  initiator_company: CompanyBrief
  dealer_company?: CompanyBrief | null
  leasing_company?: CompanyBrief | null
  requested_terms: FastDealTerms
  final_terms?: FastDealTerms | null
  vehicles_total: MoneyString
  confirmed_amount?: MoneyString | null
  has_pending_changes: boolean
  pending_changes: PendingChange[]
  status_reason?: string | null
  vehicles: FastDealVehicle[]
  lc_applications: FastDealLcApplication[]
  group_deals: {
    id: UUID
    display_number: string
    status: FastDealStatus
    dealer_company?: CompanyBrief | null
    vehicles_total?: MoneyString
    vehicle_count?: number
    is_current?: boolean
  }[]
  files: FastDealFile[]
  assignees: AssigneeOut[]
  history: FastDealHistoryItem[]
  allowed_actions: FastDealAction[]
  party: FastDealParty
  sent_at?: string | null
  confirmed_at?: string | null
  created_at: string
  updated_at: string
}

export interface FastDealListItem {
  id: UUID
  display_number: string
  source_type: FastDealSource
  status: FastDealStatus
  client: CompanyBrief
  initiator_company: CompanyBrief
  dealer_company?: CompanyBrief | null
  leasing_company?: CompanyBrief | null
  invited_lc_count: number
  vehicle_count: number
  vehicles_total: MoneyString
  assignees: AssigneeOut[]
  created_at: string
  updated_at: string
  kind: 'fast_deal'
}

export interface FastDealListResponse {
  items: FastDealListItem[]
  total: number
  page: number
  page_size: number
}

export interface FastDealFilters {
  number?: string
  client_inn?: string
  client_company_id?: UUID
  leasing_company_id?: UUID
  dealer_company_id?: UUID
  source_type?: FastDealSource
  status?: FastDealStatus
  page?: number
  page_size?: number
}

export interface FilterOptions {
  clients: CompanyBrief[]
  leasing_companies: CompanyBrief[]
  dealers: CompanyBrief[]
}

export interface CreateFastDealBody {
  company_id?: UUID
  company?: SelectedCompany
  client_phone: string
}

export interface AddVehicleBody {
  vehicle_source_type: 'product' | 'manual'
  product_id?: UUID
  vin?: string
  price?: MoneyString
  category_id?: UUID
  mark_id?: UUID
  model_id?: UUID
  modification_id?: UUID
  trim_id?: UUID
  mark_name?: string
  model_name?: string
  modification_name?: string
  trim_name?: string
  body_color_id?: UUID
  body_color_name?: string
  dealer_company_id?: UUID
}

export type PatchVehicleBody = Partial<Omit<AddVehicleBody, 'vehicle_source_type' | 'product_id'>> & {
  replace_with?: AddVehicleBody
}

export interface LeasingTermsBody {
  /** Rubles OR percent, never both. */
  down_payment?: MoneyString
  down_payment_percent?: MoneyString
  lease_term_months: number
  /** Manual monthly payment; omitted → calculated on the server. */
  monthly_payment?: MoneyString
  buyout_amount?: MoneyString
}

export interface OfferBody {
  financing_amount: MoneyString
  down_payment: MoneyString
  down_payment_percent?: MoneyString
  lease_term_months: number
  monthly_payment: MoneyString
  total_cost: MoneyString
  buyout_amount?: MoneyString
  rate?: MoneyString
  markup?: MoneyString
  total_interest?: MoneyString
  vat_refund?: MoneyString
  profit_tax_savings?: MoneyString
  total_savings?: MoneyString
  optional_financial_terms?: Record<string, string | number | null>
  pdf_file_id?: UUID
}

export interface OptionsBody {
  equipments: { code: string; price: MoneyString; comment?: string | null }[]
  services: { code: string; price: MoneyString; comment?: string | null }[]
  purposes: string[]
  regions: string[]
}

export interface VinLookupResult {
  found: boolean
  product?: Record<string, unknown> | null
  reserved: boolean
  reason?: string | null
}

export interface SupportProgramOption {
  id: UUID
  name: string
  support_type: string
  support_amount: MoneyString
  is_compatible: boolean
  applied: boolean
  affects_price?: boolean
  starts_at?: string | null
  ends_at?: string | null
}

/** `{ detail, code?, field?, vin?, source_number? }` as returned for failed requests. */
export interface FastDealErrorBody {
  detail: string
  code?: string
  field?: string
  vin?: string
  source_number?: string
}
