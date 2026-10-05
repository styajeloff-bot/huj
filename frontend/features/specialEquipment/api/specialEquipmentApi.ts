import type { UUID } from '~/types/ids'
import { resolveSpecialEquipmentApiBase } from '../apiBase'
import { shouldInjectSpecialEquipmentCategoriesFailure } from '../e2eFaultInjection'
import type {
  SpecialEquipmentCategoriesResponse,
  SpecialEquipmentCategoryContextResponse,
  SpecialEquipmentCompatibleAttachmentsResponse,
  SpecialEquipmentCartResponse,
  SpecialEquipmentCreatePaymentResponse,
  SpecialEquipmentCreateScheduledPaymentResponse,
  SpecialEquipmentLeasingScheduleResponse,
  SpecialEquipmentFavoritesResponse,
  SpecialEquipmentFacetsResponse,
  SpecialEquipmentMarksResponse,
  SpecialEquipmentOrderResponse,
  SpecialEquipmentOrdersResponse,
  SpecialEquipmentPaymentConfirmationResponse,
  SpecialEquipmentPaymentStatusResponse,
  SpecialEquipmentPaymentMethod,
  SpecialEquipmentProductDetail,
  SpecialEquipmentProductsResponse,
} from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
type StorefrontApiPath = (path: string) => string

export interface SpecialEquipmentProductsParams {
  category_path?: string
  mark_id?: UUID[]
  model_id?: UUID[]
  modification_id?: UUID[]
  body_color_id?: UUID[]
  interior_color_id?: UUID[]
  trim_id?: UUID[]
  superstructure_id?: UUID[]
  availability?: Array<'available' | 'on_order'>
  condition?: 'new' | 'used'
  price_min?: string
  price_max?: string
  mileage_min?: string
  mileage_max?: string
  engine_hours_min?: string
  engine_hours_max?: string
  city_id?: UUID
  warehouse_id?: UUID
  min_in_stock?: string
  search?: string
  description_include?: string
  description_exclude?: string
  sort: string
  page: number
  page_size: number
  attribute?: string[]
}

export type SpecialEquipmentFacetsParams = Omit<
  SpecialEquipmentProductsParams,
  'sort' | 'page' | 'page_size'
>

