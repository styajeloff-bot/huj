export type CompanyRole = 'leasing_company' | 'dealer' | 'distributor'
export type DocumentStatus = 'active' | 'expiring' | 'expired' | 'pending' | 'deactivated'
export interface RegistryCompany { company_id: string; leasing_company_id: string | null; role: CompanyRole; name: string; inn: string | null }
export interface CompanySelection { platform_ml: boolean; leasing_company_ids: string[]; dealer_company_ids: string[]; distributor_company_ids: string[]; companies?: RegistryCompany[] }
export interface Participants extends CompanySelection { mark_id: string | null; model_id: string | null; mark_name?: string | null; model_name?: string | null }
export interface CatalogItem { id: string; name: string; mark_id?: string }
export interface RegistryFile { id: string; name: string; type: string; size: number; download_url: string }
export interface RegistryVersion { id: string; version_number: number; name: string; related_companies: CompanySelection; is_current: boolean; metadata_backfilled: boolean; valid_from: string; valid_to: string | null; uploaded_by: { id: string; display_name: string }; uploaded_at: string; files: RegistryFile[] }
export interface VersionSnapshotInput { expected_current_version_id: string; name: string; related_companies: CompanySelection; valid_from: string; valid_to: string | null; retained_file_ids: string[] }
export interface ReferenceDocument { id: string; group_id: string; is_main: boolean; document_type: string; contract_number: string; name: string; related_companies: CompanySelection; status: DocumentStatus; active: boolean; current_version: RegistryVersion; version_count: number }
export interface DocumentGroup { group_id: string; participants: Participants; main_document: ReferenceDocument | null; display_document: ReferenceDocument; children_count: number; documents_count: number; counts_by_type: Record<string, number>; can_manage: boolean }
export interface TableRow extends DocumentGroup { related_documents: { id: string; document_type: string; contract_number: string; label: string; url: string }[] }
export interface Page<T> { items: T[]; pagination: { page: number; page_size: number; total: number } }
export interface CursorPage<T> { items: T[]; pagination: { has_more: boolean; next_cursor: string | null; limit: number } }
export interface RegistryType { code: string; name: string }
export interface RegistryFilters { search: string; document_type: string; mark_id: string; model_id: string; valid_from: string; valid_to: string; status: string; leasing_company_id: string; dealer_company_id: string; distributor_company_id: string; participant_scope: 'participants' | 'related' }
export interface DeletionUsages { document_ids: string[]; programs: { id: string; name: string }[]; fingerprint: string }
export interface MonetizationDocumentContext { leasing_company_id: string; dealer_company_id?: string | null; distributor_company_id?: string | null; mark_id?: string | null; model_id?: string | null; platform_ml: boolean }
export const emptyCompanies = (): CompanySelection => ({ platform_ml: false, leasing_company_ids: [], dealer_company_ids: [], distributor_company_ids: [] })
export const emptyParticipants = (): Participants => ({ ...emptyCompanies(), mark_id: null, model_id: null })
export const statusLabels: Record<DocumentStatus, string> = { active: 'Действует', expiring: 'Истекает', expired: 'Истёк', pending: 'Ещё не наступил', deactivated: 'Деактивирован' }
export const typeLabels: Record<string, string> = { contract: 'Договор', agreement: 'Соглашение', additional_agreement: 'Доп. соглашение', invoice: 'Счёт', act: 'Акт', power_of_attorney: 'Доверенность', other: 'Прочее' }
export const companyLabels: Record<CompanyRole, string> = { leasing_company: 'ЛК', dealer: 'Дилер', distributor: 'Дистрибьютор' }
export const dateLabel = (date: string | null) => date ? date.slice(0, 10).split('-').reverse().join('.') : 'бессрочно'
export function companyLines(value: CompanySelection): string[] {
  const lines = value.platform_ml ? ['Платформа МЛ'] : []
  for (const role of ['leasing_company', 'distributor', 'dealer'] as const) for (const item of value.companies ?? []) if (item.role === role) lines.push(`${companyLabels[role]} ${item.name}`)
  return lines
}
export function companyId(company: RegistryCompany): string | null { return company.role === 'leasing_company' ? company.leasing_company_id : company.company_id }
export function companyPayload(value: CompanySelection): CompanySelection { return { platform_ml: value.platform_ml, leasing_company_ids: [...value.leasing_company_ids], dealer_company_ids: [...value.dealer_company_ids], distributor_company_ids: [...value.distributor_company_ids] } }
