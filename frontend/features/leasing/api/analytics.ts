import { useApi } from '~/composables/useApi'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

const resolveRuntimeConfig = (): RuntimeConfig => (
  typeof useRuntimeConfig === 'function'
    ? useRuntimeConfig()
    : { public: { apiBase: '' } } as RuntimeConfig
)

// ============================================================================
// Filters & Request
// ============================================================================

export interface LkDashboardFilters {
  period_from?: string
  period_to?: string
  statuses?: string[]
  dealers?: string[]
  marks?: string[]
}

export type LkDashboardTab =
  | 'overview'
  | 'applications'
  | 'proposals'
  | 'financials'

export interface LkDashboardRequest {
  tab: LkDashboardTab
  filters: LkDashboardFilters
  limit?: number
  offset?: number
}

// ============================================================================
// Shared Widget Types
// ============================================================================

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

export interface PipelineStage {
  name: string
  count: number
  amount: number
  color: string
}

export interface HistogramBin {
  range: string
  count: number
  amount: number
}

// ============================================================================
// Tab-Specific Row Types
// ============================================================================

export interface ApplicationsTableRow {
  id: number
  number: string
  date: string
  client: string
  inn: string
  amount: number
  status: string
  status_color: string
  vehicle: string
  employee: string
}

export interface ProposalsTableRow {
  id: number
  date: string
  client: string
  leasing_company: string
  type: 'preliminary' | 'final'
  amount: number
  rate: number
  status: string
  status_color: string
}

export interface DocumentsTableRow {
  id: number
  date: string
  client: string
  document_type: string
  status: string
  status_color: string
  employee: string
}

export interface TeamTableRow {
  employee_id: string
  employee_name: string
  role: string
  applications_count: number
  approved_count: number
  rejected_count: number
  conversion_percent: number
  avg_processing_days: number
}

export interface FinancialsTableRow {
  id: number
  date: string
  client: string
  amount: number
  rate: number
  markup_percent: number
  monthly_payment: number
  total_revenue: number
}

export interface ExchangeTableRow {
  id: number
  date: string
  currency_pair: string
  rate: number
  change_percent: number
}

// ============================================================================
// Tab Response Types
// ============================================================================

export interface LkTabResponse {
  tab: LkDashboardTab
  filters_applied: LkDashboardFilters
  widgets: Record<string, unknown>
}

export interface LkOverviewResponse extends LkTabResponse {
  widgets: {
    'W-OVR-01'?: KpiWidget
    'W-OVR-02'?: KpiWidget
    'W-OVR-03'?: KpiWidget
    'W-OVR-04'?: KpiWidget
    'W-OVR-05'?: KpiWidget
    'W-OVR-06'?: KpiWidget
    'W-OVR-07'?: KpiWidget
    'W-OVR-08'?: KpiWidget
    'W-OVR-09'?: LineChartSeries[]
    'W-OVR-10'?: DonutSlice[]
    'W-OVR-11'?: BarChartData
    'W-OVR-12'?: BarChartData
    [key: string]: any
  }
}

export interface LkApplicationsResponse extends LkTabResponse {
  widgets: {
    'W-APP-01'?: KpiWidget
    'W-APP-02'?: KpiWidget
    'W-APP-03'?: KpiWidget
    'W-APP-04'?: KpiWidget
    'W-APP-05'?: LineChartSeries[]
    'W-APP-06'?: ApplicationsTableRow[]
    'W-APP-07'?: { total: number; page: number; limit: number; pages: number }
    [key: string]: any
  }
}

export interface LkProposalsResponse extends LkTabResponse {
  widgets: {
    'W-PRP-01'?: KpiWidget
    'W-PRP-02'?: KpiWidget
    'W-PRP-03'?: KpiWidget
    'W-PRP-04'?: KpiWidget
    'W-PRP-05'?: LineChartSeries[]
    'W-PRP-06'?: DonutSlice[]
    'W-PRP-07'?: ProposalsTableRow[]
    'W-PRP-08'?: { total: number; page: number; limit: number; pages: number }
    [key: string]: any
  }
}

export interface LkDocumentsResponse extends LkTabResponse {
  widgets: {
    'W-DOC-01'?: KpiWidget
    'W-DOC-02'?: KpiWidget
    'W-DOC-03'?: KpiWidget
    'W-DOC-04'?: KpiWidget
    'W-DOC-05'?: StackedBarChartData
    'W-DOC-06'?: DocumentsTableRow[]
    'W-DOC-07'?: { total: number; page: number; limit: number; pages: number }
    [key: string]: any
  }
}

