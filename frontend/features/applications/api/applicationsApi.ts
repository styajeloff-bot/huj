import type { $Fetch } from 'ofetch'
import type { ApplicationSourceType, SiteApplicationSourceType } from '~/features/applications/sourceType'
import { withNotificationCompanyContext } from '~/utils/apiCompanyContext'
import type { CatalogId, UUID } from '~/types/ids'
import type { CommerceApplicationItem } from '~/features/commerce/types'
import type { SupportBadgeProgram } from '~/types/support'
import type { AdditionalOptionPrice } from '~/features/applications/additionalOptionPrice'
import type { ApplicationListKind } from '~/features/fast-deals/mergedList'
import type { FastDealListItem } from '~/features/fast-deals/types'

export interface ApplicationEquipmentOption {
  equipment_code: string
  price?: AdditionalOptionPrice
  comment?: string | null
}

export interface ApplicationServiceOption {
  service_code: string
  price?: AdditionalOptionPrice
  comment?: string | null
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type EntityId = UUID

export interface WarehouseInfo {
  id?: EntityId | null
  address?: string | null
  brand?: string | null
  city?: string | null
  company_id?: EntityId | null
  company_name?: string | null
}

export interface AssignedDealer {
  id: EntityId
  name: string
  inn?: string | null
}

export interface DealerDistributionPosition {
  application_vehicle_id: EntityId
  title: string
  quantity: number
  stock_dealer: AssignedDealer | null
  dealer_allocations: { dealer: AssignedDealer; quantity: number }[]
  unassigned_quantity: number
  can_assign_dealer: boolean
}

export interface DealerDistributionPayload {
  request_id: EntityId
  dealer_id: EntityId
  items: {
    application_vehicle_id: EntityId
    quantity: number
    expected_unassigned_quantity: number
  }[]
}

export interface AssignedEmployee {
  id: EntityId
  name?: string | null
  phone?: string | null
  sub_role?: string | null
}

export interface AssignmentAuditActor {
  id: EntityId
  name?: string | null
}

export interface AssignableDealer {
  id: EntityId
  name: string
  inn?: string | null
  brands: string[]
}

export interface DealerGroup {
  id: EntityId
  name: string
  dealers: AssignableDealer[]
}

export interface EmployeeOption extends AssignedEmployee {
  id: EntityId
}

export interface DealerGroupsResponse {
  groups: DealerGroup[]
}

export interface DistributorDealerOption {
  id: EntityId
  name: string | null
  company_type: string
}

export interface DistributorDealersResponse {
  dealers: DistributorDealerOption[]
  pagination: Pagination | null
}

export interface EmployeesSearchResponse {
  employees: EmployeeOption[]
}

export interface AssignDealerPayload {
  dealer_id: EntityId
}

export interface AssignEmployeesPayload {
  primary_employee_id?: EntityId | null
  additional_employee_id?: EntityId | null
}

export interface ApplicationMutationResponse {
  application: Application
}

export interface ApplicationVehicleMutationResponse {
  application_vehicle: ApplicationVehicle
}

export interface ApplicationsApiErrorInfo {
  code: string | null
  message: string
}

export const parseApplicationsApiError = (
  error: unknown,
  fallback: string,
): ApplicationsApiErrorInfo => {
  const payload = error && typeof error === 'object'
    ? error as {
        data?: {
          detail?: string | { code?: unknown; message?: unknown; error?: unknown }
          error?: unknown
          error_code?: unknown
          message?: unknown
        }
        message?: unknown
      }
    : null
  const detail = payload?.data?.detail

  if (typeof detail === 'string' && detail.trim()) {
    return { code: null, message: detail }
  }

  if (detail && typeof detail === 'object') {
    const code = typeof detail.code === 'string' && detail.code.trim() ? detail.code : null
    const messageCandidate = detail.message ?? detail.error
    if (typeof messageCandidate === 'string' && messageCandidate.trim()) {
      return { code, message: messageCandidate }
    }
    if (code) {
      return { code, message: fallback }
    }
  }

  if (typeof payload?.data?.error === 'string' && payload.data.error.trim()) {
    return { code: null, message: payload.data.error }
  }
  if (typeof payload?.data?.message === 'string' && payload.data.message.trim()) {
    return {
      code: typeof payload.data.error_code === 'string' ? payload.data.error_code : null,
      message: payload.data.message,
    }
  }
  if (typeof payload?.message === 'string' && payload.message.trim()) {
    return { code: null, message: payload.message }
  }
  return { code: null, message: fallback }
}

export interface DealerActionDocument {
  id?: EntityId
  application_vehicle_id?: EntityId
  action?: 'reject' | 'replace' | 'reserve' | 'discount' | 'markup' | 'contact_client' | 'replace_vin' | string
  file_url?: string | null
  file_key?: string | null
  file_name?: string | null
  file_type?: string | null
  uploaded_by?: EntityId | null
  created_at?: string | null
}

export interface ApplicationVehicle {
  can_manage_whole_vehicle?: boolean
  confirmed_quantity?: number | null
  fulfillment_version?: number
  allocated_vehicle_ids?: EntityId[]
  allocated_vins?: Array<string | null>
  id?: EntityId
  application_vehicle_id?: EntityId
  vehicle_id?: EntityId | null
  modification_id?: CatalogId | null
  brand?: string | null
  mark_name?: string | null
  mark_cyrillic_name?: string | null
  model?: string | null
  model_name?: string | null
  model_cyrillic_name?: string | null
  group_name?: string | null
  complectation_name?: string | null
  year?: number | null
  price?: number | null
  unit_price?: number | null
  total_price?: number | null
  catalog_price?: number | null
  catalog_price_from?: number | null
  catalog_price_to?: number | null
  quantity: number
  equipments?: ApplicationEquipmentOption[]
  services?: ApplicationServiceOption[]
  leasing_purpose?: string | null
  leasing_purposes?: string[] | null
  leasing_purpose_comment?: string | null
  region?: string | null
  regions?: string[] | null
  vin?: string | null
  vehicle_vin?: string | null
  engine?: string | null
  engine_type?: string | null
  transmission?: string | null
  drive?: string | null
  support?: string | number | boolean | null
  status?: string | null
  car_status?: string | null
  comment?: string | null
  dealer_comment?: string | null
  reserve_expires_at?: string | null
  discount_type?: string | null
  discount_value?: number | string | null
  markup_type?: string | null
  markup_value?: number | string | null
  discount_show_catalog_price?: boolean | null
  markup_show_catalog_price?: boolean | null
  show_catalog_price?: boolean | null
  final_price?: number | string | null
  dealer_id?: EntityId | null
  dealer_name?: string | null
  dealer_company_id?: EntityId | null
  assigned_dealer?: AssignedDealer | null
  stock_dealer?: AssignedDealer | null
  dealer_assigned_by_id?: EntityId | null
  dealer_assigned_by?: AssignmentAuditActor | null
  dealer_assigned_at?: string | null
  primary_employee_id?: EntityId | null
  primary_employee?: AssignedEmployee | null
  additional_employee_id?: EntityId | null
  additional_employee?: AssignedEmployee | null
  employees_assigned_by_id?: EntityId | null
  employees_assigned_by?: AssignmentAuditActor | null
  employees_assigned_at?: string | null
  warehouse_id?: EntityId | null
  warehouse_address?: string | null
  warehouse?: WarehouseInfo | null
  dealer_action_documents?: DealerActionDocument[]
}

export interface ApplicationSupportPerProgram {
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
}

export interface ApplicationCalculation {
  term?: number
  advance_rate?: number
  advance_amount?: number
  monthly_payment?: number
  total_cost?: number
  rate?: number
  total_interest?: number
  buyout_amount?: number
  vat_refund?: number
  profit_tax_savings?: number
  total_savings?: number
  selected_support?: Record<UUID, UUID[]>
  support_program_details?: SupportBadgeProgram[]
  support_per_program?: ApplicationSupportPerProgram[]
}

export interface ApplicationCompany {
  id?: EntityId
  name?: string | null
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  company_type?: string | null
  phone?: string | null
  email?: string | null
  legal_address?: string | null
  actual_address?: string | null
  tax_system?: string | null
}

export interface ApplicationOwner {
  id?: EntityId
  name?: string | null
  phone?: string | null
  email?: string | null
  role?: string | null
}

export interface Application {
  dealer_distribution?: DealerDistributionPosition[]
  id: EntityId
  display_number?: string | null
  source_type?: ApplicationSourceType | null
  group_id?: EntityId | null
  group_number?: string | null
  status: string
  application_status?: string | null
  application_status_label?: string | null
  group_status?: string | null
  group_status_label?: string | null
  company_id?: EntityId
  company_name?: string | null
  company_inn?: string | null
  company?: ApplicationCompany | null
  owner?: ApplicationOwner | null
  phone?: string | null
  email?: string | null
  name?: string | null
  vehicles: ApplicationVehicle[]
  items?: CommerceApplicationItem[]
  calculation?: ApplicationCalculation | null
  questionnaire?: Record<string, unknown> | null
  questionnaire_data?: Record<string, unknown> | null
  selected_leasing_companies?: string[]
  can_assign_dealer?: boolean
  dealer_company_id?: EntityId | null
  assigned_dealer?: AssignedDealer | null
  assigned_dealer_group_id?: EntityId | null
  dealer_assigned_by_id?: EntityId | null
  dealer_assigned_by?: AssignmentAuditActor | null
  dealer_assigned_at?: string | null
  primary_employee_id?: EntityId | null
  primary_employee?: AssignedEmployee | null
  additional_employee_id?: EntityId | null
  additional_employee?: AssignedEmployee | null
  employees_assigned_by_id?: EntityId | null
  employees_assigned_by?: AssignmentAuditActor | null
  employees_assigned_at?: string | null
  vehicle_count?: number | null
  vehicles_count?: number | null
  total_amount?: number | null
  total_cost?: number | null
  total_vehicles_price?: number | null
  items_count?: number | null
  total_items_price?: string | null
  special_equipment_count?: number | null
  total_special_equipment_price?: string | null
  down_payment_percent?: number | null
  lease_term_months?: number | null
  monthly_payment?: number | null
  rate?: number | null
  created_at: string
  updated_at: string
}

export interface Pagination {
  page: number
  limit: number
  total: number
  pages: number
}

export interface ApplicationsListResponse {
  applications: Application[]
  total: number
  pagination: Pagination
}

/**
 * «Мои заявки» of dealers and distributors also list fast deals: rows with `kind: 'fast_deal'`
 * are `FastDealListItem`s (their own card, their own statuses), every other row is an application.
 */
export type MergedApplicationRow = Application | FastDealListItem

export interface MergedApplicationsListResponse {
  applications: MergedApplicationRow[]
  total: number
  pagination: Pagination
}

export interface ApplicationListFilters {
  search?: string
  source_type?: SiteApplicationSourceType[]
  /** Narrow the merged list to ordinary applications or to fast deals; omit for both. */
  kind?: ApplicationListKind
}

export interface ApplicationDetailResponse {
  application: Application
}

export interface CreateApplicationBody {
  source_type: SiteApplicationSourceType
  company_id?: EntityId
  vehicles: Array<{
    vehicle_id: EntityId
    quantity: number
  }>
  calculation?: ApplicationCalculation
  name?: string
  email?: string
}

export interface ApplicationInitResponse {
  application_id: UUID
  status?: string
}

export interface CreateApplicationResponse {
  application_id?: UUID
  applicationIds?: EntityId[]
  status?: string
  group?: Record<string, unknown> | null
}

export interface CreateApplicationPayload {
  source_type: SiteApplicationSourceType
  company_id: EntityId
  vehicles: Array<{
    vehicle_id?: EntityId | null
    modification_id?: CatalogId | null
    quantity: number
    custom_price?: number | null
    comment?: string | null
    is_model_order?: boolean
    equipments?: ApplicationEquipmentOption[]
    services?: ApplicationServiceOption[]
  }>
  companyNameOrInn?: string
  name?: string
  email?: string
  selectedLeasingCompanies?: string[]
}

export interface AvailableVinsResponse {
  success: boolean
  vehicles: Array<{
    id?: EntityId
    vehicle_id?: EntityId
    vin: string
    [key: string]: unknown
  }>
}

export interface AssignVinResponse {
  success: boolean
}

export interface StatusUpdateBody {
  status: 'active' | 'rejected' | 'issued'
}

export interface DealerVehicleActionPayload {
  action: 'reject' | 'replace' | 'reserve' | 'discount' | 'markup' | 'contact_client' | 'replace_vin'
  comment?: string | null
  reserve_expires_at?: string | null
  discount_type?: 'rubles_off' | 'percent_off' | 'fixed_price' | null
  discount_value?: number | string | null
  markup_type?: 'rubles_up' | 'percent_up' | null
  markup_value?: number | string | null
  show_catalog_price?: boolean
  final_price?: number | string | null
  vin?: string | null
  files?: File[]
}

export interface DealerVehicleActionResponse {
  success: boolean
  status: string
  application_vehicle: ApplicationVehicle
}

export interface DealerRequestedPriceResponse {
  item_id: EntityId
  application_id: EntityId
  agreed_price: string
  currency: string
  status: 'price_set'
  price_set_by: EntityId
  price_set_at: string
  application_total_amount: string
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createApplicationsApi = (config: RuntimeConfig, notificationCompanyContext?: () => unknown) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(withNotificationCompanyContext(url, notificationCompanyContext?.()), { baseURL: config.public.apiBase, credentials: 'include', ...options })

