import type { UUID } from '~/types/ids'

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export interface Pagination {
  page: number
  limit: number
  total: number
  pages: number
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface DistributorAnalytics {
  [key: string]: unknown
}

export interface DistributorAnalyticsResponse {
  analytics: DistributorAnalytics
}

// ---------------------------------------------------------------------------
// Applications
// ---------------------------------------------------------------------------

export interface DistributorApplication {
  id: UUID
  [key: string]: unknown
}

export interface ApplicationsGroupedResponse {
  applications: DistributorApplication[]
  pagination: Pagination
}

export interface ApplicationPdfResponse {
  download_url: string
}

export interface ApplicationVehicle {
  id: UUID
  vin?: string
  [key: string]: unknown
}

export interface ApplicationVehiclesResponse {
  vehicles: ApplicationVehicle[]
  pagination?: Pagination
}

export interface AddVehiclePayload {
  vehicle_id: UUID
  is_model_order: boolean
}

export interface ReplaceVehiclePayload {
  vehicle_id: UUID
  is_model_order: boolean
}

// ---------------------------------------------------------------------------
// Model orders
// ---------------------------------------------------------------------------

export interface ModelOrdersStats {
  [key: string]: unknown
}

export interface ModelOrdersStatsResponse {
  stats: ModelOrdersStats
}

export interface AssignVinPayload {
  vin: string
}

// ---------------------------------------------------------------------------
// Available vehicles (for application)
// ---------------------------------------------------------------------------

export interface AvailableVehiclesResponse {
  vehicles: ApplicationVehicle[]
}

// ---------------------------------------------------------------------------
// Dealers
// ---------------------------------------------------------------------------

export interface Dealer {
  id: UUID
  name: string | null
  company_type: string
}

export interface DealersResponse {
  dealers: Dealer[]
  pagination: Pagination | null
}

export interface UpdateDealerStatusPayload {
  status: string
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export interface DistributorProfile {
  logo?: string
  documents?: DistributorDocument[]
  [key: string]: unknown
}

export interface DistributorProfileResponse {
  profile: DistributorProfile
}

export interface LogoUploadResponse {
  logo_url: string
}

export interface DistributorDocument {
  id: UUID
  file_name: string
  mime_type: string
  [key: string]: unknown
}

export interface DocumentsUploadResponse {
  documents: DistributorDocument[]
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface DistributorReport {
  id: UUID
  file_name: string
  mime_type: string
  [key: string]: unknown
}

export interface DistributorReportsResponse {
  reports: DistributorReport[]
  pagination: Pagination
}

export interface CreateReportPayload {
  [key: string]: unknown
}

// ---------------------------------------------------------------------------
// Warehouse (vehicles)
// ---------------------------------------------------------------------------

export interface WarehouseVehicle {
  id: UUID
  [key: string]: unknown
}

export interface WarehouseStats {
  [key: string]: unknown
}

export interface WarehouseResponse {
  vehicles: WarehouseVehicle[]
  stats: WarehouseStats | null
  brands: string[]
  years: number[]
  pagination: Pagination
}

// ---------------------------------------------------------------------------
// Warehouse analytics
// ---------------------------------------------------------------------------

export interface WarehouseAnalyticsStatusItem {
  status: string
  count: number
  value: number
}

export interface WarehouseAnalyticsMarkItem {
  mark: string
  count: number
  value: number
}

export interface WarehouseAnalyticsDealerItem {
  dealer_id: UUID
  dealer_name: string
  count: number
  value: number
}

export interface WarehouseAnalyticsCityItem {
  city: string
  count: number
  value: number
}

export interface WarehouseAnalyticsTimelineItem {
  period: string | null
  status: string
  count: number
}

export interface WarehouseAnalyticsBody {
  total_vehicles: number
  total_value: number
  total_dealers: number
  by_status: WarehouseAnalyticsStatusItem[]
  by_mark: WarehouseAnalyticsMarkItem[]
  by_dealer: WarehouseAnalyticsDealerItem[]
  by_city: WarehouseAnalyticsCityItem[]
  timeline: WarehouseAnalyticsTimelineItem[]
}

export interface WarehouseAnalyticsResponse {
  analytics: WarehouseAnalyticsBody
}

export interface BulkDeletePayload {
  ids: UUID[]
}

export interface BulkUpdatePayload {
  ids: UUID[]
  patch: Record<string, unknown>
}

export interface BulkDetailsResponse {
  vehicles: Array<Record<string, unknown>>
  pagination?: Pagination
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createDistributorApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, { baseURL: config.public.apiBase, credentials: 'include', ...options })

  return {
    // ---- Analytics --------------------------------------------------------

    getAnalytics(period: string) {
      return request<DistributorAnalyticsResponse>(
        `/api/v1/distributor/analytics?period=${period}`,
      )
    },

    exportAnalyticsXlsx() {
      return request<Blob>('/api/v1/distributor/analytics?format=xlsx', {
        responseType: 'blob',
      })
    },

    getWarehouseAnalytics() {
      return request<WarehouseAnalyticsResponse>(
        '/api/v1/distributor/warehouse-analytics',
      )
    },

    // ---- Applications -----------------------------------------------------

    getApplicationsGrouped(query: string) {
      return request<ApplicationsGroupedResponse>(
        `/api/v1/distributor/applications-grouped?${query}`,
      )
    },

    getApplicationPdf(applicationId: UUID) {
      return request<ApplicationPdfResponse>(
        `/api/v1/distributor/applications/${applicationId}/pdf`,
      )
    },

    getApplicationVehicles(applicationId: UUID, query: string) {
      return request<ApplicationVehiclesResponse>(
        `/api/v1/distributor/applications/${applicationId}/vehicles?${query}`,
      )
    },

    addVehicleToApplication(applicationId: UUID, payload: AddVehiclePayload) {
      return request<void>(
        `/api/v1/distributor/applications/${applicationId}/vehicles`,
        { method: 'POST', body: payload },
      )
    },

    replaceApplicationVehicle(vehicleItemId: UUID, payload: ReplaceVehiclePayload) {
      return request<void>(
        `/api/v1/distributor/application-vehicles/${vehicleItemId}/replace`,
        { method: 'PUT', body: payload },
      )
    },

    deleteApplicationVehicle(vehicleItemId: UUID) {
      return request<void>(
        `/api/v1/distributor/application-vehicles/${vehicleItemId}`,
        { method: 'DELETE' },
      )
    },

    // ---- Model orders -----------------------------------------------------

    getModelOrdersStats() {
      return request<ModelOrdersStatsResponse>('/api/v1/distributor/model-orders/stats')
    },

    assignVin(vehicleId: UUID, payload: AssignVinPayload) {
      return request<void>(`/api/v1/application-vehicles/${vehicleId}`, {
        method: 'PATCH',
        body: payload,
      })
    },

    // ---- Available vehicles -----------------------------------------------

    getAvailableVehiclesForApp(query: string) {
      return request<AvailableVehiclesResponse>(
        `/api/v1/distributor/available-vehicles-for-app?${query}`,
      )
    },

    // ---- Dealers ----------------------------------------------------------

    getDealers(query: string) {
      return request<DealersResponse>(`/api/v1/distributor/dealers?${query}`)
    },

    updateDealerStatus(dealerId: UUID, payload: UpdateDealerStatusPayload) {
      return request<void>(`/api/v1/distributor/dealers/${dealerId}`, {
        method: 'PATCH',
        body: payload,
      })
    },

    exportDealersXlsx() {
      return request<Blob>('/api/v1/distributor/dealers?format=xlsx', {
        responseType: 'blob',
      })
    },

    // Profile read moved to authApi.getMyProfile (Phase 13 R13a —
    // /distributor/profile consolidated into /users/me). Distributor
    // self-update via /users/me PATCH is intentionally not supported
    // (legacy /distributor/profile had no PUT either).

    uploadLogo(formData: FormData) {
      return request<LogoUploadResponse>('/api/v1/distributor/profile/logo', {
        method: 'POST',
        body: formData,
      })
    },

    uploadDocuments(formData: FormData) {
      return request<DocumentsUploadResponse>('/api/v1/distributor/profile/documents', {
        method: 'POST',
        body: formData,
      })
    },

    downloadDocument(documentId: UUID) {
      return request<Blob>(`/api/v1/distributor/profile/documents/${documentId}/download`)
    },

    // ---- Reports ----------------------------------------------------------

    getReports(query: string) {
      return request<DistributorReportsResponse>(`/api/v1/distributor/reports?${query}`)
    },

    createReport(payload: CreateReportPayload) {
      return request<void>('/api/v1/distributor/reports', {
        method: 'POST',
        body: payload,
      })
    },

    downloadReport(reportId: UUID) {
      return request<Blob>(`/api/v1/distributor/reports/${reportId}/download`)
    },

    deleteReport(reportId: UUID) {
      return request<void>(`/api/v1/distributor/reports/${reportId}`, {
        method: 'DELETE',
      })
    },

    // ---- Warehouse --------------------------------------------------------

    getVehicles(query: string) {
      return request<WarehouseResponse>(`/api/v1/distributor/vehicles?${query}`)
    },

    exportVehiclesXlsx(query: string = '') {
      const separator = query ? '&' : ''
      return request<Blob>(
        `/api/v1/distributor/vehicles?${query}${separator}format=xlsx`,
        { responseType: 'blob' },
      )
    },

    deleteVehicle(vehicleId: UUID) {
      return request<void>(`/api/v1/distributor/vehicles/${vehicleId}`, {
        method: 'DELETE',
      })
    },

    bulkDeleteVehicles(payload: BulkDeletePayload) {
      return request<void>('/api/v1/distributor/vehicles', {
        method: 'DELETE',
        body: payload,
      })
    },

    bulkUpdateVehicles(payload: BulkUpdatePayload) {
      return request<void>('/api/v1/distributor/vehicles', {
        method: 'PATCH',
        body: payload,
      })
    },

    getVehiclesByIds(ids: UUID[]) {
      const query = ids.map((id) => `ids=${encodeURIComponent(id)}`).join('&')
      return request<BulkDetailsResponse>(
        `/api/v1/distributor/vehicles?${query}`,
      )
    },
  }
}
