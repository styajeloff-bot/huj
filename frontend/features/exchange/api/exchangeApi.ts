import type {
  VehicleId,
  EntityId,
  DealerOption,
  ExchangeCartItem,
  ExchangeRequest,
  ExchangeBid,
  ExchangeRequestFile,
  ExchangeRequestId,
  ExchangeRequestStatus,
  WarehouseInfo,
  BidComment,
} from '../types'
import type { UUID } from '~/types/ids'
import { withNotificationCompanyContext } from '~/utils/apiCompanyContext'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface ExchangeCartResponse {
  cart_items: ExchangeCartItem[]
  summary: {
    total_items: number
    total_amount: number
  }
}

export interface ExchangeRequestListResponse {
  requests: ExchangeRequest[]
  pagination: {
    page: number
    limit: number
    total: number
    pages: number
  }
}

interface DistributorExchangeRequestListResponse {
  items: ExchangeRequest[]
  pagination: ExchangeRequestListResponse['pagination']
}

export interface WarehouseListResponse {
  warehouses: WarehouseInfo[]
}

export interface DealerOptionsResponse {
  options: DealerOption[]
}

/** Partial update body for `PATCH /exchange/cart/{item_id}`. */
export interface PatchExchangeCartItemRequest {
  quantity?: number
  expiration_at?: string | null
  discount_type?: string | null
  discount_value?: number | null
  /** Selected warehouse ids (client-side state only; not persisted server-side yet). */
  warehouses?: EntityId[]
  /** Selected dealer option ids (client-side state only). */
  options?: EntityId[]
  /** Per-dealer comment `{dealer_id, comment}` (client-side state only). */
  dealer_comment?: { dealer_id: UUID; comment: string }
  selected_support_ids?: UUID[]
}

interface BidOptionsPayload {
  option_ids?: UUID[]
}

