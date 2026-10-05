// =============================================================================
// Distributor Analytics — Types & Helpers
// =============================================================================

import type { WarehouseAnalyticsBody } from './distributorApi'
import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

const resolveRuntimeConfig = (): RuntimeConfig => (
  typeof useRuntimeConfig === 'function'
    ? useRuntimeConfig()
    : { public: { apiBase: '' } } as RuntimeConfig
)

export type DistributorDashboardTab =
  | 'warehouse'
  | 'applications'
  | 'exchange'
  | 'financials'
  | 'sales-dc'
  | 'sales-dc-regions'
  | 'team'

export interface DistributorDashboardFilters {
  period_from?: string
  period_to?: string
  prev_period_from?: string
  prev_period_to?: string
  month?: string
  page?: number
  limit?: number
  statuses?: string[]
  cities?: string[]
  marks?: string[]
  models?: string[]
  dealers?: UUID[]
  dealer_groups?: string[]
  leasing_companies?: string[]
  show_deals?: boolean
}

// ---------------------------------------------------------------------------
// Shared Widget Types (re-exported from leasing for convenience)
// ---------------------------------------------------------------------------

export interface KpiWidget {
  value: number
  delta?: number
  delta_percent?: number
  period_comparison?: string
}

export interface TimeSeriesPoint {
  x: string
  y: number
}

export interface LineChartSeries {
  name: string
  color: string
  data: TimeSeriesPoint[]
  dashed?: boolean
}

export interface DonutSlice {
  code?: string
  label: string
  value: number
  color: string
}

export interface BarSeries {
  name: string
  color: string
  data: number[]
}

export interface BarChartData {
  labels: string[]
  datasets: BarSeries[]
}

export interface StackedBarDataset {
  label: string
  data: number[]
  backgroundColor: string
}

export interface StackedBarChartData {
  labels: string[]
  datasets: StackedBarDataset[]
}

// ---------------------------------------------------------------------------
// Tab Response Types
// ---------------------------------------------------------------------------

export interface WarehouseTabResponse {
  tab: 'warehouse'
  filters_applied: DistributorDashboardFilters
  widgets: {
    'W-WHS-01'?: KpiWidget // Всего авто
    'W-WHS-02'?: KpiWidget // В наличии
    'W-WHS-03'?: KpiWidget // В резерве
    'W-WHS-04'?: KpiWidget // Продано
    'W-WHS-05'?: KpiWidget // Общая стоимость
    'W-WHS-06'?: KpiWidget // Дилеры
    'W-WHS-07'?: KpiWidget // Средняя стоимость
    'W-WHS-08'?: DonutSlice[] // Распределение по статусам
    'W-WHS-09'?: BarChartData // По маркам и моделям (ТОП-10)
    'W-WHS-10'?: BarChartData // Динамика по месяцам
    'W-WHS-11'?: { items: WarehouseDealerRow[]; pagination: Pagination }
    'W-WHS-12'?: { items: WarehouseCityRow[]; pagination: Pagination }
  }
}

export interface WarehouseDealerRow {
  dealer_name: string
  count: number
  value: number
}

export interface WarehouseCityRow {
  city: string
  count: number
}

export interface ApplicationsTabResponse {
  tab: 'applications'
  filters_applied: DistributorDashboardFilters
  widgets: {
    'W-APP-01'?: KpiWidget // Всего
    'W-APP-02'?: KpiWidget // Активные
    'W-APP-03'?: KpiWidget // Отклонённые
    'W-APP-04'?: KpiWidget // Выданные
    'W-APP-05'?: KpiWidget // Срок сделки (дн.)
    'W-APP-06'?: ComboChartData // Заявки текущий vs предыдущий
    'W-APP-07'?: ComboChartData // Сделки текущий vs предыдущий
    'W-APP-08'?: { items: ApplicationsTableRow[]; pagination: Pagination }
    'W-APP-09'?: KpiWidget // Сделки (issued)
    'W-APP-10'?: ApplicationsStatusStatRow[] // Детальная статистика по статусам
  }
}

export interface ApplicationsStatusStatRow {
  status: string
  status_label: string
  count: number
}

export type ApplicationStatusFunnelSelectionMode =
  | 'created_in_period'
  | 'active_during_period'