export interface LkTeamResponse extends LkTabResponse {
  widgets: {
    'W-TEAM-01'?: BarChartData
    'W-TEAM-02'?: BarChartData
    'W-TEAM-03'?: BarChartData
    'W-TEAM-04'?: TeamTableRow[]
    'W-TEAM-05'?: { total: number; page: number; limit: number; pages: number }
    [key: string]: any
  }
}

export interface LkFinancialsResponse extends LkTabResponse {
  widgets: {
    'W-FIN-01'?: KpiWidget
    'W-FIN-02'?: KpiWidget
    'W-FIN-03'?: KpiWidget
    'W-FIN-04'?: KpiWidget
    'W-FIN-05'?: PipelineStage[]
    'W-FIN-06'?: LineChartSeries[]
    'W-FIN-07'?: LineChartSeries[]
    'W-FIN-08'?: HistogramBin[]
    'W-FIN-09'?: FinancialsTableRow[]
    'W-FIN-10'?: { total: number; page: number; limit: number; pages: number }
    [key: string]: any
  }
}

export interface LkExchangeResponse extends LkTabResponse {
  widgets: {
    'W-EXC-01'?: KpiWidget
    'W-EXC-02'?: KpiWidget
    'W-EXC-03'?: KpiWidget
    'W-EXC-04'?: KpiWidget
    'W-EXC-05'?: LineChartSeries[]
    'W-EXC-06'?: LineChartSeries[]
    'W-EXC-07'?: ExchangeTableRow[]
    'W-EXC-08'?: { total: number; page: number; limit: number; pages: number }
    [key: string]: any
  }
}

export type LkDashboardResponse =
  | LkOverviewResponse
  | LkApplicationsResponse
  | LkProposalsResponse
  | LkDocumentsResponse
  | LkTeamResponse
  | LkFinancialsResponse
  | LkExchangeResponse

// ============================================================================
// API Functions
// ============================================================================

export const createLeasingAnalyticsApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    fetchDashboard: <T extends LkDashboardResponse>(body: LkDashboardRequest) =>
      request<T>('/api/v1/analytics/lk-dashboard', { method: 'POST', body }),
  }
}

export async function fetchLkDashboard<T extends LkDashboardResponse>(
  body: LkDashboardRequest
): Promise<T> {
  return createLeasingAnalyticsApi(resolveRuntimeConfig()).fetchDashboard<T>(body)
}

export function useLkDashboard<T extends LkDashboardResponse>(options?: { immediate?: boolean }) {
  return useApi((body: LkDashboardRequest) => fetchLkDashboard<T>(body), options)
}

// ============================================================================
// Filter Options
// ============================================================================

export interface FilterOption {
  value: string
  label: string
}

export const STATUS_OPTIONS: FilterOption[] = [
  { value: 'submitted', label: 'Новая' },
  { value: 'under_review', label: 'На рассмотрении' },
  { value: 'under_review_with_docs', label: 'На рассмотрении с доп. документами' },
  { value: 'approved_scoring', label: 'Одобрено по скорингу' },
  { value: 'approved_scoring_another_cond', label: 'Одобрено по скорингу на других условиях' },
  { value: 'rejected_prescoring', label: 'Отказано на прескоринге' },
  { value: 'documents_required', label: 'Требуются документы' },
  { value: 'approved_final', label: 'Финально одобрено' },
  { value: 'approved_final_another_cond', label: 'Финально одобрено на других условиях' },
  { value: 'rejected_approved', label: 'Отказано после одобрения' },
  { value: 'selected_lc', label: 'Выбрана лизинговая компания' },
  { value: 'deal', label: 'Сделка' },
  { value: 'closed', label: 'Закрыто' },
]

// ============================================================================
// Helpers
// ============================================================================

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

export function getWidgetStackedBar(widgets: Record<string, unknown>, key: string): StackedBarChartData | undefined {
  const w = widgets[key]
  if (w && typeof w === 'object' && 'labels' in w && 'datasets' in w) {
    return w as StackedBarChartData
  }
  return undefined
}

export function getWidgetPipeline(widgets: Record<string, unknown>, key: string): PipelineStage[] {
  const w = widgets[key]
  if (Array.isArray(w)) return w as PipelineStage[]
  return []
}

export function getWidgetHistogram(widgets: Record<string, unknown>, key: string): HistogramBin[] {
  const w = widgets[key]
  if (Array.isArray(w)) return w as HistogramBin[]
  return []
}

export function getWidgetTable<T>(widgets: Record<string, unknown>, key: string): T[] {
  const w = widgets[key]
  if (Array.isArray(w)) return w as T[]
  return []
}

export function getWidgetPagination(widgets: Record<string, unknown>, key: string): { total: number; page: number; limit: number; pages: number } | undefined {
  const w = widgets[key]
  if (w && typeof w === 'object' && 'total' in w) {
    return w as { total: number; page: number; limit: number; pages: number }
  }
  return undefined
}
