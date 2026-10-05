<template>
  <section data-storefront-block="equipment.catalog"
    :id="resultsId"
    class="bg-storefront-background text-storefront-text"
    :aria-busy="catalogPending || facetsPending"
  >
    <div class="mx-auto max-w-7xl py-8">
      <form data-storefront-block="equipment.filters" class="mb-6 grid grid-cols-[minmax(0,1fr)_auto] gap-3 text-storefront-text" role="search" @submit.prevent="submitSearch">
        <label class="relative min-w-0">
          <span class="sr-only">Поиск по каталогу транспортных средств и специальной техники</span>
          <MagnifyingGlassIcon class="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-storefront-icon-muted" aria-hidden="true" />
          <input
            v-model="searchInput"
            type="search"
            autocomplete="off"
            placeholder="Название, марка, модель или код"
            class="h-12 w-full rounded-lg border border-storefront-border bg-storefront-surface pl-11 pr-4 text-base text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
          >
        </label>
        <button
          type="submit"
          class="block min-h-12 shrink-0 rounded-lg bg-storefront-primary px-6 text-sm font-bold text-storefront-primary-foreground hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-primary"
        >
          Найти технику
        </button>
      </form>

      <div data-storefront-block="equipment.filters" class="mb-4 grid grid-cols-2 gap-2 text-storefront-text">
        <button
          ref="filterTrigger"
          type="button"
          class="flex min-h-12 min-w-0 items-center justify-center gap-2 rounded-lg border border-storefront-border bg-storefront-surface px-3 text-sm font-bold text-storefront-text hover:border-storefront-secondary-hover-border hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
          :aria-expanded="filtersOpen"
          aria-controls="special-equipment-all-filters"
          @click="openFilters"
        >
          <AdjustmentsHorizontalIcon class="h-5 w-5 shrink-0 text-storefront-icon" aria-hidden="true" />
          <span>Все фильтры</span>
          <span v-if="activeFilterCount" class="rounded-full bg-storefront-selected px-2 py-0.5 text-xs text-storefront-link">
            {{ activeFilterCount }}
          </span>
        </button>
        <SortSelect :value="catalogQuery.sort" :usage-metric="usageMetric" @change="changeSort" />
      </div>

      <section :aria-labelledby="resultsHeadingId" aria-live="polite" :aria-busy="catalogPending">
        <div class="flex flex-row items-end justify-between gap-4">
            <div>
              <p v-if="resultsContext" class="mb-1 text-sm text-storefront-text-muted">
                {{ resultsContext }}
              </p>
              <h2 :id="resultsHeadingId" class="text-2xl font-bold tracking-tight text-storefront-title">
                {{ resultsTitle }}
              </h2>
              <p class="mt-1 text-sm text-storefront-text-muted">
                <template v-if="catalogPending">Обновляем результаты…</template>
                <template v-else>{{ resultSummary }}</template>
              </p>
            </div>
          </div>

          <div v-if="activeFilterChips.length" data-storefront-block="equipment.filters" class="mt-4 flex flex-wrap gap-2 text-storefront-text" aria-label="Активные фильтры">
            <button
              v-for="chip in activeFilterChips"
              :key="chip.key"
              type="button"
              class="inline-flex min-h-11 min-w-11 items-center gap-1.5 rounded-full bg-storefront-selected px-3 text-sm font-semibold text-storefront-link hover:bg-storefront-selected focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
              :aria-label="`Удалить фильтр ${chip.label}`"
              @click="removeActiveFilter(chip)"
            >
              <span class="max-w-64 truncate">{{ chip.label }}</span>
              <XMarkIcon class="h-4 w-4 text-storefront-icon" aria-hidden="true" />
            </button>
          </div>

          <div v-if="catalogPending" class="mt-6 grid grid-cols-1 gap-5" aria-label="Загрузка объявлений">
            <div v-for="index in 6" :key="index" class="grid grid-cols-[minmax(17rem,36%)_minmax(0,1fr)] overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface">
              <div class="aspect-[4/3] animate-pulse bg-storefront-skeleton motion-reduce:animate-none" />
              <div class="grid min-w-0 gap-3 p-5">
                <span class="h-4 w-1/3 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
                <span class="h-6 w-4/5 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
                <span class="mt-6 h-11 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
              </div>
            </div>
          </div>

          <div v-else-if="catalogError" class="mt-6 rounded-xl border border-storefront-error-border bg-storefront-error p-6 text-storefront-error-text" role="alert">
            <ExclamationTriangleIcon class="h-8 w-8 text-storefront-icon" aria-hidden="true" />
            <h3 class="mt-3 text-lg font-bold">Не удалось загрузить каталог</h3>
            <p class="mt-1 text-sm leading-relaxed">Проверьте подключение и попробуйте ещё раз.</p>
            <button type="button" class="mt-4 min-h-11 rounded-lg border border-storefront-error-border bg-storefront-surface px-4 text-sm font-bold hover:bg-storefront-error-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-destructive" @click="refreshCatalog()">
              Повторить
            </button>
          </div>

          <div v-else-if="products.length === 0" class="mt-6 rounded-xl border border-storefront-border bg-storefront-surface px-6 py-14 text-center">
            <MagnifyingGlassIcon class="mx-auto h-12 w-12 text-storefront-icon-muted" aria-hidden="true" />
            <h3 class="mt-4 text-xl font-bold text-storefront-title">Ничего не найдено</h3>
            <p class="mx-auto mt-2 max-w-md text-sm leading-relaxed text-storefront-text-muted">
              Измените параметры поиска или сбросьте фильтры.
            </p>
            <button type="button" class="mt-5 min-h-11 rounded-lg bg-storefront-primary px-5 text-sm font-bold text-storefront-primary-foreground hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-primary" @click="resetSearchAndFilters">
              Показать всю технику
            </button>
          </div>

          <template v-else>
            <div class="mt-6 grid grid-cols-1 gap-5">
              <SpecialEquipmentProductCard
                v-for="product in products"
                :key="product.id"
                :product="product"
                :public-route="publicRoute"
                :category-path="categoryPath"
                :is-favorite="commerce.isFavorite(product.id)"
                :is-in-cart="commerce.isInCart(product.id)"
                :favorite-pending="commerce.isFavoritePending(product.id)"
                :cart-pending="commerce.isCartPending(product.id)"
                @toggle-favorite="commerce.toggleFavorite($event, product.capabilities.can_favorite)"
                @toggle-cart="commerce.toggleCart($event, product.capabilities.can_add_to_cart, product)"
              />
            </div>
            <SpecialEquipmentPagination class="mt-9" :page="pagination.page" :pages="pagination.pages" @change="changePage" />
          </template>
      </section>
    </div>

    <Teleport to="body">
      <Transition name="special-equipment-filter-backdrop">
        <div
          v-if="filtersOpen"
          data-storefront-block="equipment.filters.dialog" class="fixed inset-0 z-[70] bg-storefront-overlay/45 backdrop-blur-[1px] text-storefront-text"
          aria-hidden="true"
          @click="closeFilters"
        />
      </Transition>
      <Transition name="special-equipment-filter-drawer">
        <aside
          v-if="filtersOpen"
          id="special-equipment-all-filters"
          data-storefront-block="equipment.filters.dialog"
          ref="filterDrawer"
          class="special-equipment-filter-drawer fixed inset-y-0 right-0 z-[80] flex w-full max-w-[38rem] flex-col overflow-hidden bg-storefront-surface storefront-shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="special-equipment-all-filters-title"
          @keydown="handleFilterKeydown"
        >
          <header class="flex min-h-[4.25rem] shrink-0 items-center justify-between gap-3 border-b border-storefront-border px-5">
            <h2 id="special-equipment-all-filters-title" class="text-lg font-bold text-storefront-title">Все фильтры</h2>
            <button
              ref="filterCloseButton"
              type="button"
              class="grid min-h-11 min-w-11 place-items-center rounded-lg border border-storefront-border text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
              aria-label="Закрыть фильтры"
              @click="closeFilters"
            >
              <XMarkIcon class="h-5 w-5 text-storefront-icon" aria-hidden="true" />
            </button>
          </header>
          <div class="special-equipment-filter-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-5">
            <div v-if="facetsPending && facets.attribute_groups.length === 0" class="my-4 grid gap-4" aria-label="Загрузка фильтров">
              <span v-for="index in 5" :key="index" class="h-16 animate-pulse rounded-lg bg-storefront-skeleton motion-reduce:animate-none" />
            </div>
            <div v-else-if="facetsError" class="my-4 rounded-lg bg-storefront-error p-4 text-sm text-storefront-error-text" role="alert">
              <p>Не удалось загрузить фильтры.</p>
              <button
                type="button"
                class="mt-2 min-h-11 min-w-11 font-bold underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
                @click="refreshFacets()"
              >
                Повторить
              </button>
            </div>
            <SpecialEquipmentFilters
              v-else
              class="py-4"
              :facets="facets"
              :query="catalogQuery"
              :dynamic-filters="dynamicFilters"
              :attributes-loading="facetsPending"
              @update="updateCatalogQuery"
              @clear="clearFilters"
            />
          </div>
          <footer class="grid shrink-0 grid-cols-2 gap-2 border-t border-storefront-border bg-storefront-surface p-5">
            <button type="button" class="min-h-11 rounded-lg border border-storefront-border px-3 text-sm font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary" @click="clearFilters">Сбросить</button>
            <button type="button" class="min-h-11 rounded-lg bg-storefront-primary px-3 text-sm font-bold text-storefront-primary-foreground hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-primary" @click="closeFilters">Показать объявления</button>
          </footer>
        </aside>
      </Transition>
    </Teleport>

    <AuthModal v-if="showAuthModal" @close="showAuthModal = false" @authenticated="handleAuthenticated" />
  </section>
