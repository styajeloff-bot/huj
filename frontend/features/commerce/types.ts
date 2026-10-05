import type { RouteLocationRaw } from 'vue-router'
import type { UUID } from '~/types/ids'
import type { SupportBadgeProgram } from '~/types/support'

export type CommerceItemType = 'vehicle' | 'special_equipment'
export type CommerceMoney = string
export type CommerceCheckoutIntent = 'leasing' | 'full_purchase' | 'reservation' | 'preorder'
export type CommercePurchaseType = Exclude<CommerceCheckoutIntent, 'leasing'>
export type CommercePaymentMethod = 'card' | 'sbp' | 'bank_transfer'

export interface CommerceItemRef {
  type: CommerceItemType
  id: UUID
}

export interface CommercePurchaseSelection {
  item: CommerceItemRef
  quantity: number
  cart_item_ids?: UUID[]
  group_items?: Array<{
    item: CommerceItemRef
    quantity: number
    price: CommerceMoney | null
  }>
}

export interface CommerceCompanyPayload {
  id?: UUID
  name: string
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  actual_address?: string | null
  manager_name?: string | null
  entity_type?: string | null
  phone?: string | null
  email?: string | null
  [key: string]: unknown
}

export interface CommerceCapabilities {
  can_lease: boolean
  can_buy: boolean
  can_preorder: boolean
}

export interface CommerceFact {
  label: string
  value: string
}

export interface CommerceItem {
  ref: CommerceItemRef
  title: string
  subtitle: string | null
  image_url: string | null
  detail_url: string | null
  price: CommerceMoney | null
  price_on_request?: boolean
  price_from?: CommerceMoney | null
  currency_code: string
  availability: string
  manufacturer: string | null
  model: string | null
  modification: string | null
  year: number | null
  facts: CommerceFact[]
  capabilities: CommerceCapabilities
}

export interface CommercePurchaseLine {
  item: CommerceItem
  quantity: number
}

export interface CommerceCheckoutLine {
  item: CommerceItem
  quantity: number
  allow_overstock?: boolean
  custom_price: CommerceMoney | null
  comment: string
  equipments: Array<{
    equipment_code?: string
    service_code?: string
    price?: number | null
  }>
  services: Array<{
    equipment_code?: string
    service_code?: string
    price?: number | null
  }>
  leasing_purpose: string | null
  leasing_purposes?: string[] | null
  leasing_purpose_comment: string | null
  regions: string[]
  cart_item_ids?: UUID[]
}

export interface CommerceLeasingCalculationPayload {
  total_amount?: number
  down_payment?: number
  down_payment_percent?: number
  lease_term_months?: number
  monthly_payment?: number
  total_cost?: number
  markup?: number
  rate?: number
  total_interest?: number
  buyout_amount?: number
  vat_refund?: number
  profit_tax_savings?: number
  total_savings?: number
  selected_support?: Record<UUID, UUID[]>
  support_per_vehicle?: unknown[]
  support_per_program?: unknown[]
  support_program_details?: unknown[]
  calculations_per_vehicle?: unknown[]
}

export interface CommerceApplicationItem {
  type: CommerceItemType
  id: UUID
  item_id: UUID | null
  product_ids?: UUID[]
  title: string
  image_url: string | null
  detail_url: string | null
  quantity: number
  unit_price: CommerceMoney | null
  total_price: CommerceMoney | null
  catalog_price?: CommerceMoney | null
  show_catalog_price?: boolean | null
  discount_type?: string | null
  discount_value?: CommerceMoney | null
  discount_amount?: CommerceMoney | null
  markup_type?: string | null
  markup_value?: CommerceMoney | null
  markup_amount?: CommerceMoney | null
  final_price?: CommerceMoney | null
  comment?: string | null
  dealer_comment?: string | null
  leasing_purpose?: string | null
  leasing_purposes?: string[] | null
  region?: string | null
  regions?: string[] | null
  currency_code: string
  status: string | null
  item_role?: 'offer' | 'attachment' | 'component'
  price_on_request?: boolean
  price_status?: 'none' | 'pending' | 'set'
  price_set_by?: UUID | null
  price_set_at?: string | null
  seller_company_id?: UUID | null
  overstock_requested_quantity?: number | null
  snapshot: Record<string, unknown> | null
  support_program_details?: SupportBadgeProgram[]
}

export interface CommerceOrderSnapshot {
  title: string
  subtitle: string | null
  image_url: string | null
  manufacturer: string | null
  model: string | null
  modification: string | null
  year: number | null
}

export interface CommerceOrder {
  id: UUID
  item: CommerceItemRef
  item_snapshot: CommerceOrderSnapshot
  purchase_type: CommercePurchaseType | 'leasing'
  status: string
  total_price: CommerceMoney
  paid_amount: CommerceMoney
  remaining_amount: CommerceMoney
  currency_code: string
  leasing_application_id: UUID | null
  down_payment_percent: CommerceMoney | null
  hold_expires_at: string | null
  cancellation_reason: string | null
  cancellation_requested_at: string | null
  cancelled_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface CommerceOrderRef {
  type: CommerceItemType
  id: UUID
}

export interface CommercePayment {
  id: UUID
  order: CommerceOrderRef
  payment_type: string
  amount: CommerceMoney
  status: string
  payment_method: CommercePaymentMethod | null
  error_message: string | null
  fiscal_status: string | null
  expires_at: string | null
  paid_at: string | null
  created_at: string | null
  updated_at: string | null
  receipt_content_url: string | null
}

export interface CommerceScheduleItem {
  id: UUID
  order: CommerceOrderRef
  payment_number: number
  due_date: string
  amount: CommerceMoney
  principal: CommerceMoney | null
  interest: CommerceMoney | null
  payment_id: UUID | null
  is_paid: boolean
  payment_status: string | null
  payment_paid_at: string | null
  receipt_content_url: string | null
  can_pay: boolean
  created_at: string | null
  updated_at: string | null
}

export interface CommercePaymentWidgetData {
  formUrl: string
  formParams: Record<string, string>
  orderId: string
  amount: CommerceMoney
  expiresAt: string
}

export interface CommercePaymentSbpData {
  sbpLink: string
  orderId: string
  amount: CommerceMoney
  description: string
  expiresAt: string
}

export interface CommerceCreateOrderResult {
  orders: CommerceOrder[]
  payments: CommercePayment[]
  replayed: boolean
  widgetData?: CommercePaymentWidgetData | null
  sbpData?: CommercePaymentSbpData | null
}

export interface CommerceCreatePaymentResult {
  order: CommerceOrder
  payment: CommercePayment
  schedule_item?: CommerceScheduleItem | null
  replayed: boolean
  widgetData?: CommercePaymentWidgetData | null
  sbpData?: CommercePaymentSbpData | null
}

export interface CommerceLeasingApplicationResult {
  application_id: UUID
  items: Array<{
    item: CommerceItemRef
    line_id: UUID
    quantity: number
  }>
  status: string
}

export interface CommerceDomainAdapter {
  type: CommerceItemType
  catalogLabel: string
  catalogLocation: RouteLocationRaw
  detailLocation: (item: CommerceItem) => RouteLocationRaw | null
}

export interface CommerceProblemDetails {
  title?: string
  detail?: string
  status?: number
  message?: string
}
