import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Request interfaces
// ---------------------------------------------------------------------------

export interface CalculateRequest {
  total_amount: number
  additional_amount?: number
  down_payment: number
  down_payment_percent: number
  lease_term_months: number
  buyout_amount?: number
  vehicle_ids?: UUID[]
  vehicle_price_overrides?: Record<UUID, number>
  vehicle_quantities?: Record<UUID, number>
  selected_support_ids?: UUID[]
  selected_support?: Record<UUID, UUID[]>
}

export interface SendCalculationEmailRequest {
  to: string
  subject: string
  text: string
  html: string
}

export interface SupportStatusRequest {
  vehicle_ids: UUID[]
}

export interface SaveCalculationRequest {
  name: string
  params: Record<string, unknown>
  calculation: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface CalculateResponse {
  calculation: Record<string, unknown>
  support?: Record<string, unknown> | null
}

export interface SupportStatusResponse {
  items: Record<string, unknown>
}

export interface SavedCalculation {
  id: UUID
  name: string
  vehicle_price?: number
  monthly_payment?: number
  created_at?: string
  params: Record<string, unknown>
  calculation: Record<string, unknown>
}

export interface SaveCalculationResponse {
  calculation: SavedCalculation
}

export interface ListCalculationsResponse {
  calculations: SavedCalculation[]
}

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createCalculatorApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    /** Calculate leasing schedule. */
    calculate: <T = CalculateResponse>(body: CalculateRequest) =>
      request<T>('/api/v1/calculator/calculate', {
        method: 'POST',
        body,
      }),

    /** Send calculation result via email. */
    sendCalculationEmail: (body: SendCalculationEmailRequest) =>
      request<void>('/api/v1/calculator/send-calculation-email', {
        method: 'POST',
        body,
      }),

    /** Check support status for a list of vehicles. */
    getSupportStatus: (body: SupportStatusRequest) =>
      request<SupportStatusResponse>('/api/v1/calculator/support-status', {
        method: 'POST',
        body,
      }),

    /** List saved calculations for the current user. */
    listSavedCalculations: () =>
      request<ListCalculationsResponse>('/api/v1/client/calculations'),

    /** Save a new calculation. */
    saveCalculation: (body: SaveCalculationRequest) =>
      request<SaveCalculationResponse>('/api/v1/client/calculations', {
        method: 'POST',
        body,
      }),

    /** Delete a saved calculation by ID. */
    deleteCalculation: (id: UUID) =>
      request<void>(`/api/v1/client/calculations/${id}`, {
        method: 'DELETE',
      }),
  }
}
