import type { UUID } from '~/types/ids'

export type SpecialEquipmentSort =
  | 'published_desc'
  | 'published_asc'
  | 'price_asc'
  | 'price_desc'
  | 'name_asc'
  | 'mileage_asc'
  | 'mileage_desc'
  | 'engine_hours_asc'
  | 'engine_hours_desc'

export type SpecialEquipmentSaleStatus =
  | 'available'
  | 'on_order'
  | 'reserved'
  | 'sold'
  | 'unavailable'

export type SpecialEquipmentPrice = string | number | null
export type SpecialEquipmentUsageMetric = 'mileage_km' | 'engine_hours'
export type SpecialEquipmentCondition = '' | 'new' | 'used'

export interface SpecialEquipmentCategoryNode {
  id: UUID
  name: string
  slug: string
  sort_order: number
  image_url: string | null
  usage_metric: SpecialEquipmentUsageMetric
  is_attachment_category: boolean
  product_count?: number
  parent_ids: UUID[]
  child_ids: UUID[]
}

export interface SpecialEquipmentCategoryRef {
  id: UUID
  name: string
  slug: string
}

export interface SpecialEquipmentTerminalCategory extends SpecialEquipmentCategoryRef {
  code: string
}

export interface SpecialEquipmentCategoryPlacement {
  parent_id: UUID
  category_id: UUID
  sort_order: number
}

export interface SpecialEquipmentMark {
  id: UUID
  name: string
  slug?: string
}

export interface SpecialEquipmentModelRef {
  id: UUID
  name: string
  slug?: string
  mark: SpecialEquipmentMark
}

export interface SpecialEquipmentModificationRef {
  id: UUID
  name: string
  slug?: string
  year_from?: number | null
  year_to?: number | null
  model: SpecialEquipmentModelRef
}

export interface SpecialEquipmentSuperstructureRef {
  id: UUID
  name: string
  type_name?: string | null
  manufacturer?: string | null
}

export function productModel<T extends { id?: UUID | null; name?: string | null }>(product: {
  model?: T | null
  modification?: { model: T } | null
}): T {
  if (product.model) return product.model
  if (product.modification?.model) return product.modification.model
  throw new Error('Product is missing both model and modification.model')
}

export interface SpecialEquipmentTrimRef {
  id: UUID
  name: string
  slug?: string
  code?: string
}

export interface SpecialEquipmentImage {
  id: UUID
  content_url: string
  alt_text: string | null
  sort_order?: number
  is_primary?: boolean
}

export interface SpecialEquipmentColorRef {
  id: UUID
  name: string
  code?: string
}

export interface SpecialEquipmentWarehouseStock {
  warehouse_id: UUID
  address: string
  brand: string
  owner_company_name: string
  count: number
}

export interface SpecialEquipmentCardAttribute {
  id: UUID
  code: string
  name: string
  data_type: 'number' | 'text' | 'boolean' | 'select'
  unit: string | null
  group_id: UUID | null
  group_name: string
  value: string | boolean | null
  display_value: string
  option_id: UUID | null
  option_label: string | null
}

export interface SpecialEquipmentCapabilities {
  can_favorite: boolean
  can_add_to_cart: boolean
  can_lease: boolean
  can_buy: boolean
  can_preorder: boolean
  reason?: string | null
}

export interface SpecialEquipmentProductCard {
  id: UUID
  slug: string
  detail_url: string | null
  code: string
  title?: string | null
  model?: SpecialEquipmentModelRef | null
  modification: SpecialEquipmentModificationRef | null
  superstructure?: SpecialEquipmentSuperstructureRef | null
  trim: SpecialEquipmentTrimRef | null
  /** Effective price used by checkout and public sorting. */
  price: SpecialEquipmentPrice
  /** Explicit request-price mode. Price renderers must not infer it from null. */
  price_on_request: boolean
  /** Public lower bound shown exactly as "от N ₽" in request-price mode. */
  price_from: SpecialEquipmentPrice
  base_price: SpecialEquipmentPrice
  special_price: SpecialEquipmentPrice
  currency_code: 'RUB'
  manufacture_year: number | null
  condition: Exclude<SpecialEquipmentCondition, ''>
  owners_count?: number | null
  normalization_state?: 'normalized' | 'legacy' | 'conflict'
  mileage_km: number | null
  engine_hours: number | null
  categories: SpecialEquipmentCategoryRef[]
  terminal_category: SpecialEquipmentTerminalCategory | null
  sale_status: SpecialEquipmentSaleStatus
  body_color: SpecialEquipmentColorRef | null
  interior_color: SpecialEquipmentColorRef | null
  primary_image: SpecialEquipmentImage | null
  capabilities: SpecialEquipmentCapabilities
  available_count: number
  warehouse_city_name?: string | null
  warehouse_stock: SpecialEquipmentWarehouseStock[]
  card_attributes: SpecialEquipmentCardAttribute[]
}