export interface ApplicationStatusFunnelFilters {
  periodFrom: string
  periodTo: string
  selectionMode: ApplicationStatusFunnelSelectionMode
}

export interface ApplicationStatusFunnelRow {
  status: string
  label: string
  order: number
  eventsCount: number
  endStateCount: number
}

export interface ApplicationStatusFunnelResponse {
  unit: 'lca'
  timezone: 'Europe/Moscow'
  periodFrom: string
  periodTo: string
  selectionMode: ApplicationStatusFunnelSelectionMode
  historyAvailableFrom: string
  selectedCount: number
  rows: ApplicationStatusFunnelRow[]
}

export interface ComboChartData {
  labels: string[]
  barDatasets: BarSeries[]
  lineDataset?: LineChartSeries
}

export type StatusBucket = 'active' | 'rejected' | 'issued'

export interface ApplicationsTableRow {
  display_number: string
  created_at: string
  approved_at?: string
  deal_duration_days?: number | null
  leasing_company: string
  dealer_name: string
  mark: string
  model: string
  total_amount: number
  status: string
  status_label: string
  status_bucket: StatusBucket
}

export interface FinancialsTabResponse {
  tab: 'financials'
  filters_applied: DistributorDashboardFilters
  widgets: {
    'W-FIN-01'?: KpiWidget // В работе (₽)
    'W-FIN-01a'?: KpiWidget // ТС в работе (шт)
    'W-FIN-02'?: KpiWidget // Одобрено (₽)
    'W-FIN-02a'?: KpiWidget // Одобрено ТС (шт)
    'W-FIN-03'?: KpiWidget // Выдано (₽)
    'W-FIN-03a'?: KpiWidget // Выдано ТС (шт)
    'W-FIN-04'?: KpiWidget // Ср. ставка
    'W-FIN-05'?: KpiWidget // Ср. срок
    'W-FIN-06'?: KpiWidget // Ср. аванс %
    'W-FIN-07'?: LineChartSeries[] // Динамика объемов
    'W-FIN-08'?: { items: FinancialsTableRow[]; pagination: Pagination }
  }
}

export interface FinancialsTableRow {
  display_number: string
  status: string
  total_amount: number
  down_payment: number
  down_payment_percent: number
  lease_term_months: number
  monthly_payment: number
  rate: number
  total_cost: number
}

export interface ExchangeTabResponse {
  tab: 'exchange'
  filters_applied: DistributorDashboardFilters
  widgets: {
    'W-EXC-01'?: KpiWidget
    'W-EXC-02'?: KpiWidget
    'W-EXC-03'?: KpiWidget
    'W-EXC-04'?: KpiWidget
    'W-EXC-05'?: KpiWidget
    'W-EXC-06'?: LineChartSeries[]
    'W-EXC-07'?: { items: ExchangeTableRow[]; pagination: Pagination }
  }
}

export interface ExchangeTableRow {
  status: string
  status_label: string
  mark: string
  model: string
  quantity: number
  discount_type: string
  discount_type_label: string
  discount_value: number
  bids_count: number
  accepted_bids: number
  average_price: number
  created_at: string
}

export interface SalesDcTabResponse {
  tab: 'sales-dc'
  filters_applied: DistributorDashboardFilters
  widgets: {
    'W-SDC-01'?: { items: SalesDcApplicationsRow[]; pagination: Pagination }
    'W-SDC-02'?: { items: SalesDcSalesRow[]; pagination: Pagination }
  }
}

export interface SalesDcApplicationsRow {
  month: string
  dealer_name: string
  new_applications: number
  new_clients: number
  approved_applications: number
  approved_clients: number
  financed_applications: number
  financed_clients: number
  approval_rate: number
  financing_rate: number
}

export interface SalesDcSalesRow {
  month: string
  dealer_name: string
  avg_vehicle_cost: number
  avg_contract_amount: number
  avg_down_payment_percent: number
  avg_down_payment_amount: number
  avg_lease_term: number
  avg_rate: number
  accessories_total: number
  accessories_percent: number
}

export interface SalesDcRegionsTabResponse {
  tab: 'sales-dc-regions'
  filters_applied: DistributorDashboardFilters
  widgets: {
    'W-SDR-01'?: { items: SalesByMarkRow[]; columns: string[] }
    'W-SDR-02'?: { items: SalesByCityRow[]; columns: string[] }
  }
}

