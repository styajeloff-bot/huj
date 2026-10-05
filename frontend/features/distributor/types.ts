import type { UUID } from '~/types/ids'

// ── Dealers ──────────────────────────────────────────────────────────
// Real backend contract: GET /api/v1/distributor/dealers returns dealer
// *companies* with only these fields (see
// fastapi/application/queries/distributor/list_distributor_dealers.py).
export interface Dealer {
  id: UUID
  name: string | null
  company_type: string
}

// ── Pagination ──────────────────────────────────────────────────────
export interface Pagination {
  page: number
  limit: number
  total: number
  pages: number
}

// ── Reports ─────────────────────────────────────────────────────────
export interface Report {
  id: UUID
  name: string
  type: string
  status: string
  created_at: string
  updated_at?: string
  file_size: number
  file_name?: string
  mime_type?: string
  progress?: number
}

export type ReportType = 'inventory' | 'sales' | 'financial' | 'analytics' | 'daily'
export type ReportStatus = 'pending' | 'generating' | 'completed' | 'failed'

// ── Analytics ───────────────────────────────────────────────────────
export interface AnalyticsVehicle {
  id: UUID
  image: string | null
  name: string
  year: number | string
  avgDays?: number
  soldCount?: number
  daysOnStock?: number
}

export interface PricingSegment {
  name: string
  percentage: number
  count: number
}

export interface ChartData {
  labels: string[]
  values: number[]
}

export interface Recommendation {
  id: UUID
  text: string
}

export interface AnalyticsData {
  turnoverRate: number
  averageSaleDays: number
  efficiency: number
  roi: number
  fastSelling: AnalyticsVehicle[]
  slowSelling: AnalyticsVehicle[]
  pricing: {
    averagePrice: number
    averageDiscount: number
    discountedPercent: number
    segments: PricingSegment[]
  }
  forecast: {
    expectedSales: number
    expectedRevenue: number
    confidence: number
  }
  recommendations: Recommendation[]
  market: {
    position: number
    advantage: number
    marketShare: number
  }
  salesData?: ChartData
  brandData?: ChartData
  seasonalData?: ChartData
}

// ── Model Orders / Applications ─────────────────────────────────────
export interface SupportInfo {
  base_total?: number | null
  vehicle_discount_support?: number
  dealer_commission_support?: number
  down_payment_support?: number
  interest_support?: number
  effective_total?: number | null
  effective_down_payment?: number | null
}

export interface Application {
  id: UUID
  display_number?: string | null
  applicant_name: string
  company: string
  status: string
  vehicles_count: number
  pending_count: number
  assigned_count: number
  support: SupportInfo | null
  total_amount: number
  created_at: string
  updated_at?: string | null
}

export interface ApplicationVehicle {
  fulfillment_version?: number
  allocated_vehicle_ids?: UUID[]
  allocated_vins?: Array<string | null>
  id: UUID
  catalog_url: string
  mark_name: string
  model_name: string
  generation_name: string
  configuration_name: string
  color: string | null
  year: number | string | null
  is_model_order: boolean
  vin: string | null
  unit_price: number
  base_price?: number
  special_price?: number | null
  discount_price?: number
  leasing_purpose?: string | null
  leasing_purposes?: string[] | null
  leasing_purpose_comment?: string | null
  region?: string | null
  regions?: string[] | null
}

export interface ModelOrderStats {
  pending_orders: number
  assigned_orders: number
}

// ── Warehouse ───────────────────────────────────────────────────────
export interface WarehouseVehicle {
  id: UUID
  vin?: string
  [key: string]: unknown
}

export interface WarehouseStats {
  [key: string]: unknown
}

// ── Profile ─────────────────────────────────────────────────────────
export interface DistributorDocument {
  id: UUID
  file_name: string
  mime_type: string
  status: string
  [key: string]: unknown
}

export interface DistributorProfile {
  company_name: string
  inn: string
  kpp: string
  ogrn: string
  legal_address: string
  actual_address: string
  phone: string
  email: string
  website: string
  fax: string
  bank_account: string
  bik: string
  bank_name: string
  logo: string | null
  notifications: {
    email: boolean
    sms: boolean
    push: boolean
  }
  created_at: string | null
  last_activity: string | null
  stats: {
    total_dealers: number
    total_vehicles: number
    monthly_sales: number
    monthly_revenue: number
  }
  verification: {
    documents: boolean
    bank: boolean
    contacts: boolean
    status: string
  }
  documents: DistributorDocument[]
}

// ── Application Modal ───────────────────────────────────────────────
export interface ApplicationDetail {
  id: UUID
  status: string
  created_at: string
  vehicle_count: number
  total_amount: number
  lease_term: number
  company_name: string
  user_email: string
  inn?: string
  phone?: string
  leasing_company_name?: string
  approval_conditions?: string
  rejection_reason?: string
  vehicles?: ApplicationModalVehicle[]
  down_payment_percent?: number
  monthly_payment?: number
  support?: SupportInfo | null
  comments?: string
  reviewer_comments?: string
  status_updated_at?: string
}

export interface ApplicationModalVehicle {
  id: UUID
  image_url?: string
  name: string
  price: number
  year?: number | string
  engine?: string
  transmission?: string
}

// ── Status maps ─────────────────────────────────────────────────────
export type DealerStatus = 'active' | 'inactive' | 'pending' | 'blocked'
export type VerificationStatus = 'verified' | 'pending' | 'rejected'
export type DocumentStatus = 'approved' | 'pending' | 'rejected'
export type OrderStatus = 'active' | 'rejected' | 'issued'

export type ReportTypeKey = 'inventory' | 'sales' | 'financial' | 'analytics'
export type ReportTypeKeyExtended = ReportTypeKey | 'daily'
