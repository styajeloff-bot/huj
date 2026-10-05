<template>
  <form data-storefront-block="equipment.filters" class="flex flex-col gap-7 text-storefront-text" @submit.prevent="applyRanges">
    <SpecialEquipmentFacetDialog
      v-if="facets.marks.length > 0"
      label="Марка"
      :options="facets.marks"
      :model-value="query.markIds"
      @apply="applyMarks"
    />

    <SpecialEquipmentFacetDialog
      v-if="facets.models.length > 0"
      label="Модель"
      :options="availableModels"
      :model-value="query.modelIds"
      :disabled="query.markIds.length === 0"
      disabled-reason="Сначала выберите марку"
      @apply="applyModels"
    />

    <SpecialEquipmentFacetDialog
      v-if="facets.modifications.length > 0"
      label="Модификация"
      :options="availableModifications"
      :model-value="query.modificationIds"
      :disabled="query.markIds.length === 0 || query.modelIds.length === 0"
      disabled-reason="Сначала выберите модель"
      @apply="applyModifications"
    />

    <SpecialEquipmentFacetDialog
      v-if="facets.trims.length > 0"
      label="Комплектация"
      :options="availableTrims"
      :model-value="query.trimIds"
      :disabled="query.modificationIds.length === 0"
      disabled-reason="Сначала выберите модификацию"
      @apply="applyTrims"
    />

    <SpecialEquipmentFacetDialog
      v-if="(facets.superstructures?.length ?? 0) > 0"
      label="Надстройка"
      :options="facets.superstructures ?? []"
      :model-value="query.superstructureIds ?? []"
      @apply="applySuperstructures"
    />

    <SpecialEquipmentFacetDialog
      v-if="facets.body_colors.length > 0"
      label="Цвет кузова"
      :options="facets.body_colors"
      :model-value="query.bodyColorIds"
      @apply="applyBodyColors"
    />

    <SpecialEquipmentFacetDialog
      v-if="facets.interior_colors.length > 0"
      label="Цвет салона"
      :options="facets.interior_colors"
      :model-value="query.interiorColorIds"
      @apply="applyInteriorColors"
    />

    <fieldset class="flex flex-col gap-3">
      <legend class="text-sm font-semibold text-storefront-label">Расположение и наличие</legend>
      <label class="grid gap-1.5 text-sm font-semibold text-storefront-label">
        Город
        <select aria-label="Город" :value="query.cityId" class="h-11 rounded-lg border border-storefront-border bg-storefront-surface px-3 text-sm text-storefront-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control" @change="changeCity">
          <option value="">Все города</option>
          <option v-for="city in facets.cities ?? []" :key="city.id" :value="city.id">{{ city.name }} ({{ city.count }})</option>
        </select>
      </label>
      <label class="grid gap-1.5 text-sm font-semibold text-storefront-label">
        Склад
        <select aria-label="Склад" :value="query.warehouseId" :disabled="availableWarehouses.length === 0" class="h-11 rounded-lg border border-storefront-border bg-storefront-surface px-3 text-sm text-storefront-text disabled:cursor-not-allowed disabled:bg-storefront-disabled focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control" @change="changeWarehouse">
          <option value="">Все склады</option>
          <option v-for="warehouse in availableWarehouses" :key="warehouse.id" :value="warehouse.id">{{ specialEquipmentWarehouseFacetLabel(warehouse) }} ({{ warehouse.count }})</option>
        </select>
      </label>
      <label class="grid gap-1.5 text-sm font-semibold text-storefront-label">
        Минимум на складе
        <input
          :value="localMinInStock"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          placeholder="0"
          :aria-invalid="Boolean(stockError)"
          :aria-describedby="stockError ? 'special-equipment-min-stock-error' : undefined"
          class="h-11 rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
          @blur="applyMinInStock"
        >
        <span
          v-if="stockError"
          id="special-equipment-min-stock-error"
          class="text-sm font-medium text-storefront-error-text"
          role="alert"
        >{{ stockError }}</span>
      </label>
    </fieldset>

    <fieldset class="flex flex-col gap-3">
      <legend class="text-sm font-semibold text-storefront-label">Описание объявления</legend>
      <label class="flex flex-col gap-2">
        <span class="text-sm font-medium text-storefront-text">Поиск по описанию</span>
        <input
          :value="query.descriptionInclude"
          type="search"
          autocomplete="off"
          maxlength="500"
          placeholder="Например, усиленная рама"
          class="h-11 min-w-0 w-full rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
          @blur="updateDescription('descriptionInclude', $event)"
        >
      </label>
      <label class="flex flex-col gap-2">
        <span class="text-sm font-medium text-storefront-text">Исключить из описания</span>
        <input
          :value="query.descriptionExclude"
          type="search"
          autocomplete="off"
          maxlength="500"
          placeholder="Например, требует ремонта"
          class="h-11 min-w-0 w-full rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
          @blur="updateDescription('descriptionExclude', $event)"
        >
      </label>
    </fieldset>

    <fieldset class="flex flex-col gap-3">
      <legend class="text-sm font-semibold text-storefront-label">Наличие</legend>
      <div class="flex flex-wrap gap-2">
        <label
          v-for="option in availabilityOptions"
          :key="option.value"
          class="grid min-h-11 basis-36 flex-1 cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold"
          :class="query.availability.includes(option.value) ? 'border-storefront-selected-border bg-storefront-selected text-storefront-selected-foreground' : 'border-storefront-border bg-storefront-surface text-storefront-text'"
        >
          <input
            type="checkbox"
            class="h-4 w-4 rounded border-storefront-border text-storefront-link focus:ring-storefront-focus storefront-control"
            :checked="query.availability.includes(option.value)"
            @change="toggleAvailability(option.value)"
          >
          <span class="min-w-0 leading-snug">{{ option.label }}</span>
          <span class="shrink-0 text-xs tabular-nums text-storefront-text-muted">{{ option.count }}</span>
        </label>
      </div>
    </fieldset>

    <fieldset class="flex flex-col gap-3">
      <legend class="text-sm font-semibold text-storefront-label">Состояние</legend>
      <div class="flex flex-wrap gap-2">
        <label
          v-for="option in conditionOptions"
          :key="option.value"
          class="flex min-h-11 basis-36 flex-1 cursor-pointer items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-sm font-semibold"
          :class="query.condition === option.value ? 'border-storefront-selected-border bg-storefront-selected text-storefront-selected-foreground' : 'border-storefront-border bg-storefront-surface text-storefront-text'"
        >
          <input
            type="radio"
            name="special-equipment-condition"
            class="sr-only storefront-control"
            :value="option.value"
            :checked="query.condition === option.value"
            @change="changeCondition(option.value)"
          >
          <span class="min-w-0 leading-snug min-[1280px]:whitespace-nowrap">{{ option.label }}</span>
          <span v-if="option.count !== null" class="shrink-0 text-xs tabular-nums text-storefront-text-muted">{{ option.count }}</span>
        </label>
      </div>
    </fieldset>

    <fieldset class="flex flex-col gap-3">
      <legend class="text-sm font-semibold text-storefront-label">Стоимость, ₽</legend>
      <RangeInputs
        :min-value="localPriceMin"
        :max-value="localPriceMax"
        min-label="Минимальная стоимость"
        max-label="Максимальная стоимость"
        @update:min-value="localPriceMin = $event"
        @update:max-value="localPriceMax = $event"
        @blur="applyRanges"
      />
      <p v-if="facets.price.min !== null && facets.price.max !== null" class="text-xs text-storefront-text-muted">
        В каталоге: {{ formatMoneyCompact(facets.price.min) }} — {{ formatMoneyCompact(facets.price.max) }}
      </p>
      <p v-if="priceError" class="text-sm font-medium text-storefront-error-text" role="alert">{{ priceError }}</p>
    </fieldset>

    <fieldset
      v-if="query.condition === 'used' && facets.usage.metric"
      class="flex flex-col gap-3"
    >
      <legend class="text-sm font-semibold text-storefront-label">{{ usageLabel }}</legend>
      <RangeInputs
        :min-value="localUsageMin"
        :max-value="localUsageMax"
        :min-label="`Минимум: ${usageLabel}`"
        :max-label="`Максимум: ${usageLabel}`"
        integer
        @update:min-value="localUsageMin = $event"
        @update:max-value="localUsageMax = $event"
        @blur="applyRanges"
      />
      <p v-if="usageError" class="text-sm font-medium text-storefront-error-text" role="alert">{{ usageError }}</p>
    </fieldset>

    <SpecialEquipmentAttributeFilterGroups
      :groups="facets.attribute_groups"
      :dynamic-filters="dynamicFilters"
      :search-drafts="searchDrafts"
      :loading="attributesLoading"
      @toggle-option="toggleAttributeOption"
      @update-range="updateRange"
      @update-search="updateTextSearch"
    />

    <button
      v-if="hasActiveFilters"
      type="button"
      class="min-h-11 rounded-lg border border-storefront-border px-4 text-sm font-semibold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
      @click="emit('clear')"
    >
      Сбросить фильтры
    </button>
  </form>