  const listQuery = (page: number, limit: number, status: string, filters: ApplicationListFilters): string => {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
    })
    if (status) params.append('status', status)
    if (filters.search?.trim()) params.append('search', filters.search.trim())
    if (filters.source_type?.length) params.append('source_type', filters.source_type.join(','))
    if (filters.kind) params.append('kind', filters.kind)
    return params.toString()
  }

  const appendOptional = (form: FormData, key: string, value: unknown) => {
    if (value !== undefined && value !== null && value !== '') {
      form.append(key, String(value))
    }
  }

  return {
    // ---- Applications CRUD ------------------------------------------------

    /** GET /api/v1/applications — ordinary applications of the current user (the client's cabinet list) */
    listApplications(page = 1, limit = 50, status = '', filters: ApplicationListFilters = {}) {
      return request<ApplicationsListResponse>(`/api/v1/applications?${listQuery(page, limit, status, filters)}`)
    },

    /**
     * GET /api/v1/applications — the dealer/distributor list that also contains fast deals.
     * A status filter of ordinary applications excludes the fast deals (the server decides).
     */
    listApplicationsMerged(page = 1, limit = 50, status = '', filters: ApplicationListFilters = {}) {
      return request<MergedApplicationsListResponse>(`/api/v1/applications?${listQuery(page, limit, status, filters)}`)
    },

    /** GET /api/v1/applications/:id — get a single application (wrapped) */
    getApplication(id: EntityId) {
      return request<ApplicationDetailResponse>(`/api/v1/applications/${id}`)
    },

    /** GET /api/v1/applications/:id — get a single application (flat response) */
    getApplicationById(id: EntityId) {
      return request<Application>(`/api/v1/applications/${id}`)
    },

    updateApplicationItems(
      id: EntityId,
      items: Array<{
        line_id: EntityId
        kind: 'vehicle' | 'special_equipment'
        leasing_purpose: string | null
        leasing_purposes?: string[] | null
        regions: string[]
        region: string | null
        comment: string | null
      }>,
    ) {
      return request<{ ok: boolean }>(`/api/v1/applications/${id}/items`, {
        method: 'PUT',
        body: { items },
      })
    },

    setSpecialEquipmentPrice(
      applicationId: EntityId,
      itemId: EntityId,
      agreedPrice: string,
    ) {
      return request<DealerRequestedPriceResponse>(
        `/api/v1/dealer/leasing-applications/${applicationId}/items/${itemId}/price`,
        {
          method: 'PATCH',
          body: { agreed_price: agreedPrice },
        },
      )
    },

    /** POST /api/v1/applications/:id/documents/attach */
    attachDocuments(id: EntityId, documentIds: EntityId[]) {
      return request<void>(`/api/v1/applications/${id}/documents/attach`, {
        method: 'POST',
        body: { document_ids: documentIds },
      })
    },

    /** POST /api/v1/applications/draft — create application draft */
    createApplications(body: CreateApplicationPayload) {
      return request<CreateApplicationResponse>('/api/v1/applications/draft', {
        method: 'POST',
        body,
      })
    },

    /** POST /api/v1/applications/draft — create an initial application */
    createInitialApplication(body: CreateApplicationBody) {
      return request<ApplicationInitResponse>('/api/v1/applications/draft', {
        method: 'POST',
        body,
      })
    },

    /** PUT /api/v1/applications/:id/status — change application status */
    updateApplicationStatus(id: EntityId, body: StatusUpdateBody) {
      return request<void>(`/api/v1/applications/${id}/status`, {
        method: 'PUT',
        body,
      })
    },

    updateAdditionalOptions(
      id: UUID,
      body: {
        application_vehicle_id: UUID
        equipments?: ApplicationEquipmentOption[]
        services?: ApplicationServiceOption[]
      },
    ) {
      return request<Record<string, unknown>>(`/api/v1/applications/${id}/additional-options`, {
        method: 'PATCH',
        body,
      })
    },

    // ---- Distributor dealer assignment -----------------------------------

    /** GET /api/v1/distributor/dealer-groups */
    listDealerGroups(applicationId?: EntityId, brand?: string) {
      const params = new URLSearchParams()
      if (applicationId) params.set('applicationId', applicationId)
      if (brand) params.set('brand', brand)
      const query = params.toString()
      return request<DealerGroupsResponse>(
        `/api/v1/distributor/dealer-groups${query ? `?${query}` : ''}`,
      )
    },

    /** GET /api/v1/distributor/dealers */
    listDistributorDealers(limit = 200) {
      const params = new URLSearchParams({
        page: '1',
        limit: limit.toString(),
      })
      return request<DistributorDealersResponse>(
        `/api/v1/distributor/dealers?${params.toString()}`,
      )
    },

    /** PUT /api/v1/:applicationId/:applicationVehicleId/diler */
    assignVehicleDealer(
      applicationId: EntityId,
      applicationVehicleId: EntityId,
      body: AssignDealerPayload,
    ) {
      return request<ApplicationVehicleMutationResponse>(
        `/api/v1/${applicationId}/${applicationVehicleId}/diler`,
        { method: 'PUT', body },
      )
    },

    distributeDealer(applicationId: EntityId, body: DealerDistributionPayload) {
      return request<{ application_vehicle_ids: EntityId[] }>(
        `/api/v1/applications/${applicationId}/dealer-distributions`,
        { method: 'POST', body },
      )
    },

    // ---- Application employees -------------------------------------------

    /** GET /api/v1/applications/:id/vehicles/:vehicleId/employees/search */
    searchApplicationVehicleEmployees(
      applicationId: EntityId,
      applicationVehicleId: EntityId,
      query = '',
      limit = 20,
    ) {
      const params = new URLSearchParams({ limit: limit.toString() })
      if (query) params.set('query', query)
      return request<EmployeesSearchResponse>(
        `/api/v1/applications/${applicationId}/vehicles/${applicationVehicleId}/employees/search?${params.toString()}`,
      )
    },

    /** PATCH /api/v1/applications/:id/vehicles/:vehicleId/employees */
    updateApplicationVehicleEmployees(
      applicationId: EntityId,
      applicationVehicleId: EntityId,
      body: AssignEmployeesPayload,
    ) {
      return request<ApplicationVehicleMutationResponse>(
        `/api/v1/applications/${applicationId}/vehicles/${applicationVehicleId}/employees`,
        {
          method: 'PATCH',
          body,
        },
      )
    },

    // ---- Vehicle VIN management -------------------------------------------

    /** GET /api/v1/application-vehicles/:id/available-vins */
    getAvailableVins(applicationVehicleId: EntityId) {
      return request<AvailableVinsResponse>(
        `/api/v1/application-vehicles/${applicationVehicleId}/available-vins`,
      )
    },

    /** PATCH /api/v1/application-vehicles/:id — role-dispatched VIN assign */
    assignVin(applicationVehicleId: EntityId, vehicleId: EntityId) {
      return request<AssignVinResponse>(
        `/api/v1/application-vehicles/${applicationVehicleId}`,
        {
          method: 'PATCH',
          body: { vehicle_id: vehicleId },
        },
      )
    },

    /** POST /api/v1/application-vehicles/:id/dealer-action */
    runDealerVehicleAction(applicationVehicleId: EntityId, payload: DealerVehicleActionPayload) {
      const files = payload.files || []
      if (files.length > 0) {
        const form = new FormData()
        form.append('action', payload.action)
        appendOptional(form, 'comment', payload.comment)
        appendOptional(form, 'reserve_expires_at', payload.reserve_expires_at)
        appendOptional(form, 'discount_type', payload.discount_type)
        appendOptional(form, 'discount_value', payload.discount_value)
        appendOptional(form, 'markup_type', payload.markup_type)
        appendOptional(form, 'markup_value', payload.markup_value)
        appendOptional(form, 'show_catalog_price', payload.show_catalog_price)
        appendOptional(form, 'final_price', payload.final_price)
        appendOptional(form, 'vin', payload.vin)
        for (const file of files) {
          form.append('files', file)
        }
        return request<DealerVehicleActionResponse>(
          `/api/v1/application-vehicles/${applicationVehicleId}/dealer-action`,
          {
            method: 'POST',
            body: form,
          },
        )
      }

      const { files: _files, ...body } = payload
      return request<DealerVehicleActionResponse>(
        `/api/v1/application-vehicles/${applicationVehicleId}/dealer-action`,
        {
          method: 'POST',
          body,
        },
      )
    },
  }
}
