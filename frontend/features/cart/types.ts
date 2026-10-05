import type { CatalogId, UUID } from '~/types/ids'
import type { SupportBadgeProgram } from '~/types/support'
import type {
  CalculatorParams,
  LeasingCalculationResult,
  SupportBreakdown,
  TooltipInfo,
} from '~/types/domains'

export type { CalculatorParams, LeasingCalculationResult, SupportBreakdown, TooltipInfo }

export interface CartItemLike {
  allow_overstock?: boolean
  cart_id: UUID
  id?: UUID
  vehicle_id: UUID
  modification_id?: CatalogId
  complectation_id?: CatalogId
  configuration_id?: CatalogId
  mark_id?: CatalogId
  model_id?: CatalogId
  mark_name: string
  model_name: string
  base_price: number
  special_price?: number | null
  discount_price?: number | null
  has_support?: boolean
  support_type?: string | null
  support_params?: Record<string, unknown> | null
  support_program_info?: {
    id?: UUID
    name?: string | null
    bill_of_lading?: unknown | null
  } | null
  applicable_support_programs?: readonly SupportBadgeProgram[]
  custom_price?: number | null
  comment?: string
  equipments?: readonly {
    equipment_code?: string
    service_code?: string
    price?: number | null
  }[]
  services?: readonly {
    equipment_code?: string
    service_code?: string
    price?: number | null
  }[]
  vin?: string | null
  is_model_order?: boolean
  is_selected: boolean
  added_at: string
  year?: number
  color?: string
  quantity: number
  images?: readonly string[]
  configuration_name?: string
  group_name?: string
  effective_price?: number
  price_from?: number
}

export interface CartPerVehicleCalculation {
  vehicle_id: UUID
  calculation: LeasingCalculationResult | null
  calculation_without_support?: LeasingCalculationResult | null
  support_breakdown?: SupportBreakdown | null
}

export interface CartEligibleSupportRow {
  vehicle_id: UUID
  program_ids: UUID[]
}

export interface CartSupportPerProgram {
  support_program_id: UUID
  type: string | null
  per_vehicle?: Array<{ vehicle_id: UUID; support_amount: number }>
}

export type CartSupportProgramDetail = SupportBadgeProgram

export interface CartCalculationData {
  total_amount: number
  additional_amount?: number
  down_payment: number
  down_payment_percent: number
  lease_term_months: number
  buyout_amount: number
  buyout_percent?: number
  vehicle_ids: UUID[]
  vehicle_price_overrides?: Record<UUID, number>
  vehicle_quantities?: Record<UUID, number>
  calculation: LeasingCalculationResult | null
  support: SupportBreakdown | null
  calculations_per_vehicle: CartPerVehicleCalculation[]
  selected_support?: Record<UUID, UUID[]>
  support_per_vehicle?: unknown[]
  support_per_program: CartSupportPerProgram[]
  support_program_details: CartSupportProgramDetail[]
  eligible_support_program_ids_by_vehicle: CartEligibleSupportRow[]
}

export interface CartCalculatorResponse {
  calculation?: LeasingCalculationResult | null
  calculation_without_support?: { calculation?: LeasingCalculationResult | null }
  support?: SupportBreakdown | null
  calculations_per_vehicle?: CartPerVehicleCalculation[]
  support_per_vehicle?: unknown[]
  support_per_program?: CartSupportPerProgram[]
  support_program_details?: CartSupportProgramDetail[]
  eligible_support_program_ids_by_vehicle?: CartEligibleSupportRow[]
}

export interface VehicleCalculationData {
  calculation: LeasingCalculationResult | null
  calculation_without_support: LeasingCalculationResult | null
  support_breakdown: SupportBreakdown | null
  support_per_program: CartSupportPerProgram[]
  support_program_details: CartSupportProgramDetail[]
  eligible_program_ids: UUID[]
}
