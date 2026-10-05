<template>
  <section
    v-for="group in groups"
    :key="groupKey(group)"
    class="border-t border-storefront-border"
  >
    <button
      type="button"
      class="flex min-h-12 w-full items-center justify-between gap-3 py-3 text-left text-storefront-title hover:text-storefront-link focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
      :aria-expanded="isExpanded(group)"
      :aria-controls="groupContentId(group)"
      @click="toggleGroup(group)"
    >
      <span class="min-w-0 text-base font-bold">{{ group.name }}</span>
      <span class="flex shrink-0 items-center gap-2 text-sm font-semibold text-storefront-label">
        <span v-if="selectedCount(group)">{{ selectedCount(group) }}</span>
        <ChevronDownIcon
          class="h-5 w-5 transition-transform motion-reduce:transition-none"
          :class="isExpanded(group) ? 'rotate-180' : ''"
          aria-hidden="true"
        />
      </span>
    </button>

    <div
      v-if="isExpanded(group)"
      :id="groupContentId(group)"
      class="flex flex-col gap-5 pb-5"
      :aria-busy="loading"
    >
      <template v-if="loading">
        <span v-for="index in 4" :key="index" class="h-11 animate-pulse rounded-md bg-storefront-skeleton motion-reduce:animate-none" />
      </template>

      <template v-else>
        <template v-for="attribute in orderedAttributes(group)" :key="attribute.id">
          <label
            v-if="isBooleanAttribute(attribute)"
            class="grid min-h-11 cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-1 text-sm text-storefront-text hover:bg-storefront-secondary-hover"
            :class="optionIsUnavailable(attribute, booleanOption(attribute)) ? 'text-storefront-text-muted opacity-60' : ''"
          >
            <input
              type="checkbox"
              class="h-4 w-4 rounded border-storefront-border text-storefront-link focus:ring-storefront-focus storefront-control"
              :checked="isSelected(attribute.id, 'true')"
              @change="emit('toggle-option', attribute.id, 'true')"
            >
            <span class="min-w-0 truncate">
              {{ attribute.name }}<span v-if="attribute.unit" class="text-storefront-text-muted">, {{ attribute.unit }}</span>
            </span>
            <span class="shrink-0 text-xs tabular-nums text-storefront-text-muted">{{ booleanOption(attribute)?.count ?? 0 }}</span>
          </label>

          <fieldset v-else class="flex flex-col gap-3">
            <legend class="text-sm font-semibold text-storefront-label">
              {{ attribute.name }}<span v-if="attribute.unit" class="font-normal text-storefront-text-muted">, {{ attribute.unit }}</span>
            </legend>

            <label v-if="attribute.filter_kind === 'search'" class="block">
              <span class="sr-only">Поиск: {{ attribute.name }}</span>
              <input
                :value="searchDrafts[attribute.id] ?? dynamicFilters[attribute.id]?.search ?? ''"
                type="search"
                autocomplete="off"
                :placeholder="`Найти: ${attribute.name.toLocaleLowerCase('ru-RU')}`"
                class="h-11 min-w-0 w-full rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
                @input="emit('update-search', attribute.id, $event)"
              >
            </label>

            <div v-else-if="attribute.filter_kind === 'range'" class="grid grid-cols-2 gap-2">
              <label>
                <span class="sr-only">Минимум: {{ attribute.name }}</span>
                <input
                  :value="dynamicFilters[attribute.id]?.min ?? ''"
                  type="text"
                  inputmode="decimal"
                  autocomplete="off"
                  placeholder="От"
                  class="h-11 min-w-0 w-full rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
                  @change="emit('update-range', attribute.id, 'min', $event)"
                >
              </label>
              <label>
                <span class="sr-only">Максимум: {{ attribute.name }}</span>
                <input
                  :value="dynamicFilters[attribute.id]?.max ?? ''"
                  type="text"
                  inputmode="decimal"
                  autocomplete="off"
                  placeholder="До"
                  class="h-11 min-w-0 w-full rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
                  @change="emit('update-range', attribute.id, 'max', $event)"
                >
              </label>
            </div>

            <div v-else class="max-h-56 overflow-y-auto pr-1">
              <label
                v-for="option in visibleOptions(attribute)"
                :key="option.value"
                class="grid min-h-11 cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-1 text-sm text-storefront-text hover:bg-storefront-secondary-hover"
                :class="optionIsUnavailable(attribute, option) ? 'text-storefront-text-muted opacity-60' : ''"
              >
                <input
                  type="checkbox"
                  class="h-4 w-4 rounded border-storefront-border text-storefront-link focus:ring-storefront-focus storefront-control"
                  :checked="isSelected(attribute.id, option.value)"
                  @change="emit('toggle-option', attribute.id, option.value)"
                >
                <span class="min-w-0 truncate">{{ option.label }}</span>
                <span class="shrink-0 text-xs tabular-nums text-storefront-text-muted">{{ option.count }}</span>
              </label>
            </div>
            <button
              v-if="attribute.options.length > optionsLimit && !showAll[attribute.id]"
              type="button"
              class="min-h-11 self-start px-1 text-sm font-semibold text-storefront-link hover:text-storefront-link-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
              @click="showAll[attribute.id] = true"
            >
              Показать все ({{ attribute.options.length }})
            </button>
          </fieldset>
        </template>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ChevronDownIcon } from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type {
  SpecialEquipmentAttributeFacet,
  SpecialEquipmentAttributeFacetGroup,
  SpecialEquipmentDynamicFilters,
  SpecialEquipmentFacetOption,
} from '../types'