export interface SalesByMarkRow {
  month: string
  mark: string
  model: string
  [city: string]: string | number
}

export interface SalesByCityRow {
  month: string
  city: string
  [mark_model: string]: string | number
}

export interface TeamTabResponse {
  tab: 'team'
  filters_applied: DistributorDashboardFilters
  widgets: {
    'W-TEA-01'?: KpiWidget
    'W-TEA-02'?: KpiWidget
    'W-TEA-03'?: KpiWidget
    'W-TEA-04'?: KpiWidget
    'W-TEA-05'?: { items: TeamDealerRow[]; pagination: Pagination }
    'W-TEA-06'?: { items: TeamReviewerRow[]; pagination: Pagination }
  }
}

export interface TeamDealerRow {
  employee_id: UUID
  employee_name: string
  applications_count: number
  approved_count: number
  rejected_count: number
}

export interface TeamReviewerRow {
  employee_id: UUID
  employee_name: string
  documents_count: number
  approved_count: number
  rejected_count: number
}

export interface Pagination {
  page: number
  limit: number
  total: number
  pages: number
}

export type DistributorDashboardResponse =
  | WarehouseTabResponse
  | ApplicationsTabResponse
  | FinancialsTabResponse
  | ExchangeTabResponse
  | SalesDcTabResponse
  | SalesDcRegionsTabResponse
  | TeamTabResponse

// ---------------------------------------------------------------------------
// API fetch
// ---------------------------------------------------------------------------

const buildDistributorAnalyticsUrl = (
  tab: DistributorDashboardTab,
  filters: DistributorDashboardFilters,
) => {
  const params = new URLSearchParams()
  const appendArray = (key: string, values?: string[]) => {
    for (const value of values || []) {
      params.append(key, value)
    }
  }

  if (filters.period_from) params.set('period_from', filters.period_from)
  if (filters.period_to) params.set('period_to', filters.period_to)
  if (filters.prev_period_from) params.set('prev_period_from', filters.prev_period_from)
  if (filters.prev_period_to) params.set('prev_period_to', filters.prev_period_to)
  if (filters.month) params.set('month', filters.month)
  if (filters.page) params.set('page', String(filters.page))
  if (filters.limit) params.set('limit', String(filters.limit))
  appendArray('statuses', filters.statuses)
  appendArray('cities', filters.cities)
  appendArray('marks', filters.marks)
  appendArray('models', filters.models)
  appendArray('dealers', filters.dealers)
  appendArray('dealer_groups', filters.dealer_groups)
  appendArray('leasing_companies', filters.leasing_companies)
  if (filters.show_deals !== undefined) params.set('show_deals', String(filters.show_deals))

  const queryString = params.toString()
  return `/api/v1/distributor/analytics/${tab}${queryString ? '?' + queryString : ''}`
}

export const buildApplicationStatusFunnelUrl = (
  filters: ApplicationStatusFunnelFilters,
) => {
  const params = new URLSearchParams({
    period_from: filters.periodFrom,
    period_to: filters.periodTo,
    selection_mode: filters.selectionMode,
  })

  return `/api/v1/analytics/applications/funnel?${params.toString()}`
}

export const createDistributorAnalyticsApi = (config: RuntimeConfig) => ({
  fetchDashboard: (
    tab: DistributorDashboardTab,
    filters: DistributorDashboardFilters,
  ) =>
    $fetch<DistributorDashboardResponse>(buildDistributorAnalyticsUrl(tab, filters), {
      baseURL: config.public.apiBase,
      method: 'GET',
      credentials: 'include',
    }),
  fetchApplicationStatusFunnel: (
    filters: ApplicationStatusFunnelFilters,
    signal?: AbortSignal,
  ) =>
    $fetch<ApplicationStatusFunnelResponse>(buildApplicationStatusFunnelUrl(filters), {
      baseURL: config.public.apiBase,
      method: 'GET',
      credentials: 'include',
      signal,
    }),
})

/**
 * Fetch distributor analytics from the real backend API.
 *
 * On HTTP 200 returns the parsed `DistributorDashboardResponse` (the
 * `widgets` object may be empty — the caller is responsible for rendering an
 * empty state in that case). On any failure (503, network error, malformed
 * response) the underlying `$fetch` error is rethrown so the caller can show
 * an error state.
 */
