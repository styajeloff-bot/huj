import type { ConditionRequest } from './types'
import { formatMoney, formatPercent } from './money'

export function formatRequestCommission(request: ConditionRequest): string {
  if (request.status === 'accepted' && request.counter_value !== null && request.counter_calc_type !== null) {
    return request.counter_calc_type === 'percent' ? formatPercent(request.counter_value) : formatMoney(request.counter_value)
  }
  return request.requested_calc_type === 'percent' ? formatPercent(request.requested_value) : formatMoney(request.requested_value)
}
