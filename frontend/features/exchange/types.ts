import type { UUID } from '~/types/ids'
import type { SupportBadgeProgram } from '~/types/support'

export type VehicleId = UUID
export type EntityId = UUID
export type ExchangeRequestId = UUID

export interface DealerOption {
  id: UUID
  name: string
  sort_order: number
  is_active?: boolean
}

export interface ExchangeCartItem {
  id: UUID
  vehicle_id: VehicleId
  quantity: number
  expiration_at: string | null
  discount_type: 'rubles_off' | 'percent_off' | 'fixed_price' | null
  discount_value: number | null
  file_url: string | null
  file_name: string | null
  selected_warehouse_ids: EntityId[]
  selected_option_ids: EntityId[]
  dealer_comments: DealerComment[]
  eligible_support_programs: SupportBadgeProgram[]
  selected_support_ids: UUID[]
  support_price_base: number
  support_price_display: number
  support_price_amount: number
  // Enriched vehicle data
  mark_name: string
  mark_cyrillic?: string
  model_name: string
  model_cyrillic?: string
  generation_name?: string
  configuration_name?: string
  group_name?: string
  color?: string
  vehicle_year?: number
  base_price: number
  discount_price: number | null
  images: string[]
}

export interface DealerComment {
  dealer_id: UUID
  dealer_name: string
  comment: string
}

export interface WarehouseInfo {
  id: EntityId
  address: string
  brand: string
  city_id?: EntityId | null
  city_name?: string | null
  dealer_id?: EntityId | null
  dealer_name: string
  company_name?: string | null
  vehicle_count?: number
  min_price?: number | string | null
  max_price?: number | string | null
}

export interface ExchangeRequest {
  lc_company_id: UUID | null
  id: ExchangeRequestId
  batch_number: number | null
  batch_index: number | null
  vehicle_id: VehicleId
  quantity: number
  expiration_at: string | null
  discount_type: string | null
  discount_value: number | null
  file_url: string | null
  file_name: string | null
  status: 'open' | 'deal' | 'archived'
  accepted_bid_id: UUID | null
  created_at: string
  updated_at: string
  warehouses: WarehouseInfo[]
  options: DealerOption[]
  bids: ExchangeBid[]
  bid_count: number
  dealer_comments: DealerComment[]
  selected_support_ids: UUID[]
  support_program_details: SupportBadgeProgram[]
  support_price_base: number
  support_price_display: number
  support_price_amount: number
  // Enriched vehicle data
  mark_name: string
  mark_cyrillic?: string
  model_name: string
  model_cyrillic?: string
  generation_name?: string
  configuration_name?: string
  group_name?: string
  color?: string
  vehicle_year?: number
  base_price: number
  discount_price: number | null
  images: string[]
}

export type KpStatus = 'none' | 'sent' | 'accepted' | 'rejected'

export interface ExchangeBid {
  id: UUID
  request_id: ExchangeRequestId
  dealer_id?: UUID
  dealer_name?: string
  price: number
  quantity: number
  comment: string | null
  options: DealerOption[]
  is_accepted: boolean
  rank: number
  is_own: boolean
  created_at: string
  updated_at: string
  lc_comments?: BidComment[]
  bid_file_url: string | null
  bid_file_name: string | null
  kp_file_url: string | null
  kp_file_name: string | null
  kp_status: KpStatus
  kp_dealer_comment: string | null
  kp_sent_at: string | null
  kp_responded_at: string | null
}

export interface BidComment {
  id: UUID
  user_id: UUID
  user_name?: string
  comment: string
  created_at: string
}

export interface ExchangeRequestFile {
  id: UUID
  request_id: ExchangeRequestId
  dealer_id: UUID | null
  file_url: string
  file_name: string
  file_type: 'kp' | 'detail'
  uploaded_by: UUID
  created_at: string
}

export type ExchangeRequestStatus = 'open' | 'deal' | 'archived'
export type DiscountType = 'rubles_off' | 'percent_off' | 'fixed_price'
