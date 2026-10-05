export type WarehouseAccessType = 'A' | 'B' | 'C'
export type WarehouseOwnerType = 'dealer' | 'distributor'

export interface Warehouse {
  id: string
  name: string
  owner_company_id: string
  owner_company_type: WarehouseOwnerType
  owner_company_name?: string
  address: string
  city_id?: string | null
  city_name?: string | null
  brand_ids: string[]
  selected_brands: WarehouseMark[]
  category_id: string | null
  category_name?: string | null
  brands?: string[]
  vehicle_marks?: string[]
  is_active: boolean
  warehouse_access_type: WarehouseAccessType
  groups: string[]
  vehicles_count: number
  vehicle_types: string[]
  sites: string[]
  created_at?: string
  updated_at?: string
  // Backward compatibility fields
  brand?: string
  company_name?: string
  company_id?: string
  dealer_id?: string
}

export interface WarehouseAccessRule {
  id: string
  warehouse_id: string
  warehouse_name: string
  owner_company_id?: string
  owner_company_name?: string
  owner_company_type?: string
  warehouse_brand_names?: string[]
  target_type: 'dealer' | 'distributor'
  target_id: string
  target_name: string
  warehouse_access_type: WarehouseAccessType
  site_id?: string
  site_name?: string
  brand_id?: string
  brand_name?: string
  source_group_id?: string
  source_group_name?: string
  is_visible: boolean
  can_create_application: boolean
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface CreateWarehouseRequest {
  name: string
  owner_company_id: string
  owner_company_type: WarehouseOwnerType
  address: string
  city_id?: string | null
  brand_ids: string[]
  category_id: string | null
  is_active?: boolean
}

export interface UpdateWarehouseRequest {
  name?: string
  owner_company_id?: string
  owner_company_type?: WarehouseOwnerType
  address?: string
  city_id?: string | null
  brand_ids?: string[]
  category_id?: string | null
  is_active?: boolean
}

export interface DealerAccessItem {
  dealer_id: string
  access_type: 'B' | 'C'
}

export interface CreateWarehouseAccessRulesRequest {
  warehouse_id: string
  mode: 'dealers' | 'dealer_group'
  dealer_group_id?: string
  group_access_type?: 'B' | 'C'
  dealers?: DealerAccessItem[]
  site_id?: string
  brand_id?: string
}

export interface UpdateWarehouseAccessRuleRequest {
  warehouse_access_type?: WarehouseAccessType
  is_active?: boolean
}

export interface WarehousesPagination {
  page: number
  limit: number
  total: number
  pages: number
}

export interface WarehousesListParams {
  page?: number | string
  limit?: number | string
  search?: string
  brand_id?: string
  brand?: string
  city_id?: string
  access_type?: string
  owner_company_id?: string
  is_active?: boolean
}

export interface AccessRulesListParams {
  page?: number
  limit?: number
  warehouse_id?: string
  target_id?: string
  is_active?: boolean
}

export interface WarehouseMark {
  id: string
  name: string
  slug?: string
}

export interface WarehouseCategory {
  id: string
  name: string
}

export interface WarehouseStorefront {
  id: string
  name?: string
  slug?: string
}

export interface WarehouseDealerGroup {
  id: string
  name: string
  distributor_company_id?: string
  is_active?: boolean
}

export interface WarehouseDeleteCounts {
  products: number
  marks: number
  models: number
  modifications: number
  attributes: number
  attribute_groups: number
  trims?: number
  equipment_packages?: number
  kits?: number
  attribute_values?: number
  images?: number
  media?: number
  carts?: number
  cart_items?: number
  favorites?: number
  access_rules?: number
  storefront_links?: number
  storefronts?: number
  [key: string]: number | undefined
}

export interface WarehouseRetainedItem {
  id?: string
  entity_type?: string
  name?: string
  reason: string
  message?: string
}

export interface WarehouseBlocker {
  type?: string
  reason?: string
  message?: string
  description?: string
  count?: number
  entity_id?: string
  [key: string]: unknown
}

export interface WarehouseDeletePreviewResponse {
  warehouse: {
    id: string
    name: string
    address: string
    owner_company_id?: string
    owner_company_name?: string
    owner_company_type?: string
  }
  counts: WarehouseDeleteCounts
  retained: (string | WarehouseRetainedItem)[]
  blockers: (string | WarehouseBlocker)[] | Record<string, unknown>
  can_delete: boolean
  catalog_revision?: number
  preview_token: string
}

export interface WarehouseCascadeDeleteRequest {
  confirmation: string
  preview_token: string
}

export interface WarehouseCascadeDeleteResponse {
  warehouse_id: string
  deleted?: boolean | Record<string, number>
  retained?: (string | WarehouseRetainedItem)[]
  catalog_revision?: number
  media_cleanup_queued?: boolean
  message?: string
  [key: string]: unknown
}
