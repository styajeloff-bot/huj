import type { UUID } from '~/types/ids'
import type {
  CatalogAttribute,
  CatalogCategory,
  CatalogEffectiveAttributeLink,
} from './types'

export interface ModificationAttributeField {
  attribute: CatalogAttribute
  isRequired: boolean
  sortOrder: number
}

export interface ModificationAttributeGroupSection {
  id: UUID | null
  name: string
  sortOrder: number
  fields: ModificationAttributeField[]
}

export const buildModificationAttributeGroups = ({
  categoryIds,
  categories,
  attributes,
}: {
  categoryIds: readonly UUID[]
  categories: readonly CatalogCategory[]
  attributes: readonly CatalogAttribute[]
}): ModificationAttributeGroupSection[] => {
  const categoriesById = new Map(categories.map(category => [category.id, category]))
  const rules = new Map<UUID, CatalogEffectiveAttributeLink>()
  for (const categoryId of categoryIds) {
    const category = categoriesById.get(categoryId)
    if (!category) continue
    for (const link of category.effective_attribute_links ?? []) {
      const existing = rules.get(link.attribute_id)
      if (!existing) {
        rules.set(link.attribute_id, { ...link })
        continue
      }
      rules.set(link.attribute_id, {
        ...existing,
        is_required: existing.is_required || link.is_required,
        is_filterable: existing.is_filterable || link.is_filterable,
        is_visible: existing.is_visible || link.is_visible,
        sort_order: Math.min(existing.sort_order, link.sort_order),
      })
    }
  }

  const attributesById = new Map(attributes.map(attribute => [attribute.id, attribute]))
  const sections = new Map<UUID | null, ModificationAttributeGroupSection>()
  for (const rule of rules.values()) {
    const attribute = attributesById.get(rule.attribute_id) ?? {
      id: rule.attribute_id,
      code: rule.attribute_id,
      name: rule.attribute_name,
      data_type: rule.data_type,
      filter_kind: rule.filter_kind,
      unit: null,
      options: [],
    }
    const groupId = rule.group_id
    const section = sections.get(groupId) ?? {
      id: groupId,
      name: rule.group_name ?? 'Прочие',
      sortOrder: rule.group_sort_order ?? Number.MAX_SAFE_INTEGER,
      fields: [],
    }
    section.fields.push({
      attribute,
      isRequired: rule.is_required,
      sortOrder: rule.sort_order,
    })
    sections.set(groupId, section)
  }

  for (const section of sections.values()) {
    section.fields.sort((left, right) => left.sortOrder - right.sortOrder
      || left.attribute.name.localeCompare(right.attribute.name, 'ru')
      || left.attribute.id.localeCompare(right.attribute.id))
  }
  return [...sections.values()].sort((left, right) => left.sortOrder - right.sortOrder
    || left.name.localeCompare(right.name, 'ru')
    || String(left.id).localeCompare(String(right.id)))
}