</template>

<script setup lang="ts">
import { AdjustmentsHorizontalIcon, ExclamationTriangleIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import AuthModal from '~/features/auth/components/AuthModal.vue'
import { createSpecialEquipmentApi } from '../api/specialEquipmentApi'
import { specialEquipmentCatalogAsyncDataKeys } from '../catalogAsyncData'
import {
  catalogQueryForCategoryContext,
  hasExplicitSpecialEquipmentAvailability,
  hasSpecialEquipmentCategoryFilterContext,
  parseDynamicFilters,
  parseSpecialEquipmentCatalogQuery,
  pruneTrimSelection,
  resetSpecialEquipmentCategorySpecificFilters,
  serializeDynamicFilters,
  toSpecialEquipmentFacetsParams,
  toSpecialEquipmentProductsParams,
} from '../composables/catalogQuery'
import { useSpecialEquipmentCommerce } from '../composables/useSpecialEquipmentCommerce'
import { isSpecialEquipmentSortAvailable } from '../sortOptions'
import { createLatestResponseGuard } from '../latestResponse'
import type {
  SpecialEquipmentCatalogQuery,
  SpecialEquipmentDynamicFilters,
  SpecialEquipmentFacets,
  SpecialEquipmentFacetsResponse,
  SpecialEquipmentProductsResponse,
  SpecialEquipmentSort,
  SpecialEquipmentTrimFacet,
  SpecialEquipmentUsageMetric,
} from '../types'
import SpecialEquipmentFilters from './SpecialEquipmentFilters.vue'
import SpecialEquipmentPagination from './SpecialEquipmentPagination.vue'
import SpecialEquipmentProductCard from './SpecialEquipmentProductCard.vue'
import SortSelect from './SortSelect.vue'
import type { PublicRouteBuilder } from '~/utils/storefrontRoute'
import { useStorefront } from '~/features/storefront'

const props = withDefaults(defineProps<{
  categoryPath?: string[]
  usageMetric?: SpecialEquipmentUsageMetric | null
  queryState: SpecialEquipmentCatalogQuery
  resultsTitle?: string
  resultsContext?: string
  resultsId?: string
  scrollOnPageChange?: boolean
  publicRoute: PublicRouteBuilder
}>(), {
  categoryPath: () => [],
  usageMetric: null,
  resultsTitle: 'Вся техника',
  resultsContext: '',
  resultsId: 'special-equipment-results',
  scrollOnPageChange: true,
})
const emit = defineEmits<{
  'update:queryState': [value: SpecialEquipmentCatalogQuery]
}>()
const categoryPath = computed(() => props.categoryPath)
const asyncDataKeys = computed(() => specialEquipmentCatalogAsyncDataKeys(categoryPath.value))
const { apiPath } = useStorefront()
const api = createSpecialEquipmentApi(useRuntimeConfig(), apiPath)
const showAuthModal = ref(false)
const filtersOpen = ref(false)
const filterTrigger = ref<HTMLButtonElement | null>(null)
const filterDrawer = ref<HTMLElement | null>(null)
const filterCloseButton = ref<HTMLButtonElement | null>(null)
let previousBodyOverflow: string | null = null
const commerce = useSpecialEquipmentCommerce({
  onAuthRequired: () => { showAuthModal.value = true },
})

const catalogQuery = computed(() => props.queryState)
const implicitUsageMetric = ref<SpecialEquipmentUsageMetric | null>(null)
const implicitContextStatus = ref<'idle' | 'loading' | 'resolved' | 'missing'>('idle')
const implicitContextFingerprint = computed(() => JSON.stringify({
  path: categoryPath.value,
  modificationIds: catalogQuery.value.modificationIds,
}))
watch(implicitContextFingerprint, () => {
  implicitUsageMetric.value = null
  implicitContextStatus.value = categoryPath.value.length === 0
    && catalogQuery.value.modificationIds.length === 1
    ? 'loading'
    : 'idle'
}, { immediate: true })
const hasCategoryFilterContext = computed(() => hasSpecialEquipmentCategoryFilterContext(
  categoryPath.value,
  catalogQuery.value.modificationIds,
  implicitContextStatus.value === 'resolved' ? implicitUsageMetric.value : null,
))
const knownTrimFacets = useState<SpecialEquipmentTrimFacet[]>(
  `special-equipment-trim-ownership:${JSON.stringify([apiPath('/special-equipment'), categoryPath.value, props.resultsId])}`,
  () => [],
)
const trimOwnershipLookups = new Map<string, Promise<void>>()
const rememberTrimFacets = (trims: readonly SpecialEquipmentTrimFacet[]) => {
  const known = new Map(knownTrimFacets.value.map(trim => [trim.id, trim]))
  let changed = false
  for (const trim of trims) {
    if (known.get(trim.id)?.modification_id === trim.modification_id) continue
    known.set(trim.id, trim)
    changed = true
  }
  if (changed) knownTrimFacets.value = [...known.values()]
}
const ensureTrimOwnership = async (
  query: SpecialEquipmentCatalogQuery = catalogQuery.value,
  path: readonly string[] = categoryPath.value,
): Promise<void> => {
  if (query.modificationIds.length === 0 || query.trimIds.length === 0) return
  const knownIds = new Set(knownTrimFacets.value.map(trim => trim.id))
  if (query.trimIds.every(id => knownIds.has(id))) return

  const key = JSON.stringify(path)
  let lookup = trimOwnershipLookups.get(key)
  if (!lookup) {
    // Filtered facets omit foreign trims, so resolve ownership without narrowing filters.
    lookup = api.getFacets({
      category_path: path.length ? path.join('/') : undefined,
      availability: ['available', 'on_order'],
    }).then(response => rememberTrimFacets(response.trims)).catch(() => undefined)
    trimOwnershipLookups.set(key, lookup)
  }
  await lookup
}
await ensureTrimOwnership()
const requestQuery = computed<SpecialEquipmentCatalogQuery>(() =>
  catalogQueryForCategoryContext(
    pruneTrimSelection(catalogQuery.value, knownTrimFacets.value),
    hasCategoryFilterContext.value,
  ),
)
const searchInput = ref(catalogQuery.value.search)
watch(() => catalogQuery.value.search, value => { searchInput.value = value })
const usageMetric = computed(() => props.usageMetric
  ?? (hasCategoryFilterContext.value ? implicitUsageMetric.value : null))
watch(usageMetric, (metric) => {
  if (isSpecialEquipmentSortAvailable(catalogQuery.value.sort, metric)) return
  void updateCatalogQuery({ sort: 'published_desc', page: 1 })
})
const productsParams = computed(() =>
  toSpecialEquipmentProductsParams(requestQuery.value, categoryPath.value, usageMetric.value),
)
const facetsParams = computed(() =>
  toSpecialEquipmentFacetsParams(requestQuery.value, categoryPath.value, usageMetric.value),
)
const productsRequestFingerprint = computed(() => JSON.stringify({
  path: categoryPath.value,
  products: productsParams.value,
}))
const facetsRequestFingerprint = computed(() => JSON.stringify({
  path: categoryPath.value,
  facets: facetsParams.value,
}))
const productsResponseGuard = createLatestResponseGuard()
const facetsResponseGuard = createLatestResponseGuard()
const latestCatalogResult = shallowRef<SpecialEquipmentProductsResponse | null>(null)
const latestFacetsResult = shallowRef<SpecialEquipmentFacetsResponse | null>(null)

const {
  data: catalogResult,
  pending: catalogPending,
  error: catalogError,
  refresh: refreshCatalog,
} = useAsyncData(
  () => `${asyncDataKeys.value.products}:${productsRequestFingerprint.value}`,
  async () => {
    const query = requestQuery.value
    const path = [...categoryPath.value]
    const metric = usageMetric.value
    const response = await productsResponseGuard.run(async () => {
      await ensureTrimOwnership(query, path)
      return api.getProducts(toSpecialEquipmentProductsParams(
        pruneTrimSelection(query, knownTrimFacets.value), path, metric,
      ))
    })
    if (!response.isLatest) {
      return latestCatalogResult.value ?? response.value
    }
    latestCatalogResult.value = response.value
    return response.value
  },
  { dedupe: 'cancel' },
)

const {
  data: facetsResult,
  pending: facetsPending,
  error: facetsError,
  refresh: refreshFacets,
} = useAsyncData(
  () => `${asyncDataKeys.value.facets}:${facetsRequestFingerprint.value}`,
  async () => {
    const query = requestQuery.value
    const path = [...categoryPath.value]
    const metric = usageMetric.value
    const response = await facetsResponseGuard.run(async () => {
      await ensureTrimOwnership(query, path)
      return api.getFacets(toSpecialEquipmentFacetsParams(
        pruneTrimSelection(query, knownTrimFacets.value), path, metric,
      ))
    })
    if (!response.isLatest) {
      return latestFacetsResult.value ?? response.value
    }
    latestFacetsResult.value = response.value
    rememberTrimFacets(response.value.trims)
    return response.value
  },
  { dedupe: 'cancel' },
)
watch(facetsResult, (response) => {
  if (!response) return
  latestFacetsResult.value = response
  rememberTrimFacets(response.trims)
  if (categoryPath.value.length > 0 || catalogQuery.value.modificationIds.length !== 1) return
  implicitUsageMetric.value = response.usage.metric
  implicitContextStatus.value = response.usage.metric === null ? 'missing' : 'resolved'
}, { immediate: true })
watch(
  () => [categoryPath.value, catalogQuery.value.modificationIds, catalogQuery.value.trimIds] as const,
  () => { void ensureTrimOwnership() },
  { immediate: true },
)

const products = computed(() => catalogResult.value?.items ?? [])
const pagination = computed(() => catalogResult.value?.pagination ?? {
  page: catalogQuery.value.page,
  page_size: 24,
  total: 0,
  pages: 0,
})
const emptyFacets = computed<SpecialEquipmentFacets>(() => ({
  marks: [],
  models: [],
  modifications: [],
  trims: [],
  body_colors: [],
  interior_colors: [],
  availability: { available: 0, on_order: 0 },
  conditions: { new: 0, used: 0 },
  price: { min: null, max: null },
  usage: { metric: usageMetric.value, min: null, max: null },
  cities: [],
  warehouses: [],
  attribute_groups: [],
}))
const facets = computed<SpecialEquipmentFacets>(() => ({
  ...emptyFacets.value,
  ...(facetsResult.value ?? latestFacetsResult.value ?? {}),
  models: facetsResult.value?.models ?? latestFacetsResult.value?.models ?? [],
  modifications: facetsResult.value?.modifications ?? latestFacetsResult.value?.modifications ?? [],
  trims: facetsResult.value?.trims ?? latestFacetsResult.value?.trims ?? [],
  body_colors: facetsResult.value?.body_colors ?? latestFacetsResult.value?.body_colors ?? [],
  interior_colors: facetsResult.value?.interior_colors ?? latestFacetsResult.value?.interior_colors ?? [],
  availability: facetsResult.value?.availability ?? latestFacetsResult.value?.availability ?? emptyFacets.value.availability,
  cities: facetsResult.value?.cities ?? latestFacetsResult.value?.cities ?? [],
  warehouses: facetsResult.value?.warehouses ?? latestFacetsResult.value?.warehouses ?? [],
  attribute_groups: hasCategoryFilterContext.value
    ? facetsResult.value?.attribute_groups ?? latestFacetsResult.value?.attribute_groups ?? []
    : [],
}))
const dynamicFilters = computed(() => parseDynamicFilters(requestQuery.value.attributeTokens))
const resultsHeadingId = `${props.resultsId}-title`

interface ActiveFilterChip {
  key: string
  label: string
  kind: 'search' | 'descriptionInclude' | 'descriptionExclude' | 'mark' | 'model' | 'modification' | 'trim' | 'superstructure' | 'bodyColor' | 'interiorColor' | 'availability' | 'condition' | 'priceMin' | 'priceMax' | 'usage' | 'city' | 'warehouse' | 'minInStock' | 'attribute'
  value?: string
}

const activeFilterCount = computed(() =>
  requestQuery.value.markIds.length
  + requestQuery.value.modelIds.length
  + requestQuery.value.modificationIds.length
  + requestQuery.value.trimIds.length
  + (requestQuery.value.superstructureIds?.length ?? 0)
  + requestQuery.value.bodyColorIds.length
  + requestQuery.value.interiorColorIds.length
  + (hasExplicitSpecialEquipmentAvailability(requestQuery.value.availability) ? 1 : 0)
  + (requestQuery.value.condition ? 1 : 0)
  + (requestQuery.value.priceMin ? 1 : 0)
  + (requestQuery.value.priceMax ? 1 : 0)
  + (requestQuery.value.usageMin || requestQuery.value.usageMax ? 1 : 0)
  + (requestQuery.value.cityId ? 1 : 0)
  + (requestQuery.value.warehouseId ? 1 : 0)
  + (requestQuery.value.minInStock ? 1 : 0)
  + (requestQuery.value.descriptionInclude ? 1 : 0)
  + (requestQuery.value.descriptionExclude ? 1 : 0)
  + requestQuery.value.attributeTokens.length,
)

const allFacetAttributes = computed(() => facets.value.attribute_groups.flatMap(group => group.attributes))
const activeFilterChips = computed<ActiveFilterChip[]>(() => {
  const chips: ActiveFilterChip[] = []
  if (requestQuery.value.search) chips.push({ key: 'search', label: `Поиск: ${requestQuery.value.search}`, kind: 'search' })
  if (requestQuery.value.descriptionInclude) {
    chips.push({
      key: 'description:include',
      label: `В описании: ${requestQuery.value.descriptionInclude}`,
      kind: 'descriptionInclude',
    })
  }
  if (requestQuery.value.descriptionExclude) {
    chips.push({
      key: 'description:exclude',
      label: `Исключено из описания: ${requestQuery.value.descriptionExclude}`,
      kind: 'descriptionExclude',
    })
  }
  for (const markId of requestQuery.value.markIds) {
    chips.push({
      key: `mark:${markId}`,
      label: facets.value.marks.find(item => item.id === markId)?.name ?? 'Марка',
      kind: 'mark',
      value: markId,
    })
  }
  for (const modelId of requestQuery.value.modelIds) {
    chips.push({
      key: `model:${modelId}`,
      label: facets.value.models.find(item => item.id === modelId)?.name ?? 'Модель',
      kind: 'model',
      value: modelId,
    })
  }
  for (const modificationId of requestQuery.value.modificationIds) {
    chips.push({
      key: `modification:${modificationId}`,
      label: facets.value.modifications.find(item => item.id === modificationId)?.name ?? 'Модификация',
      kind: 'modification',
      value: modificationId,
    })
  }
  for (const trimId of requestQuery.value.trimIds) {
    chips.push({
      key: `trim:${trimId}`,
      label: `Комплектация: ${facets.value.trims.find(item => item.id === trimId)?.name ?? 'комплектация'}`,
      kind: 'trim',
      value: trimId,
    })
  }
  for (const superstructureId of requestQuery.value.superstructureIds ?? []) {
    chips.push({
      key: `superstructure:${superstructureId}`,
      label: `Надстройка: ${facets.value.superstructures?.find(item => item.id === superstructureId)?.name ?? 'надстройка'}`,
      kind: 'superstructure',
      value: superstructureId,
    })
  }
  for (const colorId of requestQuery.value.bodyColorIds) {
    chips.push({
      key: `body-color:${colorId}`,
      label: `Цвет кузова: ${facets.value.body_colors.find(item => item.id === colorId)?.name ?? 'цвет'}`,
      kind: 'bodyColor',
      value: colorId,
    })
  }
  for (const colorId of requestQuery.value.interiorColorIds) {
    chips.push({
      key: `interior-color:${colorId}`,
      label: `Цвет салона: ${facets.value.interior_colors.find(item => item.id === colorId)?.name ?? 'цвет'}`,
      kind: 'interiorColor',
      value: colorId,
    })
  }
  if (hasExplicitSpecialEquipmentAvailability(requestQuery.value.availability)) {
    for (const availability of requestQuery.value.availability) {
      chips.push({
        key: `availability:${availability}`,
        label: availability === 'on_order' ? 'Под заказ' : 'В наличии',
        kind: 'availability',
        value: availability,
      })
    }
  }
  if (requestQuery.value.condition) {
    chips.push({
      key: 'condition',
      label: requestQuery.value.condition === 'used' ? 'С пробегом' : 'Новое',
      kind: 'condition',
    })
  }
  if (requestQuery.value.priceMin) chips.push({ key: 'price:min', label: `Цена от ${requestQuery.value.priceMin} ₽`, kind: 'priceMin' })
  if (requestQuery.value.priceMax) chips.push({ key: 'price:max', label: `Цена до ${requestQuery.value.priceMax} ₽`, kind: 'priceMax' })
  if (requestQuery.value.usageMin || requestQuery.value.usageMax) {
    const label = usageMetric.value === 'mileage_km' ? 'Пробег' : 'Моточасы'
    chips.push({ key: 'usage', label: `${label}: ${requestQuery.value.usageMin || '0'}—${requestQuery.value.usageMax || '∞'}`, kind: 'usage' })
  }
  if (requestQuery.value.cityId) chips.push({
    key: 'city',
    label: `Город: ${(facets.value.cities ?? []).find(city => city.id === requestQuery.value.cityId)?.name ?? 'город'}`,
    kind: 'city',
  })
  if (requestQuery.value.warehouseId) chips.push({ key: 'warehouse', label: 'Склад', kind: 'warehouse' })
  if (requestQuery.value.minInStock) chips.push({ key: 'min-in-stock', label: `Минимум на складе: ${requestQuery.value.minInStock}`, kind: 'minInStock' })
  for (const [attributeId, filter] of Object.entries(dynamicFilters.value)) {
    const attribute = allFacetAttributes.value.find(item => item.id === attributeId)
    const selectedLabels = filter.values.map(value =>
      attribute?.options.find(option => option.value === value)?.label ?? value,
    )
    const range = [filter.min ? `от ${filter.min}` : '', filter.max ? `до ${filter.max}` : ''].filter(Boolean).join(' ')
    chips.push({
      key: `attribute:${attributeId}`,
      label: attribute?.data_type === 'boolean' && filter.values.includes('true')
        ? attribute.name
        : `${attribute?.name ?? 'Характеристика'}: ${selectedLabels.join(', ') || range || filter.search}`,
      kind: 'attribute',
      value: attributeId,
    })
  }
  return chips
})

const resultSummary = computed(() => {
  const total = pagination.value.total
  return total ? `Найдено объявлений: ${new Intl.NumberFormat('ru-RU').format(total)}` : 'Нет подходящих объявлений'
})

const updateCatalogQuery = (patch: Partial<SpecialEquipmentCatalogQuery>) => {
  const next = { ...catalogQuery.value, ...patch }
  if (next.condition !== 'used') {
    next.usageMin = ''
    next.usageMax = ''
  }
  if (categoryPath.value.length === 0 && next.modificationIds.length !== 1) {
    next.attributeTokens = []
    next.usageMin = ''
    next.usageMax = ''
  }
  emit('update:queryState', pruneTrimSelection(next, knownTrimFacets.value))
}
watch(
  () => [catalogQuery.value.modificationIds, catalogQuery.value.trimIds, knownTrimFacets.value] as const,
  () => {
    const cleaned = pruneTrimSelection(catalogQuery.value, knownTrimFacets.value)
    if (cleaned !== catalogQuery.value) emit('update:queryState', cleaned)
  },
  { immediate: true },
)
watch(implicitContextStatus, (status) => {
  if (status !== 'missing') return
  const cleaned = resetSpecialEquipmentCategorySpecificFilters(catalogQuery.value)
  if (
    cleaned.attributeTokens.length === catalogQuery.value.attributeTokens.length
    && cleaned.usageMin === catalogQuery.value.usageMin
    && cleaned.usageMax === catalogQuery.value.usageMax
  ) return
  emit('update:queryState', cleaned)
}, { immediate: true })
watch(
  () => [categoryPath.value.length, catalogQuery.value.modificationIds.length] as const,
  ([pathLength, modificationCount]) => {
    if (pathLength > 0 || modificationCount === 1) return
    const cleaned = resetSpecialEquipmentCategorySpecificFilters(catalogQuery.value)
    if (
      cleaned.attributeTokens.length === catalogQuery.value.attributeTokens.length
      && cleaned.usageMin === catalogQuery.value.usageMin
      && cleaned.usageMax === catalogQuery.value.usageMax
    ) return
    emit('update:queryState', cleaned)
  },
  { immediate: true },
)
const clearFilters = () => updateCatalogQuery({
  markIds: [],
  modelIds: [],
  modificationIds: [],
  trimIds: [],
  superstructureIds: [],
  bodyColorIds: [],
  interiorColorIds: [],
  cityId: '',
  warehouseId: '',
  minInStock: '',
  availability: ['available', 'on_order'],
  condition: '',
  priceMin: '',
  priceMax: '',
  usageMin: '',
  usageMax: '',
  descriptionInclude: '',
  descriptionExclude: '',
  attributeTokens: [],
  page: 1,
})
const resetSearchAndFilters = () => {
  searchInput.value = ''
  emit('update:queryState', parseSpecialEquipmentCatalogQuery({}))
}
const removeActiveFilter = async (chip: ActiveFilterChip) => {
  if (chip.kind === 'search') {
    searchInput.value = ''
    updateCatalogQuery({ search: '', page: 1 })
  } else if (chip.kind === 'descriptionInclude') {
    updateCatalogQuery({ descriptionInclude: '', page: 1 })
  } else if (chip.kind === 'descriptionExclude') {
    updateCatalogQuery({ descriptionExclude: '', page: 1 })
  } else if (chip.kind === 'mark' && chip.value) {
    const markIds = catalogQuery.value.markIds.filter(id => id !== chip.value)
    const modelIds = markIds.length === 0
      ? []
      : catalogQuery.value.modelIds.filter(modelId => {
          const model = facets.value.models.find(item => item.id === modelId)
          return !model || markIds.includes(model.mark_id)
        })
    const modificationIds = modelIds.length === 0
      ? []
      : catalogQuery.value.modificationIds.filter(modificationId => {
          const modification = facets.value.modifications.find(item => item.id === modificationId)
          return !modification || modelIds.includes(modification.model_id)
        })
    updateCatalogQuery({ markIds, modelIds, modificationIds, page: 1 })
  } else if (chip.kind === 'model' && chip.value) {
    const modelIds = catalogQuery.value.modelIds.filter(id => id !== chip.value)
    const modificationIds = modelIds.length === 0
      ? []
      : catalogQuery.value.modificationIds.filter(modificationId => {
          const modification = facets.value.modifications.find(item => item.id === modificationId)
          return !modification || modelIds.includes(modification.model_id)
        })
    updateCatalogQuery({ modelIds, modificationIds, page: 1 })
  } else if (chip.kind === 'modification' && chip.value) {
    updateCatalogQuery({ modificationIds: catalogQuery.value.modificationIds.filter(id => id !== chip.value), page: 1 })
  } else if (chip.kind === 'trim' && chip.value) {
    updateCatalogQuery({ trimIds: catalogQuery.value.trimIds.filter(id => id !== chip.value), page: 1 })
  } else if (chip.kind === 'superstructure' && chip.value) {
    updateCatalogQuery({
      superstructureIds: (catalogQuery.value.superstructureIds ?? []).filter(id => id !== chip.value),
      page: 1,
    })
  } else if (chip.kind === 'bodyColor' && chip.value) {
    updateCatalogQuery({ bodyColorIds: catalogQuery.value.bodyColorIds.filter(id => id !== chip.value), page: 1 })
  } else if (chip.kind === 'interiorColor' && chip.value) {
    updateCatalogQuery({ interiorColorIds: catalogQuery.value.interiorColorIds.filter(id => id !== chip.value), page: 1 })
  } else if (chip.kind === 'availability' && (chip.value === 'available' || chip.value === 'on_order')) {
    updateCatalogQuery({ availability: ['available', 'on_order'], page: 1 })
  } else if (chip.kind === 'condition') {
    updateCatalogQuery({ condition: '', usageMin: '', usageMax: '', page: 1 })
  } else if (chip.kind === 'priceMin') {
    updateCatalogQuery({ priceMin: '', page: 1 })
  } else if (chip.kind === 'priceMax') {
    updateCatalogQuery({ priceMax: '', page: 1 })
  } else if (chip.kind === 'usage') {
    updateCatalogQuery({ usageMin: '', usageMax: '', page: 1 })
  } else if (chip.kind === 'city') {
    updateCatalogQuery({ cityId: '', warehouseId: '', page: 1 })
  } else if (chip.kind === 'warehouse') {
    updateCatalogQuery({ warehouseId: '', page: 1 })
  } else if (chip.kind === 'minInStock') {
    updateCatalogQuery({ minInStock: '', page: 1 })
  } else if (chip.kind === 'attribute' && chip.value) {
    const next = Object.fromEntries(Object.entries(dynamicFilters.value).filter(([id]) => id !== chip.value))
    updateCatalogQuery({ attributeTokens: serializeDynamicFilters(next), page: 1 })
  }
}
const submitSearch = () => updateCatalogQuery({ search: searchInput.value.trim().slice(0, 200), page: 1 })
const changeSort = (sort: SpecialEquipmentSort) => updateCatalogQuery({ sort, page: 1 })
const changePage = (page: number) => {
  updateCatalogQuery({ page })
  if (import.meta.client && props.scrollOnPageChange) {
    document.getElementById(props.resultsId)?.scrollIntoView({ behavior: 'smooth' })
  }
}

const openFilters = async () => {
  filtersOpen.value = true
  await nextTick()
  filterCloseButton.value?.focus()
}
const closeFilters = async () => {
  filtersOpen.value = false
  await nextTick()
  filterTrigger.value?.focus()
}
const handleFilterKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    event.preventDefault()
    void closeFilters()
    return
  }
  if (event.key !== 'Tab') return
  const focusable = [...(filterDrawer.value?.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
  ) ?? [])].filter(element => element.offsetParent !== null)
  const first = focusable[0]
  const last = focusable.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}