</template>

<script setup lang="ts">
import { isUuid, type UUID } from '~/types/ids'
import {
  hasExplicitSpecialEquipmentAvailability,
  serializeDynamicFilters,
  toggleSpecialEquipmentAvailability,
} from '../composables/catalogQuery'
import type {
  SpecialEquipmentCatalogQuery,
  SpecialEquipmentCondition,
  SpecialEquipmentDynamicFilters,
  SpecialEquipmentFacets,
} from '../types'
import { specialEquipmentWarehouseFacetLabel } from '../warehouseFacetLabel'
import RangeInputs from './RangeInputs.vue'
import SpecialEquipmentAttributeFilterGroups from './SpecialEquipmentAttributeFilterGroups.vue'
import SpecialEquipmentFacetDialog from './SpecialEquipmentFacetDialog.vue'

const props = defineProps<{
  facets: SpecialEquipmentFacets
  query: SpecialEquipmentCatalogQuery
  dynamicFilters: SpecialEquipmentDynamicFilters
  attributesLoading?: boolean
}>()

const emit = defineEmits<{
  update: [patch: Partial<SpecialEquipmentCatalogQuery>]
  clear: []
}>()

const { formatMoneyCompact } = useFormatPrice()
const localPriceMin = ref(props.query.priceMin)
const localPriceMax = ref(props.query.priceMax)
const localUsageMin = ref(props.query.usageMin)
const localUsageMax = ref(props.query.usageMax)
const localMinInStock = ref(props.query.minInStock)
const priceError = ref('')
const usageError = ref('')
const stockError = ref('')

