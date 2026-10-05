<template>
  <section class="se-relation-editor" :aria-labelledby="titleId">
    <header class="se-relation-editor__header">
      <div>
        <h3 :id="titleId">{{ title }}</h3>
        <p>{{ description }}</p>
      </div>
      <span class="se-relation-editor__count">{{ modelValue.length }}</span>
    </header>

    <div v-if="disabledMessage" class="se-relation-notice" role="status">
      <InformationCircleIcon aria-hidden="true" />
      <p>{{ disabledMessage }}</p>
    </div>

    <ol v-if="modelValue.length" class="se-relation-list" :aria-label="selectedLabel">
      <li v-for="(item, index) in modelValue" :key="relationProductId(item)">
        <div class="se-relation-list__main">
          <strong>{{ productTitle(item.product) }}</strong>
          <small>{{ productCaption(item.product) }}</small>
        </div>
        <div class="se-relation-list__actions">
          <button
            type="button"
            class="se-icon-button"
            :disabled="readonly || index === 0"
            :aria-label="`Поднять «${productTitle(item.product)}»`"
            @click="move(index, -1)"
          >
            <ArrowUpIcon aria-hidden="true" />
          </button>
          <button
            type="button"
            class="se-icon-button"
            :disabled="readonly || index === modelValue.length - 1"
            :aria-label="`Опустить «${productTitle(item.product)}»`"
            @click="move(index, 1)"
          >
            <ArrowDownIcon aria-hidden="true" />
          </button>
          <button
            type="button"
            class="se-icon-button se-icon-button--danger"
            :disabled="readonly"
            :aria-label="`Удалить «${productTitle(item.product)}» из ${selectedLabel.toLocaleLowerCase('ru-RU')}`"
            @click="remove(index)"
          >
            <TrashIcon aria-hidden="true" />
          </button>
        </div>
      </li>
    </ol>
    <div v-else class="se-quiet-state">{{ emptySelectionText }}</div>

    <p v-if="validationMessage" class="se-inline-error" role="alert">
      {{ validationMessage }}
    </p>

    <div class="se-relation-search">
      <label :for="searchId">{{ searchLabel }}</label>
      <div class="se-relation-search__input">
        <MagnifyingGlassIcon aria-hidden="true" />
        <input
          :id="searchId"
          v-model.trim="search"
          type="search"
          autocomplete="off"
          :placeholder="searchPlaceholder"
          :disabled="readonly || Boolean(disabledMessage)"
        >
      </div>
    </div>

    <fieldset class="se-relation-filters" :disabled="readonly || Boolean(disabledMessage)">
      <legend>Фильтры объявлений</legend>
      <label>
        <span>Марка</span>
        <select v-model="markFilter" class="select-field" :disabled="filterOptionsLoading">
          <option value="">Все марки</option>
          <option v-for="mark in markOptions" :key="mark.id" :value="mark.id">{{ mark.name }}</option>
        </select>
      </label>
      <label>
        <span>Модель</span>
        <select v-model="modelFilter" class="select-field" :disabled="!markFilter || modelsLoading">
          <option value="">Все модели</option>
          <option v-for="model in modelOptions" :key="model.id" :value="model.id">{{ model.name }}</option>
        </select>
      </label>
      <label>
        <span>Категория</span>
        <select v-model="categoryFilter" class="select-field" :disabled="filterOptionsLoading">
          <option value="">Все категории</option>
          <option v-for="category in categoryOptions" :key="category.id" :value="category.id">
            {{ category.canonical_path || category.name }}
          </option>
        </select>
      </label>
      <label>
        <span>Статус продажи</span>
        <select v-model="saleStatusFilter" class="select-field">
          <option value="">Все статусы</option>
          <option v-for="status in saleStatusOptions" :key="status.value" :value="status.value">
            {{ status.label }}
          </option>
        </select>
      </label>
      <button
        v-if="hasActiveFilters"
        type="button"
        class="se-button se-button--ghost se-button--small"
        @click="clearFilters"
      >
        Сбросить фильтры
      </button>
    </fieldset>
    <div v-if="filterOptionsError" class="se-relation-filter-error" role="alert">
      <span>{{ filterOptionsError }}</span>
      <button type="button" class="se-button se-button--ghost se-button--small" @click="loadFilterOptions">
        Повторить загрузку фильтров
      </button>
    </div>

    <div class="se-relation-results" aria-live="polite" :aria-busy="loading">
      <div v-if="loading" class="se-relation-results__state">
        <ArrowPathIcon class="se-spinner" aria-hidden="true" />
        Ищем объявления…
      </div>
      <div v-else-if="loadError" class="se-relation-results__state se-relation-results__state--error" role="alert">
        <span>{{ loadError }}</span>
        <button type="button" class="se-button se-button--secondary se-button--small" @click="loadCandidates">Повторить</button>
      </div>
      <div v-else-if="candidates.length === 0" class="se-relation-results__state">
        {{ search || hasActiveFilters ? 'По запросу и выбранным фильтрам ничего не найдено.' : emptyCandidatesText }}
      </div>
      <template v-else>
        <div class="se-relation-bulk-actions">
          <label>
            <input
              type="checkbox"
              :checked="allVisibleEligibleSelected"
              :disabled="visibleEligibleCandidates.length === 0"
              aria-label="Выбрать все доступные объявления на странице"
              @change="toggleAllVisible"
            >
            Выбрать доступные
          </label>
          <button
            type="button"
            class="se-button se-button--primary se-button--small"
            :disabled="readonly || selectedForBulk.length === 0"
            @click="addSelected"
          >
            Добавить выбранные ({{ selectedForBulk.length }})
          </button>
        </div>
        <ul class="se-relation-candidates">
          <li v-for="candidate in candidates" :key="candidate.id">
            <label class="se-relation-candidate-check">
              <input
                type="checkbox"
                :checked="selectedCandidates.has(candidate.id)"
                :disabled="readonly || Boolean(candidateDisabledReason(candidate))"
                :aria-label="`Выбрать «${productTitle(candidate)}» для группового добавления`"
                @change="toggleCandidate(candidate, $event)"
              >
              <span class="se-relation-candidate-copy">
                <strong>{{ productTitle(candidate) }}</strong>
                <small>{{ productCaption(candidate) }}</small>
              </span>
            </label>
            <button
              type="button"
              class="se-button se-button--secondary se-button--small"
              :disabled="readonly || Boolean(candidateDisabledReason(candidate))"
              :title="candidateDisabledReason(candidate)"
              @click="add(candidate)"
            >
              {{ selectedProductIds.has(candidate.id) ? 'Добавлено' : 'Добавить' }}
            </button>
          </li>
        </ul>
      </template>
    </div>

    <footer v-if="pages > 1" class="se-relation-pagination" aria-label="Страницы результатов поиска">
      <button
        type="button"
        class="se-page-button"
        aria-label="Предыдущая страница результатов"
        :disabled="page <= 1 || loading"
        @click="page -= 1"
      >
        <ChevronLeftIcon aria-hidden="true" />
      </button>
      <span>Страница {{ page }} из {{ pages }}</span>
      <button
        type="button"
        class="se-page-button"
        aria-label="Следующая страница результатов"
        :disabled="page >= pages || loading"
        @click="page += 1"
      >
        <ChevronRightIcon aria-hidden="true" />
      </button>
    </footer>
  </section>