export type SpecialEquipmentAttributeValue = string | number | boolean | null

export interface SpecialEquipmentAttributeSource {
  id: UUID
  code: string
  display_name: string
}

export interface SpecialEquipmentProductAttribute {
  id: UUID
  code: string
  name: string
  data_type: 'number' | 'text' | 'boolean' | 'select'
  unit: string | null
  group_id: UUID | null
  group_name: string
  value: SpecialEquipmentAttributeValue
  display_value: string
  option_id: UUID | null
  option_label: string | null
  source_product: SpecialEquipmentAttributeSource | null
}

export interface SpecialEquipmentProductAttributeGroup {
  id: UUID | null
  name: string
  section?: 'chassis' | 'superstructure' | null
  attributes: SpecialEquipmentProductAttribute[]
}

export interface SpecialEquipmentProductDetail extends SpecialEquipmentProductCard {
  description: string | null
  attribute_groups?: SpecialEquipmentProductAttributeGroup[]
  trim_attribute_groups?: SpecialEquipmentProductAttributeGroup[]
  attributes?: SpecialEquipmentProductAttribute[]
  images: SpecialEquipmentImage[]
}

export interface SpecialEquipmentCompatibleAttachment {
  product: SpecialEquipmentProductCard
  position: number
  primary_category: SpecialEquipmentCategoryRef | null
}

export interface SpecialEquipmentCompatibleAttachmentsResponse {
  items: SpecialEquipmentCompatibleAttachment[]
}

export interface SpecialEquipmentAttachmentSelection {
  product_id: UUID
  quantity: number
}

export interface SpecialEquipmentPagination {
  page: number
  page_size: number
  total: number
  pages: number
}

export interface SpecialEquipmentMarkFacet {
  id: UUID
  name: string
  count: number
}

export interface SpecialEquipmentModelFacet {
  id: UUID
  name: string
  count: number
  mark_id: UUID
}

export interface SpecialEquipmentModificationFacet {
  id: UUID
  name: string
  count: number
  model_id: UUID
}

export interface SpecialEquipmentTrimFacet {
  id: UUID
  name: string
  count: number
  modification_id: UUID
}

export interface SpecialEquipmentColorFacet {
  id: UUID
  name: string
  count: number
}

export interface SpecialEquipmentSuperstructureFacet {
  id: UUID
  name: string
  count: number
}

export interface SpecialEquipmentCityFacet {
  id: UUID
  name: string
  count: number
}

export interface SpecialEquipmentWarehouseFacet {
  id: UUID
  city_id: UUID | null
  city_name: string | null
  address: string
  brand: string | null
  count: number
}

export interface SpecialEquipmentFacetOption {
  value: string
  label: string
  count: number
}

/**
 * Boolean exact facets normally expose only the `true` option labelled «Есть».
 * A legacy `false` option may be present only when it is already selected, so the user can remove it.
 */
export interface SpecialEquipmentAttributeFacet {
  id: UUID
  code: string
  name: string
  data_type: 'number' | 'text' | 'boolean' | 'select'
  filter_kind: 'exact' | 'range' | 'search'
  unit: string | null
  group_id: UUID | null
  group_name: string
  min: SpecialEquipmentPrice
  max: SpecialEquipmentPrice
  options: SpecialEquipmentFacetOption[]
}

export interface SpecialEquipmentAttributeFacetGroup {
  id: UUID | null
  name: string
  sort_order: number
  attributes: SpecialEquipmentAttributeFacet[]
}

