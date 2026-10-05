// =============================================================================
// Shared domain types for cart, calculator, and purchases features.
// =============================================================================

import type { CatalogId, UUID } from '~/types/ids'

// ---------------------------------------------------------------------------
// Cart
// ---------------------------------------------------------------------------

// Re-export CartItem from the cart store (single source of truth)
export type { CartItem } from '~/features/cart/store/cart'

/**
 * Loose variant of CartItem that accepts both mutable and DeepReadonly
 * versions (as returned by the cart store). Use in function signatures that
 * only *read* cart items.
 */
export interface CartItemLike {
  allow_overstock?: boolean
  cart_id: UUID
  vehicle_id: UUID
  modification_id?: CatalogId
  complectation_id?: CatalogId
  mark_name: string
  model_name: string
  base_price: number
  special_price?: number | null
  discount_price?: number | null
  has_support?: boolean
  support_type?: string | null
  support_params?: Record<string, unknown> | null
  custom_price?: number | null
  comment?: string
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
  id?: UUID
}

// ---------------------------------------------------------------------------
// Calculator
// ---------------------------------------------------------------------------

/** Result of a single leasing calculation (returned from backend for one vehicle or aggregate). */
export interface LeasingCalculationResult {
  monthlyPayment: number
  totalCost: number
  totalInterest?: number
  vatRefund?: number
  profitTaxSavings?: number
  totalSavings?: number
  buyoutAmount?: number
  rate?: number
  markup?: number
  markupPercent?: number
  monthlyPrincipalPayment?: number
  monthlyInterestPayment?: number
  annuityFactor?: number
  loanAmount?: number
  totalAmount?: number
}

/** Per-vehicle calculation row returned from backend. */
export interface PerVehicleCalculation {
  vehicle_id: UUID
  calculation: LeasingCalculationResult | null
  calculation_without_support?: LeasingCalculationResult | null
  support_breakdown?: SupportBreakdown | null
}

/** Eligible support programs row per vehicle. */
export interface EligibleSupportRow {
  vehicle_id: UUID
  program_ids: UUID[]
}

/** Support breakdown (for one vehicle or aggregate). */
export interface SupportBreakdown {
  vehicle_discount_support?: number
  dealer_commission_support?: number
  down_payment_support?: number
  interest_support?: number
  base_total?: number
  effective_total?: number
  contract_down_payment?: number
  effective_down_payment?: number
  client_down_payment?: number
  client_down_payment_percent?: number
}

/** Support amount per program. */
export interface SupportPerProgram {
  support_program_id: UUID
  type: string | null
  per_vehicle?: Array<{ vehicle_id: UUID; support_amount: number }>
}

/** Support program details. */
export interface SupportProgramDetail {
  id: UUID
  name: string | null
  starts_at: string | null
  ends_at: string | null
  bill_of_lading: unknown | null
}

/** Full calculation data emitted by CartLeasingCalculator. */
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
  calculations_per_vehicle: PerVehicleCalculation[]
  selected_support?: Record<UUID, UUID[]>
  support_per_vehicle?: unknown[]
  support_per_program: SupportPerProgram[]
  support_program_details: SupportProgramDetail[]
  eligible_support_program_ids_by_vehicle: EligibleSupportRow[]
}

/** Calculator params subset shared between components. */
export interface CalculatorParams {
  down_payment_percent: number
  lease_term_months: number
  buyout_percent: number
}

/** Vehicle-specific calculation data passed to CartItemCalculationModal. */
export interface VehicleCalculationData {
  calculation: LeasingCalculationResult | null
  calculation_without_support: LeasingCalculationResult | null
  support_breakdown: SupportBreakdown | null
  support_per_program: SupportPerProgram[]
  support_program_details: SupportProgramDetail[]
  eligible_program_ids: UUID[]
}

// ---------------------------------------------------------------------------
// Calculator (ClientCalculatorPanel)
// ---------------------------------------------------------------------------

/** Calculation result for the client calculator panel (snake_case from local compute). */
export interface ClientCalculation {
  lease_amount: number
  monthly_payment: number
  total_cost: number
  overpayment: number
  buyout_price: number
  vat_amount: number
  total_amount?: number
}

/** Payment schedule row for client calculator panel. */
export interface PaymentScheduleRow {
  month: number
  payment: number
  principal: number
  interest: number
  balance: number
}

/** Saved calculation item. */
export interface SavedCalculation {
  id: UUID
  name: string
  vehicle_price?: number
  monthly_payment?: number
  created_at?: string
  params: Record<string, unknown>
  calculation: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Calculator (CalculatorModal)
// ---------------------------------------------------------------------------

/** Result shape used by CalculatorModal. */
export interface CalculatorModalResult {
  monthlyPayment: number
  monthlyPrincipalPayment: number
  monthlyInterestPayment: number
  loanAmount: number
  totalAmount: number
  totalInterest: number
  rate: number
  buyoutAmount: number
  vatRefund: number
  profitTaxSavings: number
  totalSavings: number
  annuityFactor?: number
}

// ---------------------------------------------------------------------------
// Calculator (LeasingCalculator)
// ---------------------------------------------------------------------------

/** Tooltip info for savings tooltips. */
export interface TooltipInfo {
  title: string
  content: string
}

// ---------------------------------------------------------------------------
// Purchases
// ---------------------------------------------------------------------------

export interface PurchaseVehicleItem {
  vehicle_id: UUID
  cart_id?: UUID
  mark_name: string
  model_name: string
  base_price: number
  special_price?: number | null
  discount_price?: number | null
  custom_price?: number | null
  quantity: number
  images?: string[]
  is_model_order?: boolean
}

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------

export interface PaymentRecord {
  id: UUID
  purchase_order_id?: UUID
  payment_type: string
  amount: number
  status: string
  payment_method: string | null
  receipt_url: string | null
  fiscal_status: string | null
  fiscal_receipt_id?: string | null
  error_message: string | null
  paid_at: string | null
  created_at: string
}

export interface ScheduleItem {
  id: UUID
  purchase_order_id: UUID
  payment_number: number
  due_date: string
  amount: number
  principal: number | null
  interest: number | null
  is_paid: boolean
  payment_id: UUID | null
  payment_status: string | null
  payment_paid_at: string | null
  receipt_url: string | null
}

// ---------------------------------------------------------------------------
// Cart email data
// ---------------------------------------------------------------------------

export interface CartEmailItem {
  vehicleTitle: string
  quantity: number
  priceLine: string
  termMonths: number
  buyoutPct: number
  calcRows: Array<{ label: string; value: string }>
  supportRow: string | null
  details: Array<{ label: string; value: string }>
}

export interface CartEmailData {
  downPercent: number
  termMonths: number
  buyoutPct: number
  items: CartEmailItem[]
  totalAmount: number
  overallCalc: LeasingCalculationResult | null
  overallSupport: SupportBreakdown | null
}
