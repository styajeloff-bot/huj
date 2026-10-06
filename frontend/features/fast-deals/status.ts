import type { FastDealSource, FastDealStatus, LcApplicationStatus } from './types'

/**
 * Presentation of the fast deal dictionaries. The statuses are their own dictionary and are
 * never mixed with the statuses of ordinary applications.
 */

export const FAST_DEAL_STATUS_LABELS: Record<FastDealStatus, string> = {
  draft: 'Черновик',
  pending_lc_confirmation: 'Ожидает КП лизинговых компаний',
  pending_lc_final_confirmation: 'Ожидает финального подтверждения ЛК',
  pending_dealer_confirmation: 'Ожидает подтверждения дилера',
  pending_lc_changes_confirmation: 'Ожидает решения ЛК по изменениям',
  confirmed: 'Подтверждена',
  rejected: 'Отклонена',
  cancelled: 'Отменена',
}

const FAST_DEAL_STATUS_CLASSES: Record<FastDealStatus, string> = {
  draft: 'bg-gray-100 text-gray-800',
  pending_lc_confirmation: 'bg-amber-100 text-amber-800',
  pending_lc_final_confirmation: 'bg-purple-100 text-purple-800',
  pending_dealer_confirmation: 'bg-blue-100 text-blue-800',
  pending_lc_changes_confirmation: 'bg-orange-100 text-orange-800',
  confirmed: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  cancelled: 'bg-gray-200 text-gray-700',
}

const NEUTRAL_CLASS = 'bg-gray-100 text-gray-800'

/** Statuses in the order of the process; used by the list filter. */
export const FAST_DEAL_STATUS_OPTIONS: ReadonlyArray<{ value: FastDealStatus; label: string }> = (
  Object.keys(FAST_DEAL_STATUS_LABELS) as FastDealStatus[]
).map(value => ({ value, label: FAST_DEAL_STATUS_LABELS[value] }))

/** `confirmed` and `cancelled` are final: the deal is read-only and cannot be reopened. */
export const FAST_DEAL_FINAL_STATUSES: ReadonlySet<string> = new Set(['confirmed', 'cancelled'])

export const isFastDealStatus = (value: unknown): value is FastDealStatus =>
  typeof value === 'string' && Object.prototype.hasOwnProperty.call(FAST_DEAL_STATUS_LABELS, value)

export const isFastDealFinalStatus = (status: string | null | undefined): boolean =>
  Boolean(status && FAST_DEAL_FINAL_STATUSES.has(status))

/** An unknown status of a newer server is shown as is instead of hiding the deal. */
export const fastDealStatusLabel = (status: string | null | undefined): string => {
  if (!status) return '—'
  return isFastDealStatus(status) ? FAST_DEAL_STATUS_LABELS[status] : status
}

export const fastDealStatusClass = (status: string | null | undefined): string =>
  isFastDealStatus(status) ? FAST_DEAL_STATUS_CLASSES[status] : NEUTRAL_CLASS

// ----------------------------------------------------------------------------- invitations

export const LC_APPLICATION_STATUS_LABELS: Record<LcApplicationStatus, string> = {
  pending_review: 'Ожидает КП',
  offer_sent: 'КП отправлено',
  selected_by_dealer: 'Выбрана дилером',
  confirmed: 'Подтверждено',
  rejected: 'Отказ',
  closed_not_selected: 'Не выбрана',
}

const LC_APPLICATION_STATUS_CLASSES: Record<LcApplicationStatus, string> = {
  pending_review: 'bg-amber-100 text-amber-800',
  offer_sent: 'bg-blue-100 text-blue-800',
  selected_by_dealer: 'bg-purple-100 text-purple-800',
  confirmed: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  closed_not_selected: 'bg-gray-100 text-gray-700',
}

const isLcApplicationStatus = (value: unknown): value is LcApplicationStatus =>
  typeof value === 'string' && Object.prototype.hasOwnProperty.call(LC_APPLICATION_STATUS_LABELS, value)

export const lcApplicationStatusLabel = (status: string | null | undefined): string => {
  if (!status) return '—'
  return isLcApplicationStatus(status) ? LC_APPLICATION_STATUS_LABELS[status] : status
}

export const lcApplicationStatusClass = (status: string | null | undefined): string =>
  isLcApplicationStatus(status) ? LC_APPLICATION_STATUS_CLASSES[status] : NEUTRAL_CLASS

// ------------------------------------------------------------------------------ direction

export const FAST_DEAL_DIRECTION_LABELS: Record<FastDealSource, string> = {
  dealer_to_leasing: 'От дилера к ЛК',
  leasing_to_dealer: 'От ЛК к дилеру',
}

export const FAST_DEAL_DIRECTION_OPTIONS: ReadonlyArray<{ value: FastDealSource; label: string }> = (
  Object.keys(FAST_DEAL_DIRECTION_LABELS) as FastDealSource[]
).map(value => ({ value, label: FAST_DEAL_DIRECTION_LABELS[value] }))

export const isFastDealSource = (value: unknown): value is FastDealSource =>
  value === 'dealer_to_leasing' || value === 'leasing_to_dealer'

export const fastDealDirectionLabel = (source: string | null | undefined): string =>
  isFastDealSource(source) ? FAST_DEAL_DIRECTION_LABELS[source] : (source || '—')

/** Russian plural form for 1 / 2-4 / 5+ (with the 11-14 exception). */
export const pluralRu = (count: number, one: string, few: string, many: string): string => {
  const abs = Math.abs(count)
  const lastTwo = abs % 100
  const last = abs % 10
  if (lastTwo >= 11 && lastTwo <= 14) return many
  if (last === 1) return one
  if (last >= 2 && last <= 4) return few
  return many
}

/** «в 3 лизинговые компании» — shown for a DD that has been sent but has no chosen LC yet. */
export const invitedLeasingCompaniesLabel = (count: number): string =>
  `в ${count} ${pluralRu(count, 'лизинговую компанию', 'лизинговые компании', 'лизинговых компаний')}`