const toBidTransportBody = <T extends BidOptionsPayload>(body: T) => {
  const { option_ids, ...fields } = body
  return option_ids === undefined
    ? fields
    : { ...fields, dealer_option_ids: option_ids }
}

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createExchangeApi = (config: RuntimeConfig, notificationCompanyContext?: () => unknown) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(withNotificationCompanyContext(url, notificationCompanyContext?.()), {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    downloadUrl(path: string): string {
      const base = String(config.public.apiBase || '').replace(/\/$/, '')
      const contextualPath = withNotificationCompanyContext(path, notificationCompanyContext?.(), base)
      return path.startsWith('/api/v1/') ? `${base}${contextualPath}` : contextualPath
    },
    // ---- Dealer Options ----
    getDealerOptions: () =>
      request<DealerOptionsResponse>('/api/v1/exchange/dealer-options'),

    getAllDealerOptions: () =>
      request<DealerOptionsResponse>('/api/v1/exchange/dealer-options', {
        params: { include_inactive: true },
      }),

    createDealerOption: (body: { name: string; sort_order?: number }) =>
      request<{ option: DealerOption }>('/api/v1/exchange/dealer-options', { method: 'POST', body }),

    updateDealerOption: (id: UUID, body: Partial<DealerOption>) =>
      request<{ option: DealerOption }>(`/api/v1/exchange/dealer-options/${id}`, { method: 'PUT', body }),

    deleteDealerOption: (id: UUID) =>
      request<{ message: string }>(`/api/v1/exchange/dealer-options/${id}`, { method: 'DELETE' }),

    // ---- Exchange Cart (LC) ----
    getCart: () =>
      request<ExchangeCartResponse>('/api/v1/exchange/cart'),

    /** Lightweight projection: only `{count: N}`. */
    getCartCount: () =>
      request<{ count: number }>('/api/v1/exchange/cart?fields=count'),

    /** Create cart item (POST /exchange/cart). Upserts on duplicate (user, vehicle). */
    createCartItem: (body: { vehicle_id: VehicleId; quantity?: number; warehouse_id?: EntityId }) =>
      request<{ message: string; item: unknown; created: boolean }>(
        '/api/v1/exchange/cart',
        { method: 'POST', body },
      ),

    /** Consolidated PATCH — accepts any subset of editable fields. */
    updateCartItem: (itemId: UUID, patch: PatchExchangeCartItemRequest) =>
      request<{ message: string; item: unknown }>(
        `/api/v1/exchange/cart/${itemId}`,
        { method: 'PATCH', body: patch },
      ),

    uploadCartItemFile: async (itemId: UUID, file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<{ message: string; cart_item: unknown }>(
        `/api/v1/exchange/cart/${itemId}/upload`,
        { method: 'POST', body: formData },
      )
    },

    removeCartItem: (itemId: UUID) =>
      request<{ message: string }>(`/api/v1/exchange/cart/${itemId}`, { method: 'DELETE' }),

    clearCart: () =>
      request<{ message: string; deleted_count: number }>('/api/v1/exchange/cart', { method: 'DELETE' }),

    submitCart: () =>
      request<{ message: string; request_ids: UUID[]; count: number }>(
        '/api/v1/exchange/cart/submit',
        { method: 'POST' },
      ),

    getAvailableWarehouses: (vehicleId: VehicleId) =>
      request<WarehouseListResponse>(`/api/v1/exchange/cart/warehouses/${vehicleId}`),

    // ---- Exchange Requests (distributor read-only view) ----
    getDistributorRequests: async (query: { status?: ExchangeRequestStatus; page?: number; limit?: number } = {}): Promise<ExchangeRequestListResponse> => {
      const result = await request<DistributorExchangeRequestListResponse>('/api/v1/exchange/distributor/requests', { query })
      return { requests: result.items, pagination: result.pagination }
    },

    getDistributorStatusCounts: () =>
      request<{ counts: Record<ExchangeRequestStatus, number> }>('/api/v1/exchange/distributor/requests/counts'),

    getDistributorRequestDetail: (id: ExchangeRequestId) =>
      request<{ request: ExchangeRequest }>(`/api/v1/exchange/distributor/requests/${id}`),

    withdrawBid: (id: UUID) =>
      request<void>(`/api/v1/exchange/bids/${id}`, { method: 'DELETE' }),

    // ---- Exchange Requests (LC view) ----
    getLcStatusCounts: () =>
      request<{ counts: { open: number; deal: number; archived: number } }>(
        '/api/v1/exchange/requests/counts'
      ),

    getLcRequests: (params: { status?: ExchangeRequestStatus; page?: number; limit?: number } = {}) =>
      request<ExchangeRequestListResponse>('/api/v1/exchange/requests', {
        params,
      }),

    getLcRequestDetail: (id: ExchangeRequestId) =>
      request<{ request: ExchangeRequest }>(`/api/v1/exchange/requests/${id}`),

    archiveRequest: (id: ExchangeRequestId) =>
      request<{ message: string }>(`/api/v1/exchange/requests/${id}`, {
        method: 'PATCH',
        body: { status: 'archived' }
      }),

    resubmitRequest: (id: ExchangeRequestId) =>
      request<{ message: string; request_id: ExchangeRequestId }>(
        `/api/v1/exchange/requests/${id}`,
        { method: 'PATCH', body: { status: 'open' } }
      ),

    confirmDeal: (_requestId: ExchangeRequestId, bidId: UUID) =>
      request<{ message: string; bid: ExchangeBid }>(
        `/api/v1/exchange/bids/${bidId}/approve`,
        { method: 'PUT' }
      ),

    uploadKpToBid: async (requestId: ExchangeRequestId, bidId: UUID, file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<{ message: string; bid: ExchangeBid }>(
        `/api/v1/exchange/requests/${requestId}/bids/${bidId}/kp`,
        { method: 'POST', body: formData }
      )
    },

    duplicateRequest: (id: ExchangeRequestId) =>
      request<{ message: string; request_id: ExchangeRequestId }>(
        `/api/v1/exchange/requests/${id}`,
        { method: 'PATCH', body: { status: 'open' } }
      ),

    commentOnBid: (_requestId: ExchangeRequestId, bidId: UUID, comment: string) =>
      request<{ message: string; comment: BidComment }>(
        `/api/v1/exchange/bids/${bidId}/comments`,
        { method: 'POST', body: { comment } }
      ),

    counterOffer: (bidId: UUID, body: { price: number; comment?: string }) =>
      request<{ message: string; bid: ExchangeBid }>(
        `/api/v1/exchange/bids/${bidId}/counter-offer`,
        { method: 'POST', body }
      ),

    // ---- Exchange Requests (Dealer view) ----
    getDealerStatusCounts: () =>
      request<{ counts: { open: number; deal: number; archived: number } }>(
        '/api/v1/exchange/requests/dealer/counts'
      ),

    getDealerRequests: (params: { status?: ExchangeRequestStatus; page?: number; limit?: number } = {}) =>
      request<ExchangeRequestListResponse>('/api/v1/exchange/requests/dealer', {
        params,
      }),

    getDealerRequestDetail: (id: ExchangeRequestId) =>
      request<{ request: ExchangeRequest }>(`/api/v1/exchange/requests/dealer/${id}`),

    // ---- Exchange Bids (Dealer) ----
    createBid: (body: {
      request_id: ExchangeRequestId
      price: number
      quantity?: number
      comment?: string
      option_ids?: UUID[]
    }) =>
      request<{ message: string; bid: ExchangeBid }>('/api/v1/exchange/bids', {
        method: 'POST',
        body: toBidTransportBody(body),
      }),

    updateBid: (bidId: UUID, body: {
      price?: number
      quantity?: number
      comment?: string
      option_ids?: UUID[]
    }) =>
      request<{ message: string; bid: ExchangeBid }>(`/api/v1/exchange/bids/${bidId}`, {
        method: 'PUT',
        body: toBidTransportBody(body),
      }),

    uploadBidFile: async (bidId: UUID, file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<{ message: string; bid: ExchangeBid }>(
        `/api/v1/exchange/bids/${bidId}/file`,
        { method: 'POST', body: formData }
      )
    },

    getMyBids: (params: { page?: number; limit?: number } = {}) =>
      request<{ bids: ExchangeBid[] }>('/api/v1/exchange/bids/', { params }),

    respondToKp: (bidId: UUID, body: { action: 'accepted' | 'rejected'; comment?: string | null }) =>
      request<{ message: string; bid: ExchangeBid }>(
        `/api/v1/exchange/bids/${bidId}/kp/respond`,
        { method: 'POST', body }
      ),
  }
}