const conditionOptions = computed<Array<{
  value: SpecialEquipmentCondition
  label: string
  count: number | null
}>>(() => [
  { value: '', label: 'Все', count: null },
  { value: 'new', label: 'Новое', count: props.facets.conditions.new },
  { value: 'used', label: 'С пробегом', count: props.facets.conditions.used },
])

const usageLabel = computed(() =>
  props.facets.usage.metric === 'mileage_km' ? 'Пробег, км' : 'Моточасы',
)

const availableModels = computed(() => {
  const selectedMarks = new Set(props.query.markIds)
  if (selectedMarks.size === 0) return []
  return props.facets.models.filter(model => selectedMarks.has(model.mark_id))
})

const availableModifications = computed(() => {
  if (props.query.markIds.length === 0) return []
  const selectedModels = new Set(props.query.modelIds)
  if (selectedModels.size === 0) return []
  return props.facets.modifications.filter(modification => selectedModels.has(modification.model_id))
})

const availableTrims = computed(() => {
  if (props.query.modificationIds.length === 0) return []
  const selectedModifications = new Set(props.query.modificationIds)
  return props.facets.trims.filter(trim => selectedModifications.has(trim.modification_id))
})

const availableWarehouses = computed(() => props.query.cityId
  ? (props.facets.warehouses ?? []).filter(warehouse => warehouse.city_id === props.query.cityId)
  : props.facets.warehouses ?? [])

watch(() => props.query.priceMin, value => { localPriceMin.value = value })
watch(() => props.query.priceMax, value => { localPriceMax.value = value })
watch(() => props.query.usageMin, value => { localUsageMin.value = value })
watch(() => props.query.usageMax, value => { localUsageMax.value = value })
watch(() => props.query.minInStock, value => {
  localMinInStock.value = value
  stockError.value = ''
})

const hasActiveFilters = computed(() =>
  props.query.markIds.length > 0
  || props.query.modelIds.length > 0
  || props.query.modificationIds.length > 0
  || props.query.trimIds.length > 0
  || (props.query.superstructureIds?.length ?? 0) > 0
  || props.query.bodyColorIds.length > 0
  || props.query.interiorColorIds.length > 0
  || hasExplicitSpecialEquipmentAvailability(props.query.availability)
  || Boolean(props.query.condition)
  || Boolean(props.query.priceMin)
  || Boolean(props.query.priceMax)
  || Boolean(props.query.usageMin)
  || Boolean(props.query.usageMax)
  || Boolean(props.query.cityId)
  || Boolean(props.query.warehouseId)
  || Boolean(props.query.minInStock)
  || Boolean(props.query.descriptionInclude)
  || Boolean(props.query.descriptionExclude)
  || props.query.attributeTokens.length > 0,
)