export async function fetchDistributorAnalytics(
  tab: DistributorDashboardTab,
  filters: DistributorDashboardFilters,
): Promise<DistributorDashboardResponse> {
  return createDistributorAnalyticsApi(resolveRuntimeConfig()).fetchDashboard(tab, filters)
}

export async function fetchApplicationStatusFunnel(
  filters: ApplicationStatusFunnelFilters,
  signal?: AbortSignal,
): Promise<ApplicationStatusFunnelResponse> {
  return createDistributorAnalyticsApi(resolveRuntimeConfig())
    .fetchApplicationStatusFunnel(filters, signal)
}

function toUnknownRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object'
    ? value as Record<string, unknown>
    : null
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

export function getDistributorAnalyticsErrorMessage(error: unknown): string {
  const root = toUnknownRecord(error)
  const data = toUnknownRecord(root?.data) ?? root
  const detail = data?.detail
  const detailRecord = toUnknownRecord(detail)

  return nonEmptyString(detail)
    ?? nonEmptyString(detailRecord?.message)
    ?? nonEmptyString(detailRecord?.error)
    ?? nonEmptyString(data?.message)
    ?? nonEmptyString(data?.error)
    ?? nonEmptyString(root?.message)
    ?? 'Попробуйте обновить страницу позже.'
}

// ---------------------------------------------------------------------------
// Empty-check helpers
// ---------------------------------------------------------------------------

export function isEmptyOverviewData(data: any): boolean {
  if (!data) return true
  const byStatus = data.by_status || {}
  const total = Object.values(byStatus).reduce(
    (sum: number, v: any) => sum + (Number(v) || 0),
    0,
  )
  return (
    total === 0 &&
    (data.by_mark || []).length === 0 &&
    (data.timeline || []).length === 0
  )
}

export function isEmptyWarehouseData(
  data: WarehouseAnalyticsBody | null | undefined,
): boolean {
  if (!data) return true
  return (
    (data.total_vehicles || 0) === 0 &&
    (data.total_value || 0) === 0 &&
    (data.total_dealers || 0) === 0 &&
    (data.by_status || []).length === 0 &&
    (data.by_mark || []).length === 0 &&
    (data.by_dealer || []).length === 0 &&
    (data.by_city || []).length === 0 &&
    (data.timeline || []).length === 0
  )
}

// ---------------------------------------------------------------------------
// Widget helpers
// ---------------------------------------------------------------------------

export function getWidgetKpi(widgets: Record<string, unknown>, key: string): KpiWidget | undefined {
  const w = widgets[key]
  if (w && typeof w === 'object' && 'value' in w) {
    return w as KpiWidget
  }
  return undefined
}

export function getWidgetLineSeries(widgets: Record<string, unknown>, key: string): LineChartSeries[] {
  const w = widgets[key]
  if (Array.isArray(w) && w.length > 0 && 'data' in (w[0] as any)) {
    return w as LineChartSeries[]
  }
  return []
}

export function getWidgetDonut(widgets: Record<string, unknown>, key: string): DonutSlice[] {
  const w = widgets[key]
  if (Array.isArray(w) && w.length > 0 && 'color' in (w[0] as any)) {
    return w as DonutSlice[]
  }
  return []
}

export function getWidgetBarChart(widgets: Record<string, unknown>, key: string): BarChartData | undefined {
  const w = widgets[key]
  if (w && typeof w === 'object' && 'labels' in w && 'datasets' in w) {
    return w as BarChartData
  }
  return undefined
}

export function getWidgetTable<T>(widgets: Record<string, unknown>, key: string): T[] {
  const w = widgets[key]
  if (w && typeof w === 'object' && 'items' in w) {
    return (w as any).items as T[]
  }
  return []
}

export function getWidgetPagination(widgets: Record<string, unknown>, key: string): Pagination | undefined {
  const w = widgets[key]
  if (w && typeof w === 'object' && 'pagination' in w) {
    return (w as { pagination?: Pagination }).pagination
  }
  if (w && typeof w === 'object' && 'total' in w) {
    return w as Pagination
  }
  return undefined
}
