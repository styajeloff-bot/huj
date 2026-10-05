import type { CatalogId, UUID } from '~/types/ids'

export type Participant = 'leasing' | 'dealer' | 'distributor' | 'platform'
export type SourceType = 'platform' | 'dealer_account' | 'exchange' | 'dealer_site' | 'distributor_site'
export type Role = 'carcraft_employee' | 'dealer' | 'distributor' | 'leasing_company'
export type DecimalString = string
export interface CatalogMark { id: CatalogId; ids: CatalogId[]; name: string }
export interface CatalogModel { id: CatalogId; name: string | null }
export interface CatalogModification { id: CatalogId; name: string }
export interface CatalogTrim { id: CatalogId; name: string | null; trim_name: string | null }
export interface Company { id: UUID; name: string; inn: string | null }
export interface Page<T> { items: T[]; pagination: { page: number; page_size: number; total: number; total_pages: number } }
export interface Document { id: UUID; file_name: string; download_url: string; uploaded_at?: string | null; revision?: number; outdated?: boolean; uploaded_by_role?: string }
export interface Support { id: UUID; name: string; documents: Document[]; compatible_programs: { id: UUID; name: string }[] }
export interface ConditionRow {
  local_id: string
  participant_type: Participant
  base_type: 'property_value' | 'expense_amount' | 'none'
  expense_ref: string | null
  calc_type: 'percent' | 'amount'
  value: DecimalString
  min: DecimalString | null
  max: DecimalString | null
  vat_excluded: boolean
}
export interface SourceBlock { local_id: string; source_type: SourceType; expenses: ConditionRow[]; incomes: ConditionRow[] }
export interface ProgramDraft {
  reference_document_ids?: UUID[]
  name: string
  leasing_company_id: UUID | null
  dealer_company_id: UUID | null
  distributor_company_id: UUID | null
  support_program_id: UUID | null
  brand: string | null
  model: string | null
  modification: string | null
  trim: string | null
  vin: string | null
  period_start: string
  period_end: string | null
  status: 'active' | 'inactive'
  sources: SourceBlock[]
}
export interface ConditionPair { local_id: string; expense: ConditionRow; incomes: ConditionRow[] }
export interface PairedSourceBlock { local_id: string; source_type: SourceType; pairs: ConditionPair[] }
export interface ProgramEditorDraft extends Omit<ProgramDraft, 'sources'> { sources: PairedSourceBlock[] }
export interface SavedConditionRow extends Omit<ConditionRow, 'id' | 'local_id'> { id: UUID; local_id: string | null }
export interface SavedSourceBlock { id: UUID; source_type: SourceType; expenses: SavedConditionRow[]; incomes: SavedConditionRow[] }
export interface Program extends Omit<ProgramDraft, 'sources'> {
  can_manage: boolean
  id: UUID
  leasing_company: Company | null
  dealer: Company | null
  distributor: Company | null
  support_program: Support | null
  sources: SavedSourceBlock[]
  contracts: Document[]
}
export interface ParticipantSummary { participant_type: Participant; company: Company | null }
export type ProgramSummary = Pick<Program, 'id' | 'name' | 'brand' | 'period_start' | 'period_end' | 'status'> & {
  expense_participants: ParticipantSummary[]
  income_participants: ParticipantSummary[]
}
export interface ProgramPage extends Page<ProgramSummary> { can_manage: boolean }
export type TermsInputMode = 'percent' | 'amount'
export type DealAdjustmentItem =
  | { deal_participant_amount_id: string; input_mode: 'percent'; new_percent: DecimalString }
  | { deal_participant_amount_id: string; input_mode: 'amount'; new_value: DecimalString }
export interface AmountRow {
  original_calc_type: 'percent' | 'amount' | null
  original_percent: DecimalString | null
  original_amount: DecimalString
  percent: DecimalString | null
  input_mode: TermsInputMode
  base_type: 'property_value' | 'expense_amount'
  calculation_base_amount: DecimalString | null
  has_new_conditions: boolean
  id: UUID
  program_source_id: UUID | null
  source_participant_id: UUID | null
  participant_type: Participant
  expense_ref_amount_id: UUID | null
  raw_amount: DecimalString
  amount: DecimalString
  clip: string | null
  applied_limit: DecimalString | null
  vat_excluded: boolean
}
export interface Confirmation { applicable: boolean; confirmed_at: string | null; confirmed_by: string | null; confirmed_by_name: string | null }
export interface Deal {
  id: UUID
  application_id?: UUID | null
  leasing_company_application_id?: UUID | null
  exchange_request_id?: UUID | null
  application_number: string | null
  created_at?: string | null
  program_name?: string | null
  source_type: SourceType
  brand: string | null
  dealer_company: Company | null
  client_company: Company | null
  leasing_company?: Company | null
  distributor_company?: Company | null
  base_amount: DecimalString
  status: 'pending_approval' | 'paid'
  expenses: AmountRow[]
  incomes: AmountRow[]
  confirmations: Record<'leasing' | 'dealer' | 'distributor', Confirmation>
  documents: Document[]
  revision: number
  has_new_conditions: boolean
  can_adjust: boolean
  can_confirm: boolean
  can_upload_documents: boolean
}
export type DealSummary = Pick<Deal, 'id' | 'application_number' | 'created_at' | 'source_type' | 'brand' | 'dealer_company' | 'client_company' | 'leasing_company' | 'base_amount' | 'status' | 'confirmations'> & {
  expense_participants: ParticipantSummary[]
  income_participants: ParticipantSummary[]
}
export interface ConditionRequest {
  application_id: UUID
  application_number: string | null
  id: UUID
  leasing_company: Company | null
  dealer_company: Company
  requested_calc_type: 'percent' | 'amount'
  requested_value: DecimalString
  status: 'sent' | 'accepted' | 'rejected' | 'countered'
  counter_calc_type: 'percent' | 'amount' | null
  counter_value: DecimalString | null
}