const normalizeDecimalInput = (value: string): string => {
  const normalized = value.trim().replace(',', '.')
  return /^\d+(?:\.\d{0,4})?$/.test(normalized) ? normalized : ''
}

const normalizeIntegerInput = (value: string): string => {
  const normalized = value.trim()
  return /^\d+$/.test(normalized) ? normalized : ''
}

const validateRange = (min: string, max: string, message: string): string =>
  min && max && Number(min) > Number(max) ? message : ''

const applyRanges = () => {
  const priceMin = normalizeDecimalInput(localPriceMin.value)
  const priceMax = normalizeDecimalInput(localPriceMax.value)
  const usageMin = normalizeIntegerInput(localUsageMin.value)
  const usageMax = normalizeIntegerInput(localUsageMax.value)
  localPriceMin.value = priceMin
  localPriceMax.value = priceMax
  localUsageMin.value = usageMin
  localUsageMax.value = usageMax
  priceError.value = validateRange(priceMin, priceMax, 'Минимальная стоимость не может быть больше максимальной.')
  usageError.value = validateRange(usageMin, usageMax, `Минимальное значение поля «${usageLabel.value}» не может быть больше максимального.`)
  if (priceError.value || usageError.value) return
  if (
    priceMin === props.query.priceMin
    && priceMax === props.query.priceMax
    && usageMin === props.query.usageMin
    && usageMax === props.query.usageMax
  ) return
  emit('update', { priceMin, priceMax, usageMin, usageMax, page: 1 })
}

const changeCondition = (condition: SpecialEquipmentCondition) => {
  if (condition !== 'used') {
    localUsageMin.value = ''
    localUsageMax.value = ''
  }
  emit('update', {
    condition,
    usageMin: condition === 'used' ? props.query.usageMin : '',
    usageMax: condition === 'used' ? props.query.usageMax : '',
    page: 1,
  })
}

const selectedUuidValue = (event: Event): UUID | '' => {
  const input = event.currentTarget
  const value = input instanceof HTMLSelectElement ? input.value : ''
  return isUuid(value) ? value : ''
}

const changeCity = (event: Event) => {
  const cityId = selectedUuidValue(event)
  const warehouseStillAvailable = (props.facets.warehouses ?? []).some(warehouse =>
    warehouse.id === props.query.warehouseId && (!cityId || warehouse.city_id === cityId),
  )
  emit('update', {
    cityId,
    warehouseId: warehouseStillAvailable ? props.query.warehouseId : '',
    page: 1,
  })
}

const changeWarehouse = (event: Event) =>
  emit('update', { warehouseId: selectedUuidValue(event), page: 1 })

const applyMinInStock = (event: Event) => {
  const input = event.currentTarget
  if (!(input instanceof HTMLInputElement)) return
  const minInStock = normalizeIntegerInput(input.value)
  localMinInStock.value = minInStock
  stockError.value = minInStock && Number(minInStock) > 100_000
    ? 'Минимальный остаток не может быть больше 100 000.'
    : ''
  if (stockError.value) return
  if (minInStock !== props.query.minInStock) emit('update', { minInStock, page: 1 })
}

const hasSameUuidSelection = (left: UUID[], right: UUID[]): boolean =>
  left.length === right.length && left.every(id => right.includes(id))

const applyMarks = (markIds: UUID[]) => {
  const selectedMarkIds = [...new Set(markIds)]
  if (hasSameUuidSelection(props.query.markIds, selectedMarkIds)) return
  emit('update', {
    markIds: selectedMarkIds,
    modelIds: [],
    modificationIds: [],
    trimIds: [],
    page: 1,
  })
}

const applyModels = (modelIds: UUID[]) => {
  const selectedModelIds = [...new Set(modelIds)]
  if (hasSameUuidSelection(props.query.modelIds, selectedModelIds)) return
  emit('update', {
    modelIds: selectedModelIds,
    modificationIds: [],
    trimIds: [],
    page: 1,
  })
}