export interface SpecialEquipmentFacets {
  marks: SpecialEquipmentMarkFacet[]
  models: SpecialEquipmentModelFacet[]
  modifications: SpecialEquipmentModificationFacet[]
  trims: SpecialEquipmentTrimFacet[]
  superstructures?: SpecialEquipmentSuperstructureFacet[]
  body_colors: SpecialEquipmentColorFacet[]
  interior_colors: SpecialEquipmentColorFacet[]
  availability: {
    available: number
    on_order: number
  }
  conditions: {
    new: number
    used: number
  }
  price: {
    min: SpecialEquipmentPrice
    max: SpecialEquipmentPrice
  }
  usage: {
    metric: SpecialEquipmentUsageMetric | null
    min: SpecialEquipmentPrice
    max: SpecialEquipmentPrice
  }
  cities?: SpecialEquipmentCityFacet[]
  warehouses?: SpecialEquipmentWarehouseFacet[]
  attribute_groups: SpecialEquipmentAttributeFacetGroup[]
}

export interface SpecialEquipmentProductsResponse {
  items: SpecialEquipmentProductCard[]
  pagination: SpecialEquipmentPagination
  facets: SpecialEquipmentFacets
}

export interface SpecialEquipmentCategoriesResponse {
  items: SpecialEquipmentCategoryNode[]
  placements: SpecialEquipmentCategoryPlacement[]
  /** Complete server-ordered root set. */
  root_items: SpecialEquipmentCategoryNode[]
}

export interface SpecialEquipmentCategoryContextResponse {
  items: SpecialEquipmentCategoryRef[]
  category: SpecialEquipmentCategoryRef
}

export interface SpecialEquipmentMarksResponse {
  items: SpecialEquipmentMark[]
}

export type SpecialEquipmentFacetsResponse = SpecialEquipmentFacets

export interface SpecialEquipmentCommerceItem {
  product_id: UUID
  added_at?: string
  is_selected?: boolean
}

export interface SpecialEquipmentCommerceListResponse {
  items: SpecialEquipmentCommerceItem[]
}

/** Compact product projection returned by authenticated commerce resources. */
export interface SpecialEquipmentCommerceProduct {
  id: UUID
  slug: string | null
  title?: string | null
  detail_url: string | null
  mark: {
    id: UUID | null
    name: string | null
  }
  model: {
    id: UUID | null
    name: string | null
  }
  modification: {
    id: UUID | null
    name: string | null
  } | null
  superstructure?: SpecialEquipmentSuperstructureRef | null
  trim: {
    id: UUID | null
    name: string | null
  } | null
  manufacture_year: number | null
  price: SpecialEquipmentPrice
  price_on_request?: boolean
  price_from?: SpecialEquipmentPrice
  currency_code: string
  sale_status: string | null
  primary_image: {
    id: UUID
    content_url: string
  } | null
  capabilities: SpecialEquipmentCapabilities
  /** Confirmed aggregated stock; null until the public product projection is resolved. */
  available_count?: number | null
  body_color?: { id: UUID; name: string } | null
  base_price?: SpecialEquipmentPrice
  special_price?: SpecialEquipmentPrice
}

export interface SpecialEquipmentProblemDetails {
  type?: string
  title?: string
  status?: number
  detail?: string
  instance?: string
}

export interface SpecialEquipmentCatalogQuery {
  markIds: UUID[]
  modelIds: UUID[]
  modificationIds: UUID[]
  trimIds: UUID[]
  superstructureIds?: UUID[]
  bodyColorIds: UUID[]
  interiorColorIds: UUID[]
  availability: Array<'available' | 'on_order'>
  condition: SpecialEquipmentCondition
  priceMin: string
  priceMax: string
  usageMin: string
  usageMax: string
  cityId?: UUID | ''
  warehouseId?: UUID | ''
  minInStock?: string
  search: string
  descriptionInclude: string
  descriptionExclude: string
  sort: SpecialEquipmentSort
  page: number
  attributeTokens: string[]
}

export interface SpecialEquipmentDynamicFilter {
  values: string[]
  min: string
  max: string
  search: string
}

export type SpecialEquipmentDynamicFilters = Record<UUID, SpecialEquipmentDynamicFilter>

export type SpecialEquipmentCheckoutIntent = 'leasing' | 'full_purchase' | 'reservation' | 'preorder'
export type SpecialEquipmentPaymentMethod = 'card' | 'sbp' | 'bank_transfer'

export interface SpecialEquipmentFavoriteItem {
  product_id: UUID
  product: SpecialEquipmentCommerceProduct
  added_at: string
}

