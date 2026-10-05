import type { UUID } from '~/types/ids'
import type { RegistryImage } from '../types'

export const CATALOG_ENTITIES = [
  'products',
  'categories',
  'marks',
  'models',
  'modifications',
  'trims',
  'attributes',
  'attribute-groups',
  'colors',
  'units',
  'superstructures',
] as const

export type CatalogEntity = typeof CATALOG_ENTITIES[number]
export type CatalogSectionCounts = Record<CatalogEntity, number>

export interface CatalogSectionCountsResponse {
  products: number
  categories: number
  marks: number
  models: number
  modifications: number
  trims: number
  attributes: number
  attribute_groups: number
  colors?: number
  units?: number
  superstructures?: number
}
export type CatalogCondition = 'new' | 'used'
export type CatalogUsageMetric = 'mileage_km' | 'engine_hours'
export type CatalogDataType = 'number' | 'text' | 'boolean' | 'select'
export type CatalogFilterKind = 'exact' | 'range' | 'search'

export interface CatalogResourceBase {
  id: UUID
  code: string
  lock_version?: number
  updated_at?: string
  is_active?: boolean
}

export interface CatalogNamedRef {
  id: UUID
  code?: string
  name: string
  is_active?: boolean
}

export interface CatalogCategory extends CatalogResourceBase {
  name: string
  slug: string
  canonical_path: string
  usage_metric: CatalogUsageMetric
  sort_order: number
  is_attachment_category: boolean
  is_visible_in_catalog?: boolean
  parent_ids: UUID[]
  parents?: CatalogNamedRef[]
  image_url: string | null
  product_count?: number
  attribute_links?: CatalogCategoryAttributeLink[]
  effective_attribute_links?: CatalogEffectiveAttributeLink[]
}

export interface CatalogMark extends CatalogResourceBase {
  name: string
  slug?: string
  model_count?: number
}

export interface CatalogModel extends CatalogResourceBase {
  name: string
  mark_id: UUID
  mark?: CatalogNamedRef
  category_id?: UUID | null
  category?: CatalogNamedRef
  modification_count?: number
}

export interface CatalogModificationValue {
  attribute_id: UUID
  option_id?: UUID | null
  attribute_name?: string
  data_type?: CatalogDataType
  value: string | number | boolean | null
  display_value?: string
  group_name?: string
}

export interface CatalogModification extends CatalogResourceBase {
  name: string
  model_id: UUID
  model?: CatalogNamedRef & { mark?: CatalogNamedRef }
  year_from: number | null
  year_to: number | null
  category_ids: UUID[]
  categories?: CatalogNamedRef[]
  attribute_values: CatalogModificationValue[]
  product_count?: number
}

export interface CatalogTrim extends CatalogResourceBase {
  name: string
  slug: string
  modification_id: UUID
  modification_name: string
  model_id: UUID
  model_name: string
  mark_id: UUID
  mark_name: string
  sort_order: number
  product_count?: number
  attribute_count?: number
}

export interface CatalogTrimLifecycleItem {
  id: UUID
  modification_id: UUID
  name: string
  is_active: boolean
}

export type CatalogTrimCreateResponse = CatalogTrimLifecycleItem

export interface CatalogTrimListResponse {
  items: CatalogTrimLifecycleItem[]
}

export interface CatalogTrimAttributeCandidateOption {
  id: UUID
  code: string
  name: string
  sort_order: number
  is_active: boolean
}

export interface CatalogTrimAttributeCandidate {
  attribute_id: UUID
  attribute_code: string
  attribute_name: string
  data_type: CatalogDataType
  unit: string | null
  group_id: UUID | null
  group_name: string | null
  options: CatalogTrimAttributeCandidateOption[]
  modification_value: Omit<CatalogTrimAttributeValue, 'attribute_id'> | null
  is_available: boolean
  block_reason: string | null
  is_required: boolean
  is_filterable: boolean
  sort_order: number
}

export interface CatalogTrimAttributeCandidateGroup {
  group_id: UUID | null
  group_name: string
  sort_order: number
  attributes: CatalogTrimAttributeCandidate[]
}

export interface CatalogTrimAttributeCandidatesResponse {
  candidates: CatalogTrimAttributeCandidate[]
}

export interface CatalogTrimAttributeAssignment {
  attribute_id: UUID
  group_id: UUID | null
  attribute_code?: string
  attribute_name?: string
  data_type?: CatalogDataType
  unit?: string | null
  options?: CatalogTrimAttributeCandidateOption[]
  is_required: boolean
  is_filterable: boolean
  sort_order: number
  value_number?: string | number | null
  value_text?: string | null
  value_boolean?: boolean | null
  option_id?: UUID | null
}

export interface CatalogTrimAttributesResponse {
  items: CatalogTrimAttributeAssignment[]
}

export interface CatalogTrimAttributeValue {
  attribute_id: UUID
  value_number: string | number | null
  value_text: string | null
  value_boolean: boolean | null
  option_id: UUID | null
}

