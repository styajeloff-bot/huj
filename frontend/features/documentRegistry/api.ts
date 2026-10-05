import { withNotificationCompanyContext } from '~/utils/apiCompanyContext'
import type { CatalogItem, CompanyRole, CursorPage, DeletionUsages, DocumentGroup, MonetizationDocumentContext, Page, ReferenceDocument, RegistryCompany, RegistryFile, RegistryFilters, RegistryType, RegistryVersion, TableRow, VersionSnapshotInput } from './types'
const base = '/api/v1/document-registry'
type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
export function createDocumentRegistryApi(config: RuntimeConfig, companyContext: () => unknown = () => undefined) {
  const request = <T>(path: string, options: Record<string, unknown> = {}) => $fetch<T>(withNotificationCompanyContext(path, companyContext()), { baseURL: config.public.apiBase, credentials: 'include', ...options })
  const query = (filters: RegistryFilters) => Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ''))
  async function upload(path: string, metadata: object, files: File[]) {
    const body = new FormData(); body.append('metadata', JSON.stringify(metadata)); files.forEach(file => body.append('files', file))
    return await request<ReferenceDocument>(path, { method: 'POST', body })
  }
  function saveBlob(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return {
    types: () => request<{ items: RegistryType[] }>(`${base}/types`),
    companies: (role: CompanyRole, search: string) => request<{ items: RegistryCompany[] }>(`${base}/lookups/companies`, { query: { role, search } }),
    catalog: (markId?: string) => request<{ items: CatalogItem[] }>(`${base}/lookups/catalog`, { query: { fields: markId ? 'models' : 'marks', mark_id: markId } }),
    groups: (filters: RegistryFilters, page: number) => request<Page<DocumentGroup>>(`${base}/groups`, { query: { ...query(filters), page, page_size: 20 } }),
    children: (id: string, type: string, page: number) => request<Page<ReferenceDocument>>(`${base}/groups/${id}/documents`, { query: { document_type: type || undefined, page, page_size: 20 } }),
    table: (filters: RegistryFilters, cursor?: string) => request<CursorPage<TableRow>>(`${base}/table`, { query: { ...query(filters), cursor, limit: 10 } }),
    export: async (filters: RegistryFilters) => saveBlob(await request<Blob>(`${base}/table/export`, { query: query(filters), responseType: 'blob' }), 'Справочник документов.xlsx'),
    document: (id: string) => request<ReferenceDocument>(`${base}/documents/${id}`),
    versions: (id: string) => request<{ items: RegistryVersion[] }>(`${base}/documents/${id}/versions`),
    create: (metadata: object, files: File[], groupId?: string) => upload(groupId ? `${base}/groups/${groupId}/documents` : `${base}/documents`, metadata, files),
    newVersion: (id: string, metadata: VersionSnapshotInput, files: File[]) => upload(`${base}/documents/${id}/versions`, metadata, files),
    activateVersion: (id: string, versionId: string, expectedCurrentVersionId: string) => request<ReferenceDocument>(`${base}/documents/${id}/versions/${versionId}/activate`, { method: 'POST', body: { expected_current_version_id: expectedCurrentVersionId } }),
    activate: (id: string, active: boolean) => request<ReferenceDocument>(`${base}/documents/${id}/activation`, { method: 'PATCH', body: { active } }),
    usages: (id: string) => request<DeletionUsages>(`${base}/documents/${id}/monetization-usages`),
    remove: (id: string, fingerprint: string) => request<void>(`${base}/documents/${id}`, { method: 'DELETE', headers: { 'If-Match': fingerprint } }),
    checkNumber: (number: string) => request<{ available: boolean }>(`${base}/check-contract-number`, { query: { number } }),
    download: async (file: RegistryFile) => {
      if (!/^\/api\/v1\/document-registry\/files\/[^/]+\/download$/.test(file.download_url)) throw new Error('Недоступная ссылка на файл')
      saveBlob(await request<Blob>(file.download_url, { responseType: 'blob' }), file.name)
    },
    candidates: (value: { program_id: string } | { context: MonetizationDocumentContext }) => request<{ items: ReferenceDocument[]; groups: DocumentGroup[] }>(`${base}/monetization-candidates`, { method: 'POST', body: value }),
    programDocuments: (id: string) => request<{ items: ReferenceDocument[] }>(`/api/v1/admin/monetization/programs/${id}/reference-documents`),
    setProgramDocuments: (id: string, documentIds: string[]) => request<{ items: ReferenceDocument[] }>(`/api/v1/admin/monetization/programs/${id}/reference-documents`, { method: 'PATCH', body: { document_ids: documentIds } }),
  }
}
export type DocumentRegistryApi = ReturnType<typeof createDocumentRegistryApi>
export function registryError(error: unknown): string {
  const value = error as { data?: { detail?: unknown } }
  if (typeof value?.data?.detail === 'string') return value.data.detail
  if (value?.data?.detail && typeof value.data.detail === 'object' && 'message' in value.data.detail && typeof value.data.detail.message === 'string') return value.data.detail.message
  return 'Не удалось выполнить действие. Проверьте данные и повторите попытку.'
}
