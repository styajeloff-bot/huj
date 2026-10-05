import type { UUID } from '~/types/ids'

export type RuntimeConfigLike = ReturnType<typeof useRuntimeConfig> | { public: { apiBase?: string } }

export interface PositionItem {
  id: UUID
  name: string
  code: string
  is_active: boolean
  created_at: string
  updated_at?: string
}

export interface EmployeeItem {
  user_id: UUID
  name?: string | null
  phone?: string | null
  additional_phone?: string | null
  company_id: UUID
  company_name?: string | null
  role: string
  sub_role?: string | null
  position_id?: UUID | null
  position_name?: string | null
  can_view_applications: boolean
  can_create_applications: boolean
  can_create_employees?: boolean
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
  can_edit?: boolean
}

export type EmployeeRole = 'dealer' | 'distributor' | 'client' | 'leasing_company' | 'carcraft_employee'

export interface EmployeeObject {
  id: UUID
  name: string
}

type EmployeeListFields = Omit<EmployeeItem, 'company_id'> & {
  brands: EmployeeObject[]
  warehouses: EmployeeObject[]
  distributors: EmployeeObject[]
}

export type EmployeeListItem = EmployeeListFields & (
  | { row_type: 'company'; user_company_id: UUID; company_id: UUID; company_role: string }
  | { row_type: 'system'; user_company_id: null; company_id: null; company_role: null }
)

export interface EmployeeFilterOptions {
  companies: EmployeeObject[]
  dealers: EmployeeObject[]
  distributors: EmployeeObject[]
  brands: EmployeeObject[]
  warehouses: EmployeeObject[]
}

export interface CreatePositionPayload {
  name: string
  code: string
  is_active?: boolean
}

export interface UpdatePositionPayload {
  name?: string
  code?: string
  is_active?: boolean
}

export interface CreateEmployeePayload {
  name: string
  phone: string
  additional_phone?: string | null
  company_id: UUID
  role: string
  position_id?: UUID | null
  can_view_applications: boolean
  can_create_applications: boolean
  can_create_employees?: boolean
  is_active?: boolean
  sub_role?: string | null
}

export interface UpdateEmployeePayload {
  name?: string
  phone?: string
  additional_phone?: string | null
  company_id?: UUID
  role?: string
  position_id?: UUID | null
  can_view_applications?: boolean
  can_create_applications?: boolean
  can_create_employees?: boolean
  is_active?: boolean
  sub_role?: string | null
}

export type AccessObjectType =
  | 'warehouse'
  | 'brand'
  | 'dealer'
  | 'dealer_warehouse'
  | 'application_creator'

export type AccessType = 'all' | 'selected' | 'except_selected' | 'none'

export interface AccessRuleItem {
  id?: UUID
  access_object: AccessObjectType | string
  access_type: AccessType
  object_id?: string | null
  object_name?: string | null
  is_active?: boolean
  object_ids?: string[]
}

export interface SectionAccessItem {
  section_code: string
  can_view: boolean
}

export interface EmployeeAccessSettings {
  user_id: UUID
  company_id: UUID
  can_create_employees?: boolean
  additional_phone?: string | null
  access_rules: AccessRuleItem[]
  section_access: SectionAccessItem[]
  granter_can_create_employees?: boolean
  available_sections?: string[]
  can_edit?: boolean
}

export interface UpdateEmployeeAccessSettingsRequest {
  additional_phone?: string | null
  can_create_employees?: boolean
  access_rules: AccessRuleItem[]
  section_access: SectionAccessItem[]
}

export interface LookupItem {
  id: string
  name: string
  address?: string | null
  description?: string | null
  phone?: string | null
  [key: string]: unknown
}

export interface LookupResponse {
  items: LookupItem[]
  total?: number
}

export interface EmployeeListParams {
  role?: EmployeeRole
  dealer_id?: UUID
  distributor_id?: UUID
  brand_id?: UUID
  warehouse_id?: UUID
  company_id?: UUID
  position_id?: UUID
  name?: string
  phone?: string
  page?: number | string
  per_page?: number | string
}

export interface EmployeesListResponse {
  items: EmployeeListItem[]
  total: number
  page?: number
  per_page?: number
  pages?: number
}

