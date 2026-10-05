import type {
  CatalogCategory,
  CatalogDraft,
  CatalogEntity,
} from './types'
import { normalizeCatalogInteger } from './catalogInteger'
import { normalizeCatalogPrice } from './catalogPrice'

type CatalogPayloadCategory = Pick<
  CatalogCategory,
  'id' | 'usage_metric' | 'parent_ids' | 'attribute_links' | 'effective_attribute_links'
>

export interface CatalogCorrectionPayloadInput {
  entity: CatalogEntity
  mode: 'create' | 'edit'
  draft: CatalogDraft
  categories?: readonly CatalogPayloadCategory[]
}

export const buildCatalogCorrectionPayload = ({
  entity,
  mode,
  draft,
  categories = [],
}: CatalogCorrectionPayloadInput): Record<string, unknown> => {
  const source = draft as Readonly<Record<string, unknown>>
  const common = {
    ...(mode === 'create' ? { code: source.code } : {}),
    name: source.name,
    is_active: source.is_active,
  }
  if (entity === 'categories') {
    return {
      ...common,
      usage_metric: source.usage_metric,
      is_attachment_category: source.is_attachment_category === true,
      is_visible_in_catalog: source.is_visible_in_catalog !== false,
      sort_order: normalizeCatalogInteger(source.sort_order) ?? 0,
      parent_ids: Array.isArray(source.parent_ids) ? [...source.parent_ids] : [],
      attribute_links: Array.isArray(source.attribute_links)
        ? source.attribute_links.map(link => {
            const value = link as Record<string, unknown>
            return {
              attribute_id: value.attribute_id,
              group_id: value.group_id,
              is_required: value.is_required,
              is_filterable: value.is_filterable,
              is_visible: value.is_visible,
              sort_order: normalizeCatalogInteger(value.sort_order) ?? 0,
            }
          })
        : [],
    }
  }
  if (entity === 'marks' || entity === 'units') return common
  if (entity === 'superstructures') {
    return {
      ...common,
      category_ids: Array.isArray(source.category_ids) ? [...source.category_ids] : [],
      attributes: Array.isArray(source.attributes)
        ? source.attributes.map(attr => {
            const a = attr as Record<string, unknown>
            return {
              attribute_id: a.attribute_id,
              group_id: a.group_id,
              is_required: a.is_required === true,
              is_visible: a.is_visible === true,
              is_filterable: a.is_filterable === true,
              sort_order: normalizeCatalogInteger(a.sort_order) ?? 0,
            }
          })
        : [],
    }
  }
  if (entity === 'models') return { ...common, mark_id: source.mark_id, category_id: source.category_id }
  if (entity === 'trims') {
    if (mode === 'create') {
      return {
        modification_id: source.modification_id,
        name: source.name,
      }
    }
    return {
      name: source.name,
      is_active: source.is_active,
      sort_order: normalizeCatalogInteger(source.sort_order) ?? 0,
    }
  }
  if (entity === 'modifications') {
    const byId = new Map(categories.map(category => [category.id, category]))
    const effectiveAttributeIds = new Set<string>()
    const visited = new Set<string>()
    const collectCategoryAttributes = (categoryId: string) => {
      if (visited.has(categoryId)) return
      visited.add(categoryId)
      const category = byId.get(categoryId)
      if (!category) return
      if (category.effective_attribute_links) {
        for (const link of category.effective_attribute_links) {
          effectiveAttributeIds.add(link.attribute_id)
        }
        return
      }
      for (const link of category.attribute_links ?? []) {
        effectiveAttributeIds.add(link.attribute_id)
      }
      for (const parentId of category.parent_ids ?? []) collectCategoryAttributes(parentId)
    }
    const categoryIds = Array.isArray(source.category_ids) ? [...source.category_ids] : []
    for (const categoryId of categoryIds) {
      if (typeof categoryId === 'string') collectCategoryAttributes(categoryId)
    }
    return {
      ...common,
      model_id: source.model_id,
      year_from: normalizeCatalogInteger(source.year_from, { min: 1900, max: 2200 }),
      year_to: normalizeCatalogInteger(source.year_to, { min: 1900, max: 2200 }),
      category_ids: categoryIds,
      attribute_values: Array.isArray(source.attribute_values)
        ? source.attribute_values.filter(item => {
            const value = item as Record<string, unknown>
            return typeof value.attribute_id === 'string'
              && effectiveAttributeIds.has(value.attribute_id)
          }).map(item => {
            const value = item as Record<string, unknown>
            return value.option_id
              ? { attribute_id: value.attribute_id, option_id: value.option_id }
              : { attribute_id: value.attribute_id, value: value.value }
          })
        : [],
    }
  }
  if (entity === 'attribute-groups') {
    return {
      ...common,
      sort_order: normalizeCatalogInteger(source.sort_order) ?? 0,
      attribute_ids: Array.isArray(source.attribute_ids) ? [...source.attribute_ids] : [],
    }
  }
  if (entity === 'attributes') {
    return {
      ...(mode === 'create'
        ? { code: source.code, data_type: source.data_type }
        : {
            data_type: source.data_type,
            confirm_type_conversion: source.confirm_type_conversion === true,
          }),
      name: source.name,
      unit_id: source.unit_id || null,
      unit: source.unit || null,
      attribute_group_id: source.attribute_group_id || null,
      filter_kind: source.filter_kind,
      is_active: source.is_active,
      options: Array.isArray(source.options)
        ? source.options.map(option => {
            const value = option as Record<string, unknown>
            return {
              ...(value.id ? { id: value.id } : {}),
              code: value.code,
              name: value.name,
              sort_order: normalizeCatalogInteger(value.sort_order) ?? 0,
              is_active: value.is_active,
            }
          })
        : [],
    }
  }
  if (entity === 'colors') {
    return {
      name: source.name,
      code: source.code,
      applicability: source.applicability,
      is_active: source.is_active,
    }
  }
  const payload: Record<string, unknown> = {
    ...(mode === 'create' ? { code: source.code } : {}),
    modification_id: source.modification_id,
    trim_id: source.trim_id || null,
    seller_company_id: source.seller_company_id || null,
    description: source.description || null,
    price: normalizeCatalogPrice(source.price),
    special_price: normalizeCatalogPrice(source.special_price),
    price_on_request: source.price_on_request === true,
    price_from: source.price_on_request === true
      ? normalizeCatalogPrice(source.price_from)
      : null,
    warehouse_id: source.warehouse_id || null,
    ...(mode === 'create' ? { currency_code: 'RUB' } : {}),
    manufacture_year: normalizeCatalogInteger(source.manufacture_year, { min: 1900, max: 2200 }),
    vin: source.no_vin ? null : String(source.vin ?? '').trim() || null,
    chassis_vin: source.no_vin ? null : String(source.chassis_vin ?? '').trim() || null,
    superstructure_vin: source.no_vin ? null : String(source.superstructure_vin ?? '').trim() || null,
    no_vin: source.no_vin === true,
    condition: source.condition,
    owners_count: source.condition === 'used'
      ? normalizeCatalogInteger(source.owners_count, { min: 0 })
      : null,
    mileage_km: normalizeCatalogInteger(source.mileage_km),
    engine_hours: normalizeCatalogInteger(source.engine_hours),
    publication_status: source.publication_status,
    sale_status: source.sale_status,
    body_color_id: source.body_color_id || null,
    interior_color_id: source.interior_color_id || null,
    category_ids: Array.isArray(source.category_ids) ? [...source.category_ids] : [],
  }
  if (entity === 'products') {
    // The API clears the relation together with no_vin. Omit warehouse_id
    // rather than sending null, so UUIDs remain opaque strings end-to-end.
    if (source.no_vin === true) {
      delete payload.warehouse_id
    } else if (typeof source.warehouse_id === 'string' && source.warehouse_id) {
      payload.warehouse_id = source.warehouse_id
    } else if (mode === 'edit' && source.warehouse_id_touched === true) {
      payload.warehouse_id = null
    } else if (mode === 'edit') {
      delete payload.warehouse_id
    }
    if (payload.condition === 'new') {
      payload.owners_count = null
      payload.mileage_km = null
      payload.engine_hours = null
    } else {
      const metrics = new Set(categories
        .filter(category => (payload.category_ids as string[]).includes(category.id))
        .map(category => category.usage_metric))
      if (metrics.has('mileage_km')) payload.engine_hours = null
      if (metrics.has('engine_hours')) payload.mileage_km = null
    }
    const isKit = Boolean(
      source.is_kit === true
      || (source.creation_kind === 'attachment' && source.attachment_create_mode === 'kit')
      || (source.superstructure_id && source.model_id),
    )
    if (isKit) {
      payload.model_id = source.model_id
      payload.modification_id = source.modification_id || null
      payload.trim_id = null
      payload.superstructure_id = source.superstructure_id

      const isExisting = source.superstructure_source_mode === 'existing'
        || (source.superstructure_source_mode !== 'manual' && Boolean(source.superstructure_source_product_id))

      if (isExisting) {
        payload.superstructure_source_product_id = source.superstructure_source_product_id || null
        delete payload.superstructure_model_id
        delete payload.superstructure_modification_id
        delete payload.superstructure_name
        delete payload.superstructure_manufacturer
      } else {
        payload.superstructure_source_product_id = null
        payload.superstructure_model_id = source.superstructure_model_id || null
        payload.superstructure_modification_id = source.superstructure_modification_id || null
        payload.superstructure_name = source.superstructure_name
        payload.superstructure_manufacturer = source.superstructure_manufacturer
      }

      if (!source.modification_id && Array.isArray(source.chassis_values)) {
        payload.chassis_values = source.chassis_values
      }
      if (Array.isArray(source.superstructure_values)) {
        payload.superstructure_values = source.superstructure_values
      }
    } else {
      payload.superstructure_id = source.superstructure_id || null
    }
  }
  return payload
}
