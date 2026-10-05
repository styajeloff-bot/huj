import type { City, Company } from '~/types/features'
import type {
  Warehouse,
  WarehouseAccessRule,
  CreateWarehouseRequest,
  UpdateWarehouseRequest,
  CreateWarehouseAccessRulesRequest,
  UpdateWarehouseAccessRuleRequest,
  WarehousesPagination,
  WarehousesListParams,
  AccessRulesListParams,
  WarehouseMark,
  WarehouseCategory,
  WarehouseStorefront,
  WarehouseDealerGroup,
  WarehouseDeleteCounts,
  WarehouseRetainedItem,
  WarehouseBlocker,
  WarehouseDeletePreviewResponse,
  WarehouseCascadeDeleteRequest,
  WarehouseCascadeDeleteResponse
} from '../types'

export type {
  Warehouse,
  WarehouseAccessRule,
  CreateWarehouseRequest,
  UpdateWarehouseRequest,
  CreateWarehouseAccessRulesRequest,
  UpdateWarehouseAccessRuleRequest,
  WarehousesPagination,
  WarehousesListParams,
  AccessRulesListParams,
  WarehouseMark,
  WarehouseCategory,
  WarehouseStorefront,
  WarehouseDealerGroup,
  WarehouseDeleteCounts,
  WarehouseRetainedItem,
  WarehouseBlocker,
  WarehouseDeletePreviewResponse,
  WarehouseCascadeDeleteRequest,
  WarehouseCascadeDeleteResponse
} from '../types'

export type { City, Company } from '~/types/features'

export interface VehicleDeletionReason {
  type: string
  count: number
  description: string
}

export interface VehicleDeletionCheck {
  can_delete: boolean
  vin: string
  name: string
  blocking_reasons: VehicleDeletionReason[]
}

export interface WarehouseDeletionCheck {
  warehouse_id: string
  requested_count: number
  deletable_count: number
  blocked_count: number
  blocking_reasons: (VehicleDeletionReason & { vehicle_count: number })[]
}