export interface PositionsListResponse {
  items: PositionItem[]
  total?: number
}

const getBaseUrl = (config: RuntimeConfigLike): string => {
  return config?.public?.apiBase || ''
}

const request = <T>(
  config: RuntimeConfigLike,
  url: string,
  options: Record<string, unknown> = {},
): Promise<T> => {
  return $fetch<T>(url, {
    baseURL: getBaseUrl(config),
    credentials: 'include',
    ...options,
  })
}

export const listPositions = async (
  config: RuntimeConfigLike,
): Promise<PositionsListResponse> => {
  const data = await request<PositionsListResponse | PositionItem[]>(config, '/api/v1/positions', {
    method: 'GET',
  })
  if (Array.isArray(data)) {
    return { items: data, total: data.length }
  }
  return {
    items: data.items ?? [],
    total: data.total ?? (data.items ? data.items.length : 0),
  }
}

export const createPosition = async (
  config: RuntimeConfigLike,
  payload: CreatePositionPayload,
): Promise<PositionItem> => {
  return request<PositionItem>(config, '/api/v1/positions', {
    method: 'POST',
    body: payload,
  })
}

export const updatePosition = async (
  config: RuntimeConfigLike,
  id: UUID,
  payload: UpdatePositionPayload,
): Promise<PositionItem> => {
  return request<PositionItem>(config, `/api/v1/positions/${id}`, {
    method: 'PUT',
    body: payload,
  })
}

export const deactivatePosition = async (
  config: RuntimeConfigLike,
  id: UUID,
): Promise<PositionItem | { success: boolean }> => {
  return request<PositionItem | { success: boolean }>(config, `/api/v1/positions/${id}/deactivate`, {
    method: 'PATCH',
  })
}

export const listEmployees = async (
  config: RuntimeConfigLike,
  params?: EmployeeListParams,
): Promise<EmployeesListResponse> => {
  const queryObj: Record<string, string> = {}
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') {
        queryObj[k] = String(v)
      }
    }
  }
  const queryString = new URLSearchParams(queryObj).toString()
  const url = `/api/v1/employees${queryString ? `?${queryString}` : ''}`
  return request<EmployeesListResponse>(config, url, { method: 'GET' })
}

export const employeeFilterOptions = (
  config: RuntimeConfigLike,
  role?: EmployeeRole,
): Promise<EmployeeFilterOptions> => {
  return request<EmployeeFilterOptions>(config, '/api/v1/employees/filter-options', {
    method: 'GET',
    query: role ? { role } : {},
  })
}

export const createEmployee = async (
  config: RuntimeConfigLike,
  payload: CreateEmployeePayload,
): Promise<EmployeeItem> => {
  return request<EmployeeItem>(config, '/api/v1/employees', {
    method: 'POST',
    body: payload,
  })
}

export const updateEmployee = async (
  config: RuntimeConfigLike,
  userId: UUID,
  companyId: UUID,
  payload: UpdateEmployeePayload,
): Promise<EmployeeItem> => {
  return request<EmployeeItem>(config, `/api/v1/employees/${userId}/${companyId}`, {
    method: 'PUT',
    body: payload,
  })
}

export const deactivateEmployee = async (
  config: RuntimeConfigLike,
  userId: UUID,
  companyId: UUID,
): Promise<EmployeeItem | { success: boolean }> => {
  return request<EmployeeItem | { success: boolean }>(
    config,
    `/api/v1/employees/${userId}/${companyId}/deactivate`,
    {
      method: 'PATCH',
    },
  )
}

export const getEmployeeAccessSettings = async (
  config: RuntimeConfigLike,
  userId: UUID,
  companyId: UUID,
): Promise<EmployeeAccessSettings> => {
  return request<EmployeeAccessSettings>(
    config,
    `/api/v1/employees/${userId}/${companyId}/access-settings`,
    {
      method: 'GET',
    },
  )
}

export const updateEmployeeAccessSettings = async (
  config: RuntimeConfigLike,
  userId: UUID,
  companyId: UUID,
  data: UpdateEmployeeAccessSettingsRequest,
): Promise<EmployeeAccessSettings | { success: boolean }> => {
  return request<EmployeeAccessSettings | { success: boolean }>(
    config,
    `/api/v1/employees/${userId}/${companyId}/access-settings`,
    {
      method: 'PUT',
      body: data,
    },
  )
}

