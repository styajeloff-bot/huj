import type { UUID } from '~/types/ids'
import { createLatestCalculationRequest } from '../latestCalculationRequest'

export const useLeasingCalculator = () => {
  const config = useRuntimeConfig()
  const loading = ref(false)
  const error = ref<string | null>(null)
  const calculation = ref<any>(null)
  const specialOffer = ref<any>(null)
  const support = ref<any>(null)
  const latestRequest = createLatestCalculationRequest()

  const calculate = async (params: {
    total_amount: number
    additional_amount?: number
    down_payment: number
    down_payment_percent: number
    lease_term_months: number
    buyout_amount?: number
    vehicle_ids?: UUID[]
    vehicle_price_overrides?: Record<UUID, number>
    vehicle_quantities?: Record<UUID, number>
    selected_support_ids?: UUID[] // legacy global list
    selected_support?: Record<UUID, UUID[]> // per-vehicle selection
  }) => {
    loading.value = true
    error.value = null
    calculation.value = null
    specialOffer.value = null
    support.value = null

    const result = await latestRequest.run(() => $fetch<any>('/api/v1/calculator/calculate', {
      method: 'POST',
      body: params,
      baseURL: config.public.apiBase,
      credentials: 'include'
    }))

    if (result.status === 'stale') return null

    loading.value = false
    if (result.status === 'error') {
      const failure = result.error as { data?: { error?: string } }
      error.value = failure.data?.error || 'Ошибка при расчете'
      throw result.error
    }

    calculation.value = result.value.calculation
    support.value = result.value.support ?? null
    return result.value
  }

  const reset = () => {
    latestRequest.invalidate()
    loading.value = false
    calculation.value = null
    specialOffer.value = null
    support.value = null
    error.value = null
  }

  return {
    loading,
    error,
    calculation,
    specialOffer,
    support,
    calculate,
    reset
  }
}