const handleAuthenticated = async () => {
  showAuthModal.value = false
  await commerce.handleAuthenticated()
}
watch(filtersOpen, isOpen => {
  if (!import.meta.client) return
  if (isOpen) {
    if (previousBodyOverflow === null) previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  } else if (previousBodyOverflow !== null) {
    document.body.style.overflow = previousBodyOverflow
    previousBodyOverflow = null
  }
})
onBeforeUnmount(() => {
  if (import.meta.client && previousBodyOverflow !== null) document.body.style.overflow = previousBodyOverflow
})

</script>

<style scoped>
.special-equipment-filter-drawer { height: 100vh; max-height: 100vh; }
.special-equipment-filter-scroll {
  overscroll-behavior-y: contain;
}
@supports (height: 100dvh) {
  .special-equipment-filter-drawer { height: 100dvh; max-height: 100dvh; }
}
.special-equipment-filter-backdrop-enter-active,
.special-equipment-filter-backdrop-leave-active { transition: opacity 180ms ease; }
.special-equipment-filter-backdrop-enter-from,
.special-equipment-filter-backdrop-leave-to { opacity: 0; }
.special-equipment-filter-drawer-enter-active,
.special-equipment-filter-drawer-leave-active { transition: transform 180ms ease; }
.special-equipment-filter-drawer-enter-from,
.special-equipment-filter-drawer-leave-to { transform: translateX(100%); }
@media (prefers-reduced-motion: reduce) {
  .special-equipment-filter-backdrop-enter-active,
  .special-equipment-filter-backdrop-leave-active,
  .special-equipment-filter-drawer-enter-active,
  .special-equipment-filter-drawer-leave-active { transition-duration: 0.01ms; }
}
</style>