export interface WarehouseBulkDeleteResult {
  warehouse_id: string
  requested_count: number
  deleted_count: number
  skipped_count: number
  skipped: {
    vehicle_id: string
    vin: string
    blocking_reasons: VehicleDeletionReason[]
  }[]
}

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createWarehousesApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  return {
    getWarehouses: (params?: WarehousesListParams) => {
      const searchParams = new URLSearchParams()
      if (params) {
        if (params.page) searchParams.append('page', String(params.page))
        if (params.limit) searchParams.append('limit', String(params.limit))
        if (params.search) searchParams.append('search', params.search)
        if (params.brand_id) searchParams.append('brand_id', params.brand_id)
        if (params.brand) searchParams.append('brand', params.brand)
        if (params.city_id) searchParams.append('city_id', params.city_id)
        if (params.access_type) searchParams.append('access_type', params.access_type)
        if (params.owner_company_id) searchParams.append('owner_company_id', params.owner_company_id)
        if (params.is_active !== undefined) searchParams.append('is_active', String(params.is_active))
      }
      const query = searchParams.toString()
      return request<{ warehouses: Warehouse[]; pagination: WarehousesPagination }>(
        `/api/v1/admin/warehouses${query ? `?${query}` : ''}`
      )
    },

    getWarehouse: (id: string) =>
      request<{ warehouse: Warehouse }>(`/api/v1/admin/warehouses/${id}`),

    createWarehouse: (body: CreateWarehouseRequest) =>
      request<{ warehouse: Warehouse; message?: string }>('/api/v1/admin/warehouses', {
        method: 'POST',
        body
      }),

    updateWarehouse: (id: string, body: UpdateWarehouseRequest) =>
      request<{ warehouse: Warehouse; message?: string }>(`/api/v1/admin/warehouses/${id}`, {
        method: 'PUT',
        body
      }),

    deleteWarehouse: (id: string) =>
      request(`/api/v1/admin/warehouses/${id}`, { method: 'DELETE' }),

    getDeletePreview: async (id: string) => {
      try {
        return await request<WarehouseDeletePreviewResponse>(`/api/v1/admin/warehouses/${id}/delete-preview`)
      } catch (err: unknown) {
        const error = err as { statusCode?: number; status?: number; response?: { status?: number } }
        if (error?.statusCode === 404 || error?.status === 404 || error?.response?.status === 404) {
          return await request<WarehouseDeletePreviewResponse>(`/api/v1/warehouses/${id}/delete-preview`)
        }
        throw err
      }
    },

    cascadeDeleteWarehouse: async (id: string, body: WarehouseCascadeDeleteRequest) => {
      try {
        return await request<WarehouseCascadeDeleteResponse>(`/api/v1/admin/warehouses/${id}/cascade-delete`, {
          method: 'POST',
          body
        })
      } catch (err: unknown) {
        const error = err as { statusCode?: number; status?: number; response?: { status?: number } }
        if (error?.statusCode === 404 || error?.status === 404 || error?.response?.status === 404) {
          return await request<WarehouseCascadeDeleteResponse>(`/api/v1/warehouses/${id}/cascade-delete`, {
            method: 'POST',
            body
          })
        }
        throw err
      }
    },

    getMyWarehouses: () =>
      request<{ warehouses: Warehouse[] }>('/api/v1/admin/warehouses?limit=500'),

    getWarehouseMarks: () =>
      request<{ marks?: WarehouseMark[]; items?: WarehouseMark[] }>('/api/v1/special-equipment/marks'),

    getWarehouseMarkOptions: (params: { search?: string; page: number; limit: number }) =>
      request<{ marks: WarehouseMark[]; pagination: WarehousesPagination }>('/api/v1/warehouses/marks', {
        query: params
      }),

    getWarehouseCategories: (brandIds: string[], page: number, limit: number) => {
      const query = new URLSearchParams({ page: String(page), limit: String(limit) })
      brandIds.forEach(id => query.append('brand_ids', id))
      return request<{ categories: WarehouseCategory[]; pagination: WarehousesPagination }>(
        `/api/v1/warehouses/categories?${query}`
      )
    },

    getBrands: () =>
      request<{ brands: string[] }>('/api/v1/admin/warehouses/brands'),

    getCities: () =>
      request<{ cities: City[] }>('/api/v1/admin/cities'),

    createCity: (name: string) =>
      request<{ message: string; city: City }>('/api/v1/admin/cities', {
        method: 'POST',
        body: { name }
      }),

    getAccessRules: (params?: AccessRulesListParams) => {
      const searchParams = new URLSearchParams()
      if (params) {
        if (params.page) searchParams.append('page', String(params.page))
        if (params.limit) searchParams.append('limit', String(params.limit))
        if (params.warehouse_id) searchParams.append('warehouse_id', params.warehouse_id)
        if (params.target_id) searchParams.append('target_id', params.target_id)
        if (params.is_active !== undefined) searchParams.append('is_active', String(params.is_active))
      }
      const query = searchParams.toString()
      return request<{ rules: WarehouseAccessRule[]; pagination: WarehousesPagination }>(
        `/api/v1/admin/warehouses/access-rules${query ? `?${query}` : ''}`
      )
    },

    createAccessRules: (body: CreateWarehouseAccessRulesRequest) =>
      request<{ rules?: WarehouseAccessRule[]; message?: string }>(
        '/api/v1/admin/warehouses/access-rules',
        {
          method: 'POST',
          body
        }
      ),

    updateAccessRule: (ruleId: string, body: UpdateWarehouseAccessRuleRequest) =>
      request<{ rule: WarehouseAccessRule; message?: string }>(
        `/api/v1/admin/warehouses/access-rules/${ruleId}`,
        {
          method: 'PATCH',
          body
        }
      ),

    deleteAccessRule: (ruleId: string) =>
      request(`/api/v1/admin/warehouses/access-rules/${ruleId}`, { method: 'DELETE' }),

    getDealerGroups: () =>
      request<{ dealer_groups?: WarehouseDealerGroup[]; items?: WarehouseDealerGroup[] }>(
        '/api/v1/admin/dealer-groups?limit=200&is_active=true'
      ),

    getStorefronts: () =>
      request<{ items?: WarehouseStorefront[]; storefronts?: WarehouseStorefront[] }>(
        '/api/v1/admin/storefronts'
      ),

    getCompanies: (params?: { company_type?: string; search?: string; page?: number; limit?: number }) => {
      const searchParams = new URLSearchParams()
      if (params?.company_type) searchParams.append('company_type', params.company_type)
      if (params?.limit) searchParams.append('limit', String(params.limit))
      if (params?.page) searchParams.append('page', String(params.page))
      if (params?.search) searchParams.append('search', params.search)
      const query = searchParams.toString()
      return request<{ companies: Company[]; pagination: WarehousesPagination }>(`/api/v1/companies${query ? `?${query}` : ''}`)
    },

    getUserCompanies: () =>
      request<{ companies: Company[] }>('/api/v1/users/me/companies'),

    // Vehicle deletion support for admin
    checkVehicleDeletion: (id: string) =>
      request<VehicleDeletionCheck>(`/api/v1/admin/vehicles/${id}/deletion-check`),

    deleteVehicle: (id: string, body: { confirmation: string; reason?: string }) =>
      request<{ deleted: true; vehicle_id: string; cleaned_relations: Record<string, number> }>(
        `/api/v1/admin/vehicles/${id}`,
        { method: 'DELETE', body }
      ),

    unbindAllVehicles: (id: string) =>
      request<{ warehouse_id: string; unbound_count: number }>(
        `/api/v1/admin/warehouses/${id}/vehicles`,
        { method: 'DELETE', body: { confirmed: true } }
      ),

    checkWarehouseDeletion: (id: string) =>
      request<WarehouseDeletionCheck>(`/api/v1/admin/warehouses/${id}/vehicles/deletion-check`),

    deleteWarehouseVehicles: (id: string, confirmation: string) =>
      request<WarehouseBulkDeleteResult>(`/api/v1/admin/warehouses/${id}/vehicles/bulk-delete`, {
        method: 'POST',
        body: { confirmed: true, confirmation }
      })
  }
}