const normalizeLookupResponse = (data: any): LookupResponse => {
  if (Array.isArray(data)) {
    return { items: data, total: data.length }
  }
  return {
    items: data?.items || [],
    total: data?.total ?? (data?.items ? data.items.length : 0),
  }
}

export const lookupWarehouses = async (
  config: RuntimeConfigLike,
  params: { company_id: UUID; q?: string },
): Promise<LookupResponse> => {
  const queryObj: Record<string, string> = { company_id: String(params.company_id) }
  if (params.q) queryObj.q = params.q
  const query = new URLSearchParams(queryObj).toString()
  const data = await request<any>(config, `/api/v1/employees/lookup/warehouses?${query}`, {
    method: 'GET',
  })
  return normalizeLookupResponse(data)
}

export const lookupBrands = async (
  config: RuntimeConfigLike,
  params: { company_id: UUID; q?: string },
): Promise<LookupResponse> => {
  const queryObj: Record<string, string> = { company_id: String(params.company_id) }
  if (params.q) queryObj.q = params.q
  const query = new URLSearchParams(queryObj).toString()
  const data = await request<any>(config, `/api/v1/employees/lookup/brands?${query}`, {
    method: 'GET',
  })
  return normalizeLookupResponse(data)
}

export const lookupDealers = async (
  config: RuntimeConfigLike,
  params: { distributor_company_id: UUID; q?: string },
): Promise<LookupResponse> => {
  const queryObj: Record<string, string> = { distributor_company_id: String(params.distributor_company_id) }
  if (params.q) queryObj.q = params.q
  const query = new URLSearchParams(queryObj).toString()
  const data = await request<any>(config, `/api/v1/employees/lookup/dealers?${query}`, {
    method: 'GET',
  })
  return normalizeLookupResponse(data)
}

export const lookupColleagues = async (
  config: RuntimeConfigLike,
  params: { company_id: UUID; q?: string; exclude_user_id?: UUID },
): Promise<LookupResponse> => {
  const queryObj: Record<string, string> = { company_id: String(params.company_id) }
  if (params.q) queryObj.q = params.q
  if (params.exclude_user_id) queryObj.exclude_user_id = String(params.exclude_user_id)
  const query = new URLSearchParams(queryObj).toString()
  const data = await request<any>(config, `/api/v1/employees/lookup/colleagues?${query}`, {
    method: 'GET',
  })
  return normalizeLookupResponse(data)
}

export const createEmployeesApi = (config: RuntimeConfigLike) => ({
  listPositions: () => listPositions(config),
  createPosition: (payload: CreatePositionPayload) => createPosition(config, payload),
  updatePosition: (id: UUID, payload: UpdatePositionPayload) => updatePosition(config, id, payload),
  deactivatePosition: (id: UUID) => deactivatePosition(config, id),
  listEmployees: (params?: EmployeeListParams) => listEmployees(config, params),
  createEmployee: (payload: CreateEmployeePayload) => createEmployee(config, payload),
  updateEmployee: (userId: UUID, companyId: UUID, payload: UpdateEmployeePayload) =>
    updateEmployee(config, userId, companyId, payload),
  deactivateEmployee: (userId: UUID, companyId: UUID) =>
    deactivateEmployee(config, userId, companyId),
  getEmployeeAccessSettings: (userId: UUID, companyId: UUID) =>
    getEmployeeAccessSettings(config, userId, companyId),
  updateEmployeeAccessSettings: (
    userId: UUID,
    companyId: UUID,
    data: UpdateEmployeeAccessSettingsRequest,
  ) => updateEmployeeAccessSettings(config, userId, companyId, data),
  lookupWarehouses: (params: { company_id: UUID; q?: string }) =>
    lookupWarehouses(config, params),
  lookupBrands: (params: { company_id: UUID; q?: string }) =>
    lookupBrands(config, params),
  lookupDealers: (params: { distributor_company_id: UUID; q?: string }) =>
    lookupDealers(config, params),
  lookupColleagues: (params: { company_id: UUID; q?: string; exclude_user_id?: UUID }) =>
    lookupColleagues(config, params),
})