export interface SpecialEquipmentFavoritesResponse {
  items: SpecialEquipmentFavoriteItem[]
}

export interface SpecialEquipmentCartItem {
  id: UUID
  product_id: UUID
  quantity: number
  allow_overstock?: boolean
  parent_item_id: UUID | null
  transfer_id: UUID | null
  is_selected: boolean
  custom_price: SpecialEquipmentPrice
  comment: string | null
  equipments: Array<Record<string, unknown>>
  services: Array<Record<string, unknown>>
  added_at: string
  updated_at: string
  product: SpecialEquipmentCommerceProduct
}

export interface SpecialEquipmentCartResponse {
  items: SpecialEquipmentCartItem[]
}

export interface SpecialEquipmentPayment {
  id: UUID
  purchase_order_id: UUID
  user_id: UUID
  payment_type: string
  amount: string | number
  status: string
  payment_method: SpecialEquipmentPaymentMethod | null
  error_message: string | null
  fiscal_status: string | null
  expires_at: string | null
  paid_at: string | null
  created_at: string
  updated_at: string
  receipt_content_url: string | null
}

export interface SpecialEquipmentPaymentWidgetData {
  formUrl: string
  formParams: Record<string, string>
  orderId: string
  amount: string | number
  expiresAt: string
}

export interface SpecialEquipmentPaymentSbpData {
  sbpLink: string
  orderId: string
  amount: string | number
  description: string
  expiresAt: string
}

export interface SpecialEquipmentOrder {
  id: UUID
  user_id: UUID
  product_id: UUID
  seller_company_id: UUID | null
  leasing_application_id: UUID | null
  purchase_type: 'reservation' | 'preorder' | 'full_purchase' | 'leasing'
  status: string
  unit_price: string | number
  total_price: string | number
  paid_amount: string | number
  remaining_amount: string | number
  currency_code: string
  down_payment_percent: string | number | null
  item_snapshot: Record<string, unknown>
  hold_expires_at: string | null
  cancellation_reason: string | null
  cancellation_requested_at: string | null
  cancelled_at: string | null
  created_at: string
  updated_at: string
  payments?: SpecialEquipmentPayment[]
}

export interface SpecialEquipmentCreateOrderResponse {
  order: SpecialEquipmentOrder
  payment: SpecialEquipmentPayment | null
  replayed: boolean
  widgetData?: SpecialEquipmentPaymentWidgetData | null
  sbpData?: SpecialEquipmentPaymentSbpData | null
}

export interface SpecialEquipmentOrderResponse {
  order: SpecialEquipmentOrder
}

export interface SpecialEquipmentOrdersResponse {
  items: SpecialEquipmentOrder[]
}

export interface SpecialEquipmentCreatePaymentResponse {
  order: SpecialEquipmentOrder
  payment: SpecialEquipmentPayment
  replayed: boolean
  widgetData?: SpecialEquipmentPaymentWidgetData | null
  sbpData?: SpecialEquipmentPaymentSbpData | null
}

export interface SpecialEquipmentLeasingScheduleItem {
  id: UUID
  purchase_order_id: UUID
  payment_number: number
  due_date: string
  amount: string | number
  principal: string | number | null
  interest: string | number | null
  payment_id: UUID | null
  is_paid: boolean
  payment_status: string | null
  payment_paid_at: string | null
  receipt_content_url: string | null
  can_pay: boolean
  created_at: string
  updated_at: string
}

export interface SpecialEquipmentLeasingScheduleResponse {
  items: SpecialEquipmentLeasingScheduleItem[]
}

export interface SpecialEquipmentCreateScheduledPaymentResponse extends SpecialEquipmentCreatePaymentResponse {
  schedule_item: SpecialEquipmentLeasingScheduleItem
}

export interface SpecialEquipmentPaymentConfirmationResponse {
  order: SpecialEquipmentOrder
  payment: SpecialEquipmentPayment
}

export interface SpecialEquipmentPaymentStatusResponse {
  payment: Pick<SpecialEquipmentPayment, 'id' | 'status' | 'fiscal_status' | 'receipt_content_url' | 'error_message' | 'expires_at' | 'paid_at'>
}

export interface SpecialEquipmentLeasingApplicationResponse {
  application_id: UUID
  item_id: UUID
  product_id: UUID
  status: string | null
  item_status: string
}
