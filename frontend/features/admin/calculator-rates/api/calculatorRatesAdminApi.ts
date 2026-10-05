type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export interface CalculatorRate {
  id: string
  date_from: string
  date_to: string | null
  key_rate: number
  surcharge: number
  vat_rate: number
  profit_tax_rate: number
}

export interface CalculatorRatePayload {
  date_from: string
  date_to: string | null
  key_rate: number
  surcharge: number
  vat_rate: number
  profit_tax_rate: number
}

export type CalculatorRatePatchPayload = Partial<CalculatorRatePayload>

export const createCalculatorRatesAdminApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  return {
    listRates: () =>
      request<{ items: CalculatorRate[] }>('/api/v1/admin/calculator-rates'),
    createRate: (body: CalculatorRatePayload) =>
      request<{ calculator_rate: CalculatorRate }>('/api/v1/admin/calculator-rates', {
        method: 'POST',
        body
      }),
    updateRate: (id: string, body: CalculatorRatePatchPayload) =>
      request<{ calculator_rate: CalculatorRate }>(`/api/v1/admin/calculator-rates/${id}`, {
        method: 'PATCH',
        body
      })
  }
}