const optionsLimit = 6
const props = defineProps<{
  groups: SpecialEquipmentAttributeFacetGroup[]
  dynamicFilters: SpecialEquipmentDynamicFilters
  searchDrafts: Partial<Record<UUID, string>>
  loading?: boolean
}>()
const emit = defineEmits<{
  'toggle-option': [attributeId: UUID, value: string]
  'update-range': [attributeId: UUID, side: 'min' | 'max', event: Event]
  'update-search': [attributeId: UUID, event: Event]
}>()

const expandedGroups = ref(new Set<string>())
const seenGroups = new Set<string>()
const showAll = reactive<Partial<Record<UUID, boolean>>>({})

const groupKey = (group: SpecialEquipmentAttributeFacetGroup): string => group.id ?? 'other'
const groupContentId = (group: SpecialEquipmentAttributeFacetGroup): string => `special-equipment-facet-group-${groupKey(group)}`
const isExpanded = (group: SpecialEquipmentAttributeFacetGroup): boolean => expandedGroups.value.has(groupKey(group))
const toggleGroup = (group: SpecialEquipmentAttributeFacetGroup) => {
  const key = groupKey(group)
  const next = new Set(expandedGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedGroups.value = next
}

const isSelected = (attributeId: UUID, value: string): boolean =>
  props.dynamicFilters[attributeId]?.values.includes(value) ?? false
const selectedCount = (group: SpecialEquipmentAttributeFacetGroup): number => group.attributes.reduce((count, attribute) => {
  const filter = props.dynamicFilters[attribute.id]
  if (!filter) return count
  return count + filter.values.length + Number(Boolean(filter.min || filter.max || filter.search))
}, 0)
const hasActiveFilter = (attribute: SpecialEquipmentAttributeFacet): boolean => {
  const filter = props.dynamicFilters[attribute.id]
  return Boolean(filter?.values.length || filter?.min || filter?.max || filter?.search)
}

watch(() => props.groups, groups => {
  for (const group of groups) {
    const key = groupKey(group)
    if (seenGroups.has(key)) continue
    seenGroups.add(key)
    if (group.attributes.some(hasActiveFilter)) {
      expandedGroups.value = new Set([...expandedGroups.value, key])
    }
  }
}, { immediate: true, deep: true })

const isBooleanAttribute = (attribute: SpecialEquipmentAttributeFacet): boolean =>
  attribute.data_type === 'boolean' && attribute.filter_kind === 'exact'
const booleanOption = (attribute: SpecialEquipmentAttributeFacet): SpecialEquipmentFacetOption | undefined =>
  attribute.options.find(option => option.value === 'true')
const optionIsUnavailable = (attribute: SpecialEquipmentAttributeFacet, option?: SpecialEquipmentFacetOption): boolean =>
  Boolean(option && option.count === 0 && isSelected(attribute.id, option.value))
const visibleOptions = (attribute: SpecialEquipmentAttributeFacet): SpecialEquipmentFacetOption[] =>
  showAll[attribute.id] ? attribute.options : attribute.options.slice(0, optionsLimit)
const orderedAttributes = (group: SpecialEquipmentAttributeFacetGroup): SpecialEquipmentAttributeFacet[] => [
  ...group.attributes.filter(attribute => attribute.filter_kind === 'range'),
  ...group.attributes.filter(attribute => attribute.filter_kind === 'exact' && !isBooleanAttribute(attribute)),
  ...group.attributes.filter(isBooleanAttribute),
  ...group.attributes.filter(attribute => attribute.filter_kind === 'search'),
]
</script>