const applyModifications = (modificationIds: UUID[]) => {
  const selectedModificationIds = [...new Set(modificationIds)]
  if (hasSameUuidSelection(props.query.modificationIds, selectedModificationIds)) return
  emit('update', { modificationIds: selectedModificationIds, trimIds: [], page: 1 })
}

const applyTrims = (trimIds: UUID[]) =>
  emit('update', { trimIds: [...trimIds], page: 1 })

const applySuperstructures = (superstructureIds: UUID[]) =>
  emit('update', { superstructureIds: [...superstructureIds], page: 1 })

const applyBodyColors = (bodyColorIds: UUID[]) =>
  emit('update', { bodyColorIds: [...bodyColorIds], page: 1 })

const applyInteriorColors = (interiorColorIds: UUID[]) =>
  emit('update', { interiorColorIds: [...interiorColorIds], page: 1 })

const updateDescription = (
  field: 'descriptionInclude' | 'descriptionExclude',
  event: Event,
) => {
  const input = event.target
  if (!(input instanceof HTMLInputElement)) return
  emit('update', { [field]: input.value.trim().slice(0, 500), page: 1 })
}

const availabilityOptions = computed<Array<{
  value: 'available' | 'on_order'
  label: string
  count: number
}>>(() => [
  { value: 'available', label: 'В наличии', count: props.facets.availability.available },
  { value: 'on_order', label: 'Под заказ', count: props.facets.availability.on_order },
])
const toggleAvailability = (availability: 'available' | 'on_order') => {
  emit('update', {
    availability: toggleSpecialEquipmentAvailability(props.query.availability, availability),
    page: 1,
  })
}

const cloneDynamicFilters = (): SpecialEquipmentDynamicFilters =>
  Object.fromEntries(Object.entries(props.dynamicFilters).map(([attributeId, value]) => [
    attributeId,
    { values: [...value.values], min: value.min, max: value.max, search: value.search ?? '' },
  ]))

const toggleAttributeOption = (attributeId: UUID, value: string) => {
  const filters = cloneDynamicFilters()
  const current = filters[attributeId] ?? { values: [], min: '', max: '', search: '' }
  const values = new Set(current.values)
  if (values.has(value)) values.delete(value)
  else values.add(value)
  filters[attributeId] = { ...current, values: [...values] }
  emit('update', { attributeTokens: serializeDynamicFilters(filters), page: 1 })
}

const updateRange = (attributeId: UUID, side: 'min' | 'max', event: Event) => {
  const input = event.currentTarget
  if (!(input instanceof HTMLInputElement)) return
  const filters = cloneDynamicFilters()
  const current = filters[attributeId] ?? { values: [], min: '', max: '', search: '' }
  filters[attributeId] = { ...current, [side]: normalizeDecimalInput(input.value) }
  emit('update', { attributeTokens: serializeDynamicFilters(filters), page: 1 })
}

const searchDrafts = reactive<Partial<Record<UUID, string>>>({})
const searchTimers = new Map<UUID, ReturnType<typeof setTimeout>>()
watch(
  () => props.dynamicFilters,
  filters => {
    for (const attributeId of Object.keys(searchDrafts)) {
      if (!(attributeId in filters)) delete searchDrafts[attributeId as UUID]
    }
    for (const [attributeId, filter] of Object.entries(filters)) {
      searchDrafts[attributeId] = filter.search
    }
  },
  { deep: true, immediate: true },
)
const updateTextSearch = (attributeId: UUID, event: Event) => {
  const input = event.currentTarget
  if (!(input instanceof HTMLInputElement)) return
  searchDrafts[attributeId] = input.value
  const existingTimer = searchTimers.get(attributeId)
  if (existingTimer) clearTimeout(existingTimer)
  searchTimers.set(attributeId, setTimeout(() => {
    const filters = cloneDynamicFilters()
    const current = filters[attributeId] ?? { values: [], min: '', max: '', search: '' }
    filters[attributeId] = { ...current, search: (searchDrafts[attributeId] ?? '').trim().slice(0, 200) }
    emit('update', { attributeTokens: serializeDynamicFilters(filters), page: 1 })
    searchTimers.delete(attributeId)
  }, 350))
}
onBeforeUnmount(() => {
  for (const timer of searchTimers.values()) clearTimeout(timer)
})
</script>