export const createSpecialEquipmentApi = (
  config: RuntimeConfig,
  apiPath?: StorefrontApiPath,
) => {
  const baseURL = resolveSpecialEquipmentApiBase(config, import.meta.server)
  const forwardedAuthHeaders = import.meta.server
    ? useRequestHeaders(['cookie', 'authorization'])
    : {}
  const injectCategoriesFailure = shouldInjectSpecialEquipmentCategoriesFailure({
    enabled: config.e2eFaultInjectionEnabled,
    isServer: import.meta.server === true,
    cookieHeader: forwardedAuthHeaders.cookie,
  })
  const endpoint = (path: string) => apiPath
    ? apiPath(`/special-equipment${path}`)
    : `/api/v1/special-equipment${path}`
  const request = <T>(url: string, options: Record<string, unknown> = {}) => {
    const endpointHeaders = (options.headers ?? {}) as Record<string, string>
    return $fetch<T>(url, {
      baseURL,
      credentials: 'include',
      ...options,
      headers: {
        ...forwardedAuthHeaders,
        ...endpointHeaders,
      },
    })
  }
  return {
    getCategories: () =>
      injectCategoriesFailure
        ? Promise.reject(new Error('Injected E2E categories failure'))
        : request<SpecialEquipmentCategoriesResponse>(endpoint('/categories')),

    resolveCategoryPath: (path: string[]) =>
      request<SpecialEquipmentCategoryContextResponse>(
        endpoint('/categories/resolve'),
        { query: { path: path.join('/') } },
      ),

    getMarks: () =>
      request<SpecialEquipmentMarksResponse>(endpoint('/marks')),

    getProducts: (params: SpecialEquipmentProductsParams) =>
      request<SpecialEquipmentProductsResponse>(endpoint('/products'), {
        query: params,
      }),

    getFacets: (params: SpecialEquipmentFacetsParams) =>
      request<SpecialEquipmentFacetsResponse>(endpoint('/facets'), {
        query: params,
      }),

    getProduct: (productId: UUID, categoryPath: string[] = []) =>
      request<SpecialEquipmentProductDetail>(
        endpoint(`/products/${encodeURIComponent(productId)}`),
        { query: categoryPath.length ? { category_path: categoryPath.join('/') } : undefined },
      ),

    getCompatibleAttachments: (productId: UUID) =>
      request<SpecialEquipmentCompatibleAttachmentsResponse>(
        endpoint(`/products/${encodeURIComponent(productId)}/compatible-attachments`),
      ),

    getFavorites: () =>
      request<SpecialEquipmentFavoritesResponse>(endpoint('/favorites'), {
        _skipAuthRefresh: true,
      }),

    addFavorite: (productId: UUID) =>
      request<void>(
        endpoint(`/favorites/${encodeURIComponent(productId)}`),
        { method: 'PUT', _skipAuthRefresh: true },
      ),

    removeFavorite: (productId: UUID) =>
      request<void>(
        endpoint(`/favorites/${encodeURIComponent(productId)}`),
        { method: 'DELETE', _skipAuthRefresh: true },
      ),

    getCartItems: () =>
      request<SpecialEquipmentCartResponse>(endpoint('/cart-items'), {
        _skipAuthRefresh: true,
      }),

    getOrders: () => request<SpecialEquipmentOrdersResponse>(endpoint('/purchase-orders')),

    getOrder: (orderId: UUID) => request<SpecialEquipmentOrderResponse>(
      endpoint(`/purchase-orders/${encodeURIComponent(orderId)}`),
    ),

    createRemainingPayment: (
      orderId: UUID,
      paymentMethod: SpecialEquipmentPaymentMethod,
      idempotencyKey: string,
    ) => request<SpecialEquipmentCreatePaymentResponse>(
      endpoint(`/purchase-orders/${encodeURIComponent(orderId)}/payments`),
      {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: { payment_method: paymentMethod },
      },
    ),

    getPaymentSchedule: (orderId: UUID) => request<SpecialEquipmentLeasingScheduleResponse>(
      endpoint(`/purchase-orders/${encodeURIComponent(orderId)}/payment-schedule`),
    ),

    createScheduledPayment: (
      orderId: UUID,
      scheduleId: UUID,
      paymentMethod: SpecialEquipmentPaymentMethod,
      idempotencyKey: string,
    ) => request<SpecialEquipmentCreateScheduledPaymentResponse>(
      endpoint(`/purchase-orders/${encodeURIComponent(orderId)}/payment-schedule/${encodeURIComponent(scheduleId)}/payments`),
      {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: { payment_method: paymentMethod },
      },
    ),

    getPaymentStatus: (orderId: UUID, paymentId: UUID) => request<SpecialEquipmentPaymentStatusResponse>(
      endpoint(`/purchase-orders/${encodeURIComponent(orderId)}/payments/${encodeURIComponent(paymentId)}/status`),
    ),

    cancelOrder: (orderId: UUID, reason?: string) => request<SpecialEquipmentOrderResponse>(
      endpoint(`/purchase-orders/${encodeURIComponent(orderId)}/cancellation`),
      { method: 'PUT', body: { reason: reason || null } },
    ),

    confirmOfflinePayment: (orderId: UUID, paymentId: UUID) => request<SpecialEquipmentPaymentConfirmationResponse>(
      endpoint(`/purchase-orders/${encodeURIComponent(orderId)}/payments/${encodeURIComponent(paymentId)}/offline-confirmation`),
      { method: 'PUT' },
    ),
  }
}
