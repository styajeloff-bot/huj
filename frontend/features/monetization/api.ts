import { withApiCompanyContext, withNotificationCompanyContext } from '~/utils/apiCompanyContext'
import type { CatalogMark, CatalogModel, CatalogModification, CatalogTrim, Company, ConditionRequest, Deal, DealAdjustmentItem, DealSummary, Document, Page, Program, ProgramDraft, ProgramPage, Support } from './types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
type Query = Record<string, string | number | undefined>
type CompanyFilters = { distributor_company_id?: string; dealer_company_id?: string }
export const createMonetizationApi = (config: RuntimeConfig, companyContext: () => unknown = () => undefined, leasingCompanyContext: () => unknown = () => undefined) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) => $fetch<T>(withApiCompanyContext(withNotificationCompanyContext(url, companyContext()), 'leasing_company_id', leasingCompanyContext()), {
    baseURL: config.public.apiBase, credentials: 'include', ...options,
  })
  const upload = (url: string, files: File[], revision?: number) => {
    const body = new FormData()
    for (const file of files) body.append('files', file)
    if (revision !== undefined) body.append('revision', String(revision))
    return request<{ documents: Document[] }>(url, { method: 'POST', body })
  }
  return {
    marks: () => request<{ marks: CatalogMark[] }>('/api/v1/monetization/lookups/catalog', { query: { fields: 'marks' } }),
    models: (markIds: string[]) => request<{ models: CatalogModel[] }>('/api/v1/monetization/lookups/catalog', { query: { fields: 'models', mark_id: markIds.join(',') } }),
    modifications: (markIds: string[], modelId: string) => request<{ modifications: CatalogModification[] }>('/api/v1/monetization/lookups/catalog', { query: { fields: 'modifications', mark_id: markIds.join(','), model_id: modelId } }),
    trims: (markIds: string[], modelId: string, modificationId: string) => request<{ trims: CatalogTrim[] }>('/api/v1/monetization/lookups/catalog', { query: { fields: 'trims', mark_id: markIds.join(','), model_id: modelId, modification_id: modificationId } }),
    programs: (query: Query) => request<ProgramPage>('/api/v1/admin/monetization/programs', { query }),
    program: (id: string) => request<Program>(`/api/v1/admin/monetization/programs/${id}`),
    createProgram: (body: ProgramDraft) => request<Program>('/api/v1/admin/monetization/programs', { method: 'POST', body: { ...body, sources: body.sources.map(({ source_type, expenses, incomes }) => ({ source_type, expenses, incomes })) } }),
    setProgramStatus: (id: string, status: Program['status']) => request<Program>(`/api/v1/admin/monetization/programs/${id}`, { method: 'PATCH', body: { status } }),
    companies: (kind: 'leasing' | 'dealer' | 'distributor' | 'client', q: string, filters: CompanyFilters = {}) => request<{ items: Company[] }>('/api/v1/monetization/lookups/companies', { query: { kind, q, ...filters } }),
    supports: (q: string, distributorCompanyId?: string) => request<{ items: Pick<Support, 'id' | 'name'>[] }>('/api/v1/monetization/lookups/supports', { query: { q, distributor_company_id: distributorCompanyId } }),
    support: (id: string) => request<Support>(`/api/v1/monetization/lookups/supports/${id}`),
    deals: (query: Query) => request<Page<DealSummary>>('/api/v1/monetization/deals', { query }),
    deal: (id: string) => request<Deal>(`/api/v1/monetization/deals/${id}`),
    uploadDocuments: (id: string, files: File[], revision: number) => upload(`/api/v1/monetization/deals/${id}/documents`, files, revision),
    confirm: (id: string, revision: number, admin: boolean) => request<Deal>(`/api/v1/${admin ? 'admin/' : ''}monetization/deals/${id}/confirm`, { method: 'POST', body: { revision } }),
    adjust: (id: string, revision: number, items: DealAdjustmentItem[]) => request<Deal>(`/api/v1/admin/monetization/deals/${id}/adjust-conditions`, { method: 'POST', body: { revision, items } }),
    requestsInbox: (query: Query = {}) => request<Page<ConditionRequest>>('/api/v1/monetization/condition-requests', { query }),
    requests: (id: string) => request<{ items: ConditionRequest[]; can_request: boolean; can_negotiate: boolean }>(`/api/v1/monetization/applications/${id}/condition-requests`),
    requestCommission: (id: string, body: { leasing_company_ids: string[]; calc_type: 'percent' | 'amount'; value: string }) => request<{ requests: ConditionRequest[] }>(`/api/v1/dealer/monetization/applications/${id}/condition-requests`, { method: 'POST', body }),
    respond: (id: string, body: { decision: 'accepted' | 'rejected' | 'countered'; counter_calc_type?: 'percent' | 'amount'; counter_value?: string }) => request<ConditionRequest>(`/api/v1/leasing-company/monetization/condition-requests/${id}/respond`, { method: 'POST', body }),
    decide: (id: string, decision: 'accept_counter' | 'reject') => request<ConditionRequest>(`/api/v1/dealer/monetization/condition-requests/${id}/decision`, { method: 'POST', body: { decision } }),
    download: async (document: Document) => {
      // Only module-owned relative file endpoints can receive authenticated requests.
      if (!/^\/api\/v1\/(admin\/)?monetization\//.test(document.download_url)) throw new Error('Недоступная ссылка на документ')
      const blob = await request<Blob>(document.download_url, { responseType: 'blob' })
      const url = URL.createObjectURL(blob)
      const link = window.document.createElement('a')
      link.href = url
      link.download = document.file_name
      link.click()
      URL.revokeObjectURL(url)
    },
  }
}
export type MonetizationApi = ReturnType<typeof createMonetizationApi>
export function errorMessage(error: unknown): string {
  const failure = error as { data?: { detail?: unknown }; message?: string }
  const detail = failure?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message
  return 'Не удалось выполнить действие. Проверьте данные и повторите попытку.'
}