</template>

<script setup lang="ts">
import {
  ArrowDownIcon,
  ArrowPathIcon,
  ArrowUpIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  InformationCircleIcon,
  MagnifyingGlassIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import { createCatalogCorrectionApi } from './api'
import type {
  CatalogCategory,
  CatalogMark,
  CatalogModel,
  CatalogProduct,
  CatalogProductAttachmentLink,
} from './types'
import {
  normalizeCatalogProductRelations,
  removeCatalogProductRelation,
} from './productRelations'
import { appendCatalogProductRelations } from './productRelationCandidates'

type RelationItem = CatalogProductAttachmentLink

const props = defineProps<{
  kind: 'attachments'
  productId: UUID | null
  modelValue: RelationItem[]
  readonly?: boolean
  oppositeCount?: number
  blockedReason?: string
}>()
const emit = defineEmits<{
  'update:modelValue': [items: RelationItem[]]
}>()

const api = createCatalogCorrectionApi(useRuntimeConfig())
const id = useId()
const titleId = `catalog-relations-title-${id}`
const searchId = `catalog-relations-search-${id}`
const search = ref('')
const markFilter = ref<UUID | ''>('')
const modelFilter = ref<UUID | ''>('')
const categoryFilter = ref<UUID | ''>('')
const saleStatusFilter = ref<CatalogProduct['sale_status'] | ''>('')
const page = ref(1)
const pages = ref(1)
const candidates = ref<CatalogProduct[]>([])
const markOptions = ref<CatalogMark[]>([])
const modelOptions = ref<CatalogModel[]>([])
const categoryOptions = ref<CatalogCategory[]>([])
const selectedCandidates = ref<Map<UUID, CatalogProduct>>(new Map())
const loading = ref(false)
const loadError = ref('')
const filterOptionsLoading = ref(false)
const modelsLoading = ref(false)
const filterOptionsError = ref('')
let controller: AbortController | null = null
let filterOptionsController: AbortController | null = null
let modelsController: AbortController | null = null
let sequence = 0
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const title = computed(() => 'Совместимые надстройки')
const description = computed(() => 'Выберите конкретные объявления надстроек и расположите их в порядке показа.')
const selectedLabel = computed(() => 'Выбранные надстройки')
const searchLabel = computed(() => 'Найти надстройку')
const searchPlaceholder = computed(() => 'Название, марка, модель или код надстройки')
const emptySelectionText = computed(() => 'Совместимые надстройки ещё не выбраны.')
const emptyCandidatesText = computed(() => 'Доступных объявлений надстроек нет.')
const disabledMessage = computed(() => props.blockedReason || '')
const selectedProductIds = computed(() => new Set(props.modelValue.map(relationProductId)))
const saleStatusOptions: ReadonlyArray<{
  value: CatalogProduct['sale_status']
  label: string
}> = [
  { value: 'available', label: 'В наличии' },
  { value: 'on_order', label: 'Под заказ' },
  { value: 'reserved', label: 'Зарезервировано' },
  { value: 'sold', label: 'Продано' },
  { value: 'unavailable', label: 'Недоступно' },
]
const hasActiveFilters = computed(() => Boolean(
  markFilter.value || modelFilter.value || categoryFilter.value || saleStatusFilter.value,
))
const clearFilters = () => {
  markFilter.value = ''
  modelFilter.value = ''
  categoryFilter.value = ''
  saleStatusFilter.value = ''
}
const validationMessage = computed(() => '')

const relationProductId = (item: RelationItem): UUID => item.attachment_product_id
const productTitle = (product: CatalogProduct): string => [
  product.mark_name,
  product.model_name,
  product.modification_name,
].filter(Boolean).join(' ') || product.code
const productCaption = (product: CatalogProduct): string => [
  `Код: ${product.code}`,
  product.sale_status === 'available' ? 'В наличии' : product.sale_status === 'on_order' ? 'Под заказ' : null,
].filter(Boolean).join(' · ')
const replace = (items: RelationItem[]) => emit(
  'update:modelValue',
  normalizeCatalogProductRelations(items),
)
const move = (index: number, direction: -1 | 1) => {
  const items = [...props.modelValue]
  const target = index + direction
  if (index < 0 || target < 0 || target >= items.length) return
  ;[items[index], items[target]] = [items[target]!, items[index]!]
  replace(items)
}
const remove = (index: number) => {
  replace(removeCatalogProductRelation(props.modelValue, index))
}
const candidateDisabledReason = (candidate: CatalogProduct): string => {
  if (props.productId && candidate.id === props.productId) return 'Нельзя связать объявление с самим собой.'
  if (selectedProductIds.value.has(candidate.id)) return 'Объявление уже добавлено.'
  if (candidate.is_attachment === false) {
    return 'Выбранное объявление не относится к ветви надстроек.'
  }
  return ''
}
const visibleEligibleCandidates = computed(() => candidates.value.filter(
  candidate => !candidateDisabledReason(candidate),
))
const selectedForBulk = computed(() => Array.from(selectedCandidates.value.values()).filter(
  candidate => !candidateDisabledReason(candidate),
))
const allVisibleEligibleSelected = computed(() => (
  visibleEligibleCandidates.value.length > 0
  && visibleEligibleCandidates.value.every(candidate => selectedCandidates.value.has(candidate.id))
))
const updateCandidateSelection = (product: CatalogProduct, checked: boolean) => {
  const next = new Map(selectedCandidates.value)
  if (checked) next.set(product.id, product)
  else next.delete(product.id)
  selectedCandidates.value = next
}
const toggleCandidate = (product: CatalogProduct, event: Event) => {
  updateCandidateSelection(product, (event.currentTarget as HTMLInputElement).checked)
}
const toggleAllVisible = (event: Event) => {
  const checked = (event.currentTarget as HTMLInputElement).checked
  const next = new Map(selectedCandidates.value)
  for (const product of visibleEligibleCandidates.value) {
    if (checked) next.set(product.id, product)
    else next.delete(product.id)
  }
  selectedCandidates.value = next
}
const appendProducts = (products: readonly CatalogProduct[]) => {
  replace(appendCatalogProductRelations('attachments', props.modelValue, products))
}
const add = (product: CatalogProduct) => {
  if (candidateDisabledReason(product) || disabledMessage.value) return
  appendProducts([product])
  updateCandidateSelection(product, false)
}
const addSelected = () => {
  if (selectedForBulk.value.length === 0 || disabledMessage.value) return
  appendProducts(selectedForBulk.value)
  selectedCandidates.value = new Map()
}

const errorMessage = (error: unknown): string => {
  if (!error || typeof error !== 'object') return 'Неизвестная ошибка.'
  const failure = error as { message?: string; data?: { detail?: string } }
  return failure.data?.detail || failure.message || 'Не удалось загрузить объявления.'
}
const loadFilterOptions = async () => {
  filterOptionsController?.abort()
  const requestController = new AbortController()
  filterOptionsController = requestController
  filterOptionsLoading.value = true
  filterOptionsError.value = ''
  try {
    const [marks, categories] = await Promise.all([
      api.listAll<CatalogMark>('marks', {}, requestController.signal),
      api.listAll<CatalogCategory>('categories', { sort: 'hierarchy' }, requestController.signal),
    ])
    markOptions.value = marks
    categoryOptions.value = categories
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    filterOptionsError.value = errorMessage(error)
  } finally {
    if (filterOptionsController === requestController) filterOptionsLoading.value = false
  }
}
const loadModels = async (markId: UUID | '') => {
  modelsController?.abort()
  modelOptions.value = []
  if (!markId) {
    modelsLoading.value = false
    return
  }
  const requestController = new AbortController()
  modelsController = requestController
  modelsLoading.value = true
  try {
    modelOptions.value = await api.listAll<CatalogModel>(
      'models',
      { mark_id: markId },
      requestController.signal,
    )
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    filterOptionsError.value = errorMessage(error)
  } finally {
    if (modelsController === requestController) modelsLoading.value = false
  }
}
const loadCandidates = async () => {
  controller?.abort()
  if (props.readonly || disabledMessage.value) {
    candidates.value = []
    loading.value = false
    return
  }
  const currentSequence = ++sequence
  const requestController = new AbortController()
  controller = requestController
  loading.value = true
  loadError.value = ''
  try {
    const result = await api.list<CatalogProduct>('products', {
      search: search.value || undefined,
      page: page.value,
      page_size: 10,
      role: 'attachment',
      mark_id: markFilter.value || undefined,
      model_id: modelFilter.value || undefined,
      category_id: categoryFilter.value || undefined,
      sale_status: saleStatusFilter.value || undefined,
    }, requestController.signal)
    if (currentSequence !== sequence) return
    candidates.value = result.items
    pages.value = Math.max(1, result.pagination.pages)
    if (page.value > pages.value) page.value = pages.value
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    if (currentSequence === sequence) loadError.value = errorMessage(error)
  } finally {
    if (currentSequence === sequence) loading.value = false
  }
}

watch(search, () => {
  page.value = 1
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { void loadCandidates() }, 350)
})
watch(markFilter, (markId) => {
  modelFilter.value = ''
  void loadModels(markId)
})
watch([markFilter, modelFilter, categoryFilter, saleStatusFilter], () => {
  page.value = 1
  void loadCandidates()
})
watch(page, () => { void loadCandidates() })
watch(() => [props.kind, props.readonly, disabledMessage.value], () => {
  selectedCandidates.value = new Map()
  clearFilters()
  page.value = 1
  void loadCandidates()
}, { immediate: true })
void loadFilterOptions()
onBeforeUnmount(() => {
  controller?.abort()
  filterOptionsController?.abort()
  modelsController?.abort()
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<style scoped>
.se-relation-editor { display: grid; gap: 14px; }
.se-relation-editor__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.se-relation-editor__header h3 { margin: 0; font-size: 15px; font-weight: 780; }
.se-relation-editor__header p { margin: 3px 0 0; color: hsl(var(--se-muted)); font-size: 13px; }
.se-relation-editor__count { display: grid; min-width: 28px; height: 26px; place-items: center; border-radius: 999px; background: hsl(var(--se-surface-strong)); color: hsl(var(--se-muted)); font-size: 12px; font-weight: 800; font-variant-numeric: tabular-nums; }
.se-relation-notice { display: flex; align-items: flex-start; gap: 9px; padding: 11px 12px; border-radius: var(--se-radius-sm); background: hsl(var(--se-warning-soft)); color: hsl(var(--se-warning)); }
.se-relation-notice p { margin: 0; color: hsl(var(--se-text-soft)); }
.se-relation-list, .se-relation-candidates { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.se-relation-list li, .se-relation-candidates li { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 12px; padding: 10px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); }
.se-relation-list__main, .se-relation-candidate-copy { display: grid; min-width: 0; gap: 2px; }
.se-relation-list strong, .se-relation-candidates strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.se-relation-list small, .se-relation-candidates small { color: hsl(var(--se-muted)); }
.se-relation-base { width: fit-content; margin-top: 3px; padding: 2px 7px; border-radius: 999px; background: hsl(var(--se-primary-soft)); color: hsl(var(--se-primary)); font-size: 12px; font-weight: 750; }
.se-relation-list__actions { display: flex; flex: none; align-items: center; gap: 3px; }
.se-relation-base-action { border-color: hsl(var(--se-primary) / .35); color: hsl(var(--se-primary)); }
.se-relation-search { display: grid; gap: 5px; }
.se-relation-search > label { color: hsl(var(--se-text-soft)); font-weight: 700; }
.se-relation-search__input { position: relative; }
.se-relation-search__input svg { position: absolute; top: 50%; left: 11px; width: 18px; height: 18px; color: hsl(var(--se-muted)); transform: translateY(-50%); pointer-events: none; }
.se-relation-search__input input { width: 100%; min-height: 42px; padding: 9px 12px 9px 38px; border: 1px solid hsl(var(--se-border-strong)); border-radius: var(--se-radius-sm); background: hsl(var(--se-surface)); color: hsl(var(--se-text)); }
.se-relation-filters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; margin: 0; padding: 12px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); }
.se-relation-filters legend { padding: 0 5px; color: hsl(var(--se-text-soft)); font-size: 13px; font-weight: 750; }
.se-relation-filters label { display: grid; min-width: 0; gap: 4px; color: hsl(var(--se-muted)); font-size: 12px; font-weight: 700; }
.se-relation-filters select { width: 100%; min-height: 38px; padding: 7px 9px; border: 1px solid hsl(var(--se-border-strong)); border-radius: var(--se-radius-sm); background: hsl(var(--se-surface)); color: hsl(var(--se-text)); }
.se-relation-filters .se-button { align-self: end; }
.se-relation-filter-error { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; color: hsl(var(--se-danger)); font-size: 13px; }
.se-relation-results { min-height: 64px; }
.se-relation-replacement { display: grid; gap: 8px; padding: 12px; border: 1px solid hsl(var(--se-warning) / .35); border-radius: var(--se-radius-sm); background: hsl(var(--se-warning-soft)); }
.se-relation-replacement p { margin: 0; color: hsl(var(--se-text-soft)); }
.se-relation-replacement__actions { display: flex; flex-wrap: wrap; gap: 6px; }
.se-relation-results__state { display: flex; min-height: 64px; align-items: center; justify-content: center; gap: 9px; padding: 12px; border-radius: var(--se-radius-sm); background: hsl(var(--se-surface-muted)); color: hsl(var(--se-muted)); text-align: center; }
.se-relation-results__state--error { flex-wrap: wrap; background: hsl(var(--se-danger-soft)); color: hsl(var(--se-danger)); }
.se-relation-bulk-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; padding: 9px 10px; border-radius: var(--se-radius-sm); background: hsl(var(--se-surface-muted)); }
.se-relation-bulk-actions label, .se-relation-candidate-check { display: flex; min-width: 0; align-items: center; gap: 9px; cursor: pointer; }
.se-relation-bulk-actions input, .se-relation-candidate-check input { width: 17px; height: 17px; flex: none; accent-color: hsl(var(--se-primary)); }
.se-relation-candidate-check { flex: 1; }
.se-relation-candidates .se-button { flex: none; }
.se-relation-pagination { display: flex; align-items: center; justify-content: center; gap: 9px; color: hsl(var(--se-muted)); font-size: 13px; font-variant-numeric: tabular-nums; }
</style>