export interface CatalogTrimAttributeCreateResponse {
  item: CatalogTrimAttributeAssignment
}

export interface CatalogTrimAttributeValuesResponse {
  saved: CatalogTrimAttributeValue[]
}

export interface CatalogAttributeGroup extends CatalogResourceBase {
  name: string
  sort_order: number
  category_attribute_count?: number
  attribute_ids?: UUID[]
}

export type CatalogColorApplicability = 'body' | 'interior' | 'both'

export interface CatalogColor extends CatalogResourceBase {
  name: string
  applicability: CatalogColorApplicability
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface CatalogColorSelectItem {
  id: UUID
  name: string
  applicability: CatalogColorApplicability
}

export interface CatalogAttributeOption {
  id?: UUID
  code: string
  name: string
  sort_order: number
  is_active: boolean
  codeManuallyEdited?: boolean
}

export interface CatalogUnit extends CatalogResourceBase {
  name: string
  slug?: string
  attribute_count?: number
}

export interface CatalogSuperstructureAttribute {
  attribute_id: UUID
  group_id: UUID
  group_name?: string
  attribute_name?: string
  attribute_code?: string
  data_type?: CatalogDataType
  unit?: string | null
  is_required: boolean
  is_visible: boolean
  is_filterable: boolean
  sort_order: number
}

export interface CatalogSuperstructureAttributeCandidate {
  attribute_id: UUID
  attribute_name: string
  attribute_code: string
  data_type: CatalogDataType
  unit: string | null
  group_id: UUID
  group_name: string
  is_active: boolean
}

export interface CatalogSuperstructure extends CatalogResourceBase {
  name: string
  slug?: string
  attributes: CatalogSuperstructureAttribute[]
  category_ids?: UUID[]
  categories?: CatalogNamedRef[]
  attribute_count?: number
  product_count?: number
}

export interface CatalogAttribute extends CatalogResourceBase {
  name: string
  data_type: CatalogDataType
  filter_kind: CatalogFilterKind
  unit: string | null
  unit_id?: UUID | null
  options: CatalogAttributeOption[]
  attribute_group_id?: UUID | null
  attribute_group?: CatalogNamedRef | null
  category_count?: number
}

export interface CatalogCategoryAttributeLink {
  attribute_id: UUID
  attribute_name?: string
  group_id: UUID | null
  group_name?: string
  is_required: boolean
  is_filterable: boolean
  is_visible: boolean
  sort_order: number
  inherited?: boolean
}

export interface CatalogEffectiveAttributeLink {
  attribute_id: UUID
  attribute_name: string
  data_type: CatalogDataType
  filter_kind: CatalogFilterKind
  group_id: UUID | null
  group_name: string
  group_sort_order: number | null
  is_required: boolean
  is_filterable: boolean
  is_visible: boolean
  sort_order: number
}

export interface CatalogProduct extends CatalogResourceBase {
  slug: string
  title?: string | null
  modification_id: UUID
  trim_id?: UUID | null
  trim?: CatalogNamedRef | null
  trim_name?: string | null
  modification_name: string
  model_name: string
  mark_name: string
  modification?: CatalogNamedRef & {
    model?: CatalogNamedRef & { mark?: CatalogNamedRef }
  }
  category_ids: UUID[]
  categories?: CatalogNamedRef[]
  price: string | null
  special_price: string | null
  price_on_request: boolean
  price_from: string | null
  warehouse_id: UUID | null
  currency_code: 'RUB'
  manufacture_year: number | null
  condition: CatalogCondition
  owners_count: number | null
  no_vin: boolean
  normalization_state?: 'normalized' | 'legacy' | 'conflict'
  is_attachment?: boolean
  is_composite?: boolean
  has_own_categories?: boolean
  mileage_km: number | null
  engine_hours: number | null
  sale_status: 'available' | 'on_order' | 'reserved' | 'sold' | 'unavailable'
  publication_status: 'draft' | 'published' | 'archived'
  published_at: string | null
  seller_company_id: UUID | null
  seller_company_name?: string | null
  body_color_id?: UUID | null
  interior_color_id?: UUID | null
  body_color?: (CatalogNamedRef & { is_active: boolean }) | null
  interior_color?: (CatalogNamedRef & { is_active: boolean }) | null
  description: string | null
  vin: string | null
  chassis_vin?: string | null
  superstructure_vin?: string | null
  is_kit?: boolean
  model_id?: UUID | null
  superstructure_id?: UUID | null
  superstructure_model_id?: UUID | null
  superstructure_model?: {
    id: UUID
    code: string
    name: string
    mark: { id: UUID; code: string; name: string }
  } | null
  superstructure_modification_id?: UUID | null
  superstructure_source_product_id?: UUID | null
  superstructure_source?: {
    id: UUID
    code: string
    name: string
    publication_status: string
    mark: string
    model: string
    modification: string | null
  } | null
  superstructure_name?: string | null
  superstructure_manufacturer?: string | null
  chassis_values?: CatalogModificationValue[]
  superstructure_values?: CatalogModificationValue[]
  attribute_groups?: Array<{
    id: UUID | null
    name: string
    attributes: CatalogModificationValue[]
  }>
  images: RegistryImage[]
}

export interface AttachmentSourceItem {
  id: UUID
  code: string
  name: string
  publication_status: string
  mark?: CatalogNamedRef | null
  model?: CatalogNamedRef | null
  modification?: CatalogNamedRef | null
  superstructure_name: string
  superstructure_manufacturer: string
  superstructure_values_by_attribute: Record<string, {
    attribute_id: UUID
    option_id?: UUID | null
    value_number?: string | number | null
    value_text?: string | null
    value_boolean?: boolean | null
  }>
}

export interface CatalogProductAttachmentLink {
  attachment_product_id: UUID
  position: number
  product: CatalogProduct
}

export interface CatalogProductChassisValue {
  attribute_id: UUID
  option_id?: UUID | null
  value_number?: string | number | null
  value_text?: string | null
  value_boolean?: boolean | null
}

export interface CatalogProductSuperstructureValue {
  attribute_id: UUID
  option_id?: UUID | null
  value_number?: string | number | null
  value_text?: string | null
  value_boolean?: boolean | null
}

export interface CatalogProductAttachmentInput {
  attachment_product_id: UUID
  position: number
}

export interface CatalogProductCreateRequest extends Record<string, unknown> {
  compatible_attachments: CatalogProductAttachmentInput[]
}

export interface CatalogProductAttachmentLinksResponse {
  items: CatalogProductAttachmentLink[]
}

export interface CatalogSellerCompany {
  id: UUID
  name: string
  inn: string | null
}

/** A warehouse available for assigning to a special-equipment product. */
export interface CatalogWarehouse {
  id: UUID
  address: string
  brand?: string
  city_name?: string | null
  status?: 'active' | 'inactive'
  company_id: UUID | null
  dealer_id: UUID | null
}

export interface CatalogActiveWarehouse extends CatalogWarehouse {
  city_name: string | null
  status: 'active'
}

export type CatalogResource =
  | CatalogProduct
  | CatalogCategory
  | CatalogMark
  | CatalogModel
  | CatalogModification
  | CatalogTrim
  | CatalogAttribute
  | CatalogAttributeGroup
  | CatalogColor

export interface CatalogListResponse<T extends CatalogResource = CatalogResource> {
  items: T[]
  pagination: {
    page: number
    page_size: number
    total: number
    pages: number
  }
}

export interface CatalogProblem {
  code?: string
  message?: string
  detail?: string
  dependencies?: Array<{
    entity: string
    id: UUID
    code?: string
    name?: string
    count?: number
  }>
}

export interface CatalogColorErrorEnvelope {
  error?: {
    code?: string
    message?: string
    detail?: Record<string, unknown> | null
    field_errors?: Array<{ field?: string; code?: string; message?: string }>
  }
}

export type CatalogDraft = Record<string, unknown> & {
  id?: UUID
  code: string
  name?: string
  is_active?: boolean
  warehouse_id_touched?: boolean
}

export interface CascadeEntityRef {
  type: string
  id: string
  code?: string | null
  name?: string | null
}

export interface CascadeDeleteGroup {
  type: string
  count: number
  items: CascadeEntityRef[]
  truncated: boolean
}

export interface CascadeUnlinkGroup {
  type: string
  count: number
  description: string
}

export interface CascadeClearGroup {
  type: string
  field: string
  count: number
  description: string
}

export interface CascadeUserImpact {
  cart_items: number
  favorites: number
}

export interface CascadeProductBlockerDocument {
  type: string
  id: string
  number: string
  status: string
}

export interface CascadeProductBlocker {
  product: CascadeEntityRef
  vin?: string | null
  documents: CascadeProductBlockerDocument[]
}

export interface CascadeDistributorBlocker {
  company: {
    id: string
    name: string
    inn: string
  }
}

export interface CascadeSupportProgramBlocker {
  program: {
    id: string
    name: string
    is_active: boolean
    starts_at?: string | null
    ends_at?: string | null
  }
  references: CascadeEntityRef[]
}

export interface CascadeBlockers {
  products: CascadeProductBlocker[]
  distributors: CascadeDistributorBlocker[]
  support_programs: CascadeSupportProgramBlocker[]
  kit_sources?: Array<{
    product: { id: UUID; code: string; title: string }
    kits: Array<{ id: UUID; code: string; title: string }>
  }>
}

export interface CascadePreviewResource {
  root: CascadeEntityRef
  delete: CascadeDeleteGroup[]
  unlink: CascadeUnlinkGroup[]
  clear: CascadeClearGroup[]
  user_impact: CascadeUserImpact
  blockers: CascadeBlockers
  total: number
  preview_token: string
  catalog_revision: number
}

export interface CascadeDeletePayload {
  confirmation: string
  preview_token: string
}

export interface CascadeDeleteResult {
  deleted: Record<string, number>
  catalog_revision: number
}

