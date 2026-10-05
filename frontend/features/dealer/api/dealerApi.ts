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
// Clients
// ---------------------------------------------------------------------------

export interface DealerClient {
  id: string
  email: string
  name: string
  [key: string]: unknown
}

export interface DealerClientsStats {
  [key: string]: unknown
}

export interface DealerClientsResponse {
  clients: DealerClient[]
  stats: DealerClientsStats
  pagination: Pagination
}

export interface InviteClientPayload {
  email: string
  name: string
  message: string
}

// ---------------------------------------------------------------------------
// Inventory
// ---------------------------------------------------------------------------

export interface DealerVehicle {
  id: string
  [key: string]: unknown
}

export interface DealerInventoryResponse {
  vehicles: DealerVehicle[]
  stats: Record<string, unknown>
  brands: string[]
  years: number[]
  pagination: Pagination
}

export interface DeleteVehicleResponse {
  message: string
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export interface DealerProfile {
  [key: string]: unknown
}

export interface DealerProfileResponse {
  profile: DealerProfile
  stats: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface DealerReport {
  id: string
  [key: string]: unknown
}

export interface DealerReportsResponse {
  reports: DealerReport[]
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createDealerApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, { baseURL: config.public.apiBase, credentials: 'include', ...options })

  return {
    // ---- Clients ----------------------------------------------------------

    getClients(query: string) {
      return request<DealerClientsResponse>(`/api/v1/dealer/clients?${query}`)
    },

    inviteClient(payload: InviteClientPayload) {
      return request<void>('/api/v1/dealer/invite-client', {
        method: 'POST',
        body: payload,
      })
    },

    // ---- Inventory --------------------------------------------------------

    getInventory(query: string) {
      return request<DealerInventoryResponse>(`/api/v1/dealer/inventory?${query}`)
    },

    deleteVehicle(vehicleId: string) {
      return request<DeleteVehicleResponse>(`/api/v1/dealer/inventory/${vehicleId}`, {
        method: 'DELETE',
      })
    },

    // Profile read/write moved to authApi.getMyProfile/patchMyProfile
    // (see Phase 13 R13a — /dealer/profile consolidated into /users/me).

    // ---- Reports ----------------------------------------------------------

    getReports(query: string) {
      return request<DealerReportsResponse>(`/api/v1/dealer/reports?${query}`)
    },

    exportReportsXlsx(query: string = '') {
      const separator = query ? '&' : ''
      return request<Blob>(
        `/api/v1/dealer/reports?${query}${separator}format=xlsx`,
        { responseType: 'blob' },
      )
    },
  }
}
