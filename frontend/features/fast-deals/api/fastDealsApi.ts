import { withNotificationCompanyContext } from '~/utils/apiCompanyContext'
import type { UUID } from '~/types/ids'
import type {
  AddVehicleBody,
  CompanyBrief,
  CreateFastDealBody,
  FastDealCard,
  FastDealErrorBody,
  FastDealFile,
  FastDealFileKind,
  FastDealFilters,
  FastDealListResponse,
  FilterOptions,
  LeasingTermsBody,
  MoneyString,
  OfferBody,
  OptionsBody,
  PatchVehicleBody,
  SupportProgramOption,
  VinLookupResult,
} from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
type Query = Record<string, string | number | boolean | undefined | null>

const BASE = '/api/v1/fast-deals'

/** Every mutation answers with the fresh card; its `etag` is the next `If-Match`. */
export interface CardResponse {
  deal: FastDealCard
}

export interface LookupItem {
  id: UUID
  name: string
  [key: string]: unknown
}

/**
 * Fast deal API. Mutations require the parent deal's current `etag` (`If-Match`);
 * a stale one yields 412, a missing one 428. Child URLs use the parent's etag too.
 * Company context (`notification_company_id`) is applied like in other cabinets.
 */
export const createFastDealsApi = (config: RuntimeConfig, companyContext: () => unknown = () => undefined) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(withNotificationCompanyContext(url, companyContext()), {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })
  const mutate = (method: 'POST' | 'PATCH' | 'PUT' | 'DELETE', url: string, etag: string, body?: unknown) =>
    request<CardResponse>(url, { method, headers: { 'If-Match': etag }, ...(body === undefined ? {} : { body }) })

  return {
    list: (filters: FastDealFilters = {}) => request<FastDealListResponse>(BASE, { query: filters as Query }),
    filterOptions: () => request<FilterOptions>(`${BASE}/filter-options`),
    get: (id: UUID) => request<CardResponse>(`${BASE}/${id}`),
    create: (body: CreateFastDealBody) => request<CardResponse>(BASE, { method: 'POST', body }),
    remove: (id: UUID, etag: string) =>
      request<void>(`${BASE}/${id}`, { method: 'DELETE', headers: { 'If-Match': etag } }),

    // Catalog and directories
    vinLookup: (vin: string) =>
      request<VinLookupResult>('/api/v1/special-equipment/catalog/vin-lookup', { query: { vin } }),
    vehicleCandidates: (query: { vin?: string; warehouse_id?: UUID; mark_id?: UUID; model_id?: UUID; page?: number; page_size?: number }) =>
      request<{ items: Record<string, unknown>[]; total: number; page: number; page_size: number }>(
        `${BASE}/vehicle-candidates`, { query: query as Query }),
    lookup: (kind: 'leasing-companies' | 'dealers' | 'warehouses' | 'categories' | 'marks' | 'models' | 'modifications' | 'trims' | 'colors'
      | 'equipments' | 'services' | 'purposes' | 'regions' | 'similar-models', query: Query = {}) =>
      request<{ items: LookupItem[] }>(`${BASE}/lookups/${kind}`, { query }),

    // Draft editing
    addVehicle: (id: UUID, etag: string, body: AddVehicleBody) => mutate('POST', `${BASE}/${id}/vehicles`, etag, body),
    patchVehicle: (id: UUID, vehicleId: UUID, etag: string, body: PatchVehicleBody) =>
      mutate('PATCH', `${BASE}/${id}/vehicles/${vehicleId}`, etag, body),
    removeVehicle: (id: UUID, vehicleId: UUID, etag: string) =>
      mutate('DELETE', `${BASE}/${id}/vehicles/${vehicleId}`, etag),
    priceAdjustment: (id: UUID, vehicleId: UUID, etag: string, body: { type: 'discount' | 'markup' | null; amount: MoneyString | null }) =>
      mutate('PATCH', `${BASE}/${id}/vehicles/${vehicleId}/price-adjustment`, etag, body),
    options: (id: UUID, vehicleId: UUID, etag: string, body: OptionsBody) =>
      mutate('PUT', `${BASE}/${id}/vehicles/${vehicleId}/options`, etag, body),
    terms: (id: UUID, etag: string, body: LeasingTermsBody) => mutate('PATCH', `${BASE}/${id}/leasing-terms`, etag, body),

    // Supports
    supportPrograms: (id: UUID, vehicleId: UUID) =>
      request<{ items: SupportProgramOption[]; support_hint?: string | null }>(`${BASE}/${id}/vehicles/${vehicleId}/support-programs`),
    applySupportProgram: (id: UUID, vehicleId: UUID, etag: string, supportProgramId: UUID) =>
      mutate('POST', `${BASE}/${id}/vehicles/${vehicleId}/applied-supports`, etag, { support_program_id: supportProgramId }),
    removeAppliedSupport: (id: UUID, vehicleId: UUID, appliedId: UUID, etag: string) =>
      mutate('DELETE', `${BASE}/${id}/vehicles/${vehicleId}/applied-supports/${appliedId}`, etag),
    requestSupport: (id: UUID, vehicleId: UUID, etag: string, body: { amount: MoneyString; comment?: string }) =>
      mutate('POST', `${BASE}/${id}/vehicles/${vehicleId}/support-requests`, etag, body),
    decideSupport: (requestId: UUID, etag: string, body: { status: 'cancelled' | 'pre_approved' | 'approved'; decided_amount?: MoneyString; comment?: string }) =>
      mutate('PATCH', `${BASE}/support-requests/${requestId}`, etag, body),
    applySupport: (id: UUID, vehicleId: UUID, etag: string) =>
      mutate('POST', `${BASE}/${id}/vehicles/${vehicleId}/apply-support`, etag),

    // DD: dealer → leasing companies
    sendToLeasingCompanies: (id: UUID, etag: string, leasingCompanyIds: UUID[]) =>
      mutate('POST', `${BASE}/${id}/send-to-leasing-companies`, etag, { leasing_company_ids: leasingCompanyIds }),
    submitOffer: (lcApplicationId: UUID, etag: string, body: OfferBody) =>
      mutate('POST', `${BASE}/lc-applications/${lcApplicationId}/offer`, etag, body),
    selectOffer: (lcApplicationId: UUID, etag: string) =>
      mutate('POST', `${BASE}/lc-applications/${lcApplicationId}/select`, etag),
    withdrawSelection: (id: UUID, etag: string) => mutate('POST', `${BASE}/${id}/withdraw-selection`, etag),
    confirmAsLeasing: (lcApplicationId: UUID, etag: string, fileIds: UUID[] = []) =>
      mutate('POST', `${BASE}/lc-applications/${lcApplicationId}/confirm`, etag, { file_ids: fileIds }),
    rejectAsLeasing: (lcApplicationId: UUID, etag: string, reason: string) =>
      mutate('POST', `${BASE}/lc-applications/${lcApplicationId}/reject`, etag, { reason }),

    // DL: leasing company → dealers
    sendToDealers: (id: UUID, etag: string) =>
      request<{ group_id: UUID; deals: FastDealCard[] }>(`${BASE}/${id}/send-to-dealers`, { method: 'POST', headers: { 'If-Match': etag } }),
    confirmAsDealer: (id: UUID, etag: string, fileIds: UUID[] = []) =>
      mutate('POST', `${BASE}/${id}/confirm`, etag, { file_ids: fileIds }),
    sendChanges: (id: UUID, etag: string, comment?: string) =>
      mutate('POST', `${BASE}/${id}/send-changes`, etag, comment ? { comment } : {}),
    acceptChanges: (id: UUID, etag: string) => mutate('POST', `${BASE}/${id}/changes/accept`, etag),
    rejectChanges: (id: UUID, etag: string, reason: string) => mutate('POST', `${BASE}/${id}/changes/reject`, etag, { reason }),
    rejectAsDealer: (id: UUID, etag: string, reason: string) => mutate('POST', `${BASE}/${id}/reject`, etag, { reason }),
    cancel: (id: UUID, etag: string, reason?: string) => mutate('POST', `${BASE}/${id}/cancel`, etag, reason ? { reason } : {}),

    // Files and assignees
    uploadFiles: (id: UUID, etag: string, payload: { kind: FastDealFileKind; files: File[]; addresseeCompanyIds?: UUID[]; fastDealVehicleId?: UUID; leasingApplicationId?: UUID }) => {
      const body = new FormData()
      body.append('kind', payload.kind)
      for (const file of payload.files) body.append('files', file)
      for (const company of payload.addresseeCompanyIds ?? []) body.append('addressee_company_ids', company)
      if (payload.fastDealVehicleId) body.append('fast_deal_vehicle_id', payload.fastDealVehicleId)
      if (payload.leasingApplicationId) body.append('lc_application_id', payload.leasingApplicationId)
      return request<CardResponse & { files: FastDealFile[] }>(`${BASE}/${id}/files`, { method: 'POST', headers: { 'If-Match': etag }, body })
    },
    downloadFile: async (id: UUID, fileId: UUID, filename: string) =>
      saveBlob(await request<Blob>(`${BASE}/${id}/files/${fileId}`, { responseType: 'blob' }).catch(decodeBlobError), filename),
    downloadArchive: async (id: UUID, filename: string) =>
      saveBlob(await request<Blob>(`${BASE}/${id}/files/archive`, { responseType: 'blob' }).catch(decodeBlobError), filename),
    assignableEmployees: (id: UUID) =>
      request<{ items: { id: UUID; name: string | null; email: string | null; sub_role: string }[] }>(`${BASE}/${id}/assignable-employees`),
    setAssignees: (id: UUID, etag: string, body: { primary_user_id: UUID; additional_user_id?: UUID | null }) =>
      mutate('PUT', `${BASE}/${id}/assignees`, etag, body),
  }
}

export type FastDealsApi = ReturnType<typeof createFastDealsApi>

/** A failed blob download carries its JSON error body as a Blob: decode it so `parseFastDealError` can read it. */
async function decodeBlobError(error: unknown): Promise<never> {
  const failure = error as { data?: unknown }
  if (failure?.data instanceof Blob) {
    try {
      failure.data = JSON.parse(await failure.data.text())
    } catch {
      failure.data = undefined
    }
  }
  throw error
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = window.document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** Message and offending field/VIN of a failed fast deal request. */
export function parseFastDealError(error: unknown): FastDealErrorBody & { status?: number } {
  const failure = error as { statusCode?: number; status?: number; data?: Partial<FastDealErrorBody> }
  const status = failure?.statusCode ?? failure?.status
  const data = failure?.data ?? {}
  return {
    status,
    detail: typeof data.detail === 'string' ? data.detail : 'Не удалось выполнить действие. Проверьте данные и повторите попытку.',
    code: data.code,
    field: data.field,
    vin: data.vin,
    source_number: data.source_number,
  }
}

export type { CompanyBrief }
