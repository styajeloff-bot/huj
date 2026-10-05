<template>
  <main class="se-registry-page">
    <ol class="se-breadcrumbs" aria-label="Хлебные крошки">
      <li><NuxtLink to="/workspace">Рабочее пространство</NuxtLink></li>
      <li aria-current="page">Каталог транспортных средств и специальной техники</li>
    </ol>

    <header class="se-page-heading">
      <div>
        <p class="se-page-kicker">Спецтехника</p>
        <h1>Управление каталогом</h1>
        <p class="se-page-lead">Справочники, категории, характеристики и объявления в одной согласованной структуре.</p>
      </div>
      <div class="se-page-actions">
        <NuxtLink class="se-button se-button--secondary" to="/workspace/special-equipment-import">
          <ArrowUpTrayIcon aria-hidden="true" />
          Импорт из Excel
        </NuxtLink>
      </div>
    </header>

    <section class="se-registry-card" aria-labelledby="catalog-table-title">
      <h2 id="catalog-table-title" class="sr-only">Записи каталога</h2>
      <CatalogTabsScroller :active-key="entity">
        <nav class="se-tabs" aria-label="Разделы каталога">
          <button
            v-for="tab in tabs"
            :key="tab.entity"
            type="button"
            class="se-tab"
            :class="{ 'se-tab--active': entity === tab.entity }"
            :aria-current="entity === tab.entity ? 'page' : undefined"
            @click="selectEntity(tab.entity)"
          >
            {{ tab.label }}
            <span v-if="counts[tab.entity] !== undefined" class="se-tab-count">{{ counts[tab.entity] }}</span>
          </button>
        </nav>
      </CatalogTabsScroller>

      <div class="se-toolbar">
        <div v-if="entity === 'models' || entity === 'modifications' || entity === 'trims'" class="se-toolbar-filters" aria-label="Фильтры справочника">
          <label class="se-field-compact">
            <span>{{ entity === 'models' ? 'Марка' : 'Сначала выберите марку' }}</span>
            <CatalogSearchableSelect
              :model-value="registryMarkId"
              :options="marks"
              label="Фильтр по марке"
              placeholder="Найдите марку"
              @change="changeRegistryMark"
            />
          </label>
          <label v-if="entity === 'modifications' || entity === 'trims'" class="se-field-compact">
            <span>Модель</span>
            <CatalogSearchableSelect
              :model-value="registryModelId"
              :options="registryModels"
              label="Фильтр по модели"
              :placeholder="registryModelsLoading ? 'Загрузка…' : 'Найдите модель'"
              :disabled="!registryMarkId || registryModelsLoading"
              @change="changeRegistryModel"
            />
          </label>
        </div>
        <div v-else-if="entity === 'categories'" class="se-toolbar-filters se-toolbar-filters--categories" aria-label="Фильтры категорий">
          <label class="se-field-compact">
            <span>Сортировка</span>
            <select class="select-field" :value="categorySort" @change="changeCategorySort">
              <option value="updated_desc">По дате</option>
              <option value="hierarchy">По иерархии</option>
            </select>
          </label>
          <label v-for="level in visibleCategoryLevels" :key="level" class="se-field-compact">
            <span>Уровень {{ level }}</span>
            <CatalogSearchableSelect
              :model-value="categoryLevelIds[level - 1] ?? ''"
              :options="categoryLevelOptions(level - 1)"
              :label="`Фильтр категорий, уровень ${level}`"
              placeholder="Все"
              :disabled="level > 1 && !categoryLevelIds[level - 2]"
              @change="changeCategoryLevel(level - 1, $event)"
            />
          </label>
        </div>
        <div v-else-if="entity === 'products'" class="se-toolbar-filters" aria-label="Фильтры объявлений">
          <label class="se-field-compact">
            <span>Нормализация</span>
            <select class="select-field" :value="normalizationState" @change="changeNormalizationState">
              <option value="">Все объявления</option>
              <option value="normalized">Нормализованные</option>
              <option value="legacy">Требуют нормализации</option>
              <option value="conflict">Конфликт данных</option>
            </select>
          </label>
          <label v-for="level in visibleProductCategoryLevels" :key="level" class="se-field-compact">
            <span>Категория, уровень {{ level }}</span>
            <CatalogSearchableSelect
              :model-value="categoryLevelIds[level - 1] ?? ''"
              :options="categoryLevelOptions(level - 1)"
              :label="`Фильтр объявлений по категории, уровень ${level}`"
              placeholder="Все"
              :disabled="level > 1 && !categoryLevelIds[level - 2]"
              @change="changeProductCategoryLevel(level - 1, $event)"
            />
          </label>
        </div>
        <div v-else-if="entity === 'attributes'" class="se-toolbar-filters" aria-label="Фильтры характеристик">
          <label class="se-field-compact">
            <span>Группа</span>
            <CatalogSearchableSelect
              :model-value="registryAttributeGroupId"
              :options="groups"
              label="Фильтр по группе характеристик"
              placeholder="Все группы"
              @change="changeRegistryAttributeGroup"
            />
          </label>
        </div>
        <div v-else-if="entity === 'colors'" class="se-toolbar-filters" aria-label="Фильтры цветов">
          <label class="se-field-compact">
            <span>Применимость</span>
            <select class="select-field" :value="colorApplicabilityFilter" @change="changeColorApplicabilityFilter">
              <option value="">Все</option>
              <option value="body">Кузов</option>
              <option value="interior">Салон</option>
              <option value="both">Кузов и салон</option>
            </select>
          </label>
          <label class="se-field-compact">
            <span>Статус</span>
            <select class="select-field" :value="colorActiveFilter" @change="changeColorActiveFilter">
              <option value="">Все</option>
              <option value="true">Активные</option>
              <option value="false">Неактивные</option>
            </select>
          </label>
        </div>
        <label class="se-search">
          <MagnifyingGlassIcon aria-hidden="true" />
          <span class="sr-only">Поиск по разделу</span>
          <input v-model="searchInput" type="search" :placeholder="`Поиск: ${activeTab.label.toLocaleLowerCase('ru-RU')}`" @keydown.enter.prevent="applySearch">
        </label>
        <button type="button" class="se-button se-button--primary se-create-inline" :disabled="!canWrite" @click="openCreate">
          <PlusIcon aria-hidden="true" />
          {{ activeTab.createLabel }}
        </button>
      </div>

      <div v-if="loading" class="se-system-state" aria-label="Загрузка записей">
        <div class="se-skeleton-list">
          <div v-for="index in 6" :key="index" class="se-skeleton-row">
            <span class="se-skeleton se-skeleton--thumb" />
            <span class="se-skeleton" />
            <span class="se-skeleton" />
            <span class="se-skeleton" />
          </div>
        </div>
      </div>
      <div v-else-if="loadError" class="se-system-state" role="alert">
        <div class="se-state-content">
          <div class="se-state-icon se-state-icon--error"><ExclamationTriangleIcon aria-hidden="true" /></div>
          <h3>Не удалось загрузить раздел</h3>
          <p>{{ loadError }}</p>
          <button type="button" class="se-button se-button--secondary" @click="loadRows">Повторить</button>
        </div>
      </div>
      <div v-else-if="rows.length === 0" class="se-system-state">
        <div class="se-state-content">
          <div class="se-state-icon"><RectangleStackIcon aria-hidden="true" /></div>
          <h3>{{ missingRegistryFilter ? 'Выберите связанный справочник' : search ? 'Ничего не найдено' : 'Записей пока нет' }}</h3>
          <p>{{ missingRegistryFilter || (search ? 'Измените поисковый запрос.' : `Создайте первую запись в разделе «${activeTab.label}».`) }}</p>
          <button v-if="!search && !missingRegistryFilter" type="button" class="se-button se-button--primary" :disabled="!canWrite" @click="openCreate">{{ activeTab.createLabel }}</button>
        </div>
      </div>
      <template v-else>
        <div class="se-table-scroll">
          <table class="se-table">
            <thead>
              <tr>
                <th>{{ activeTab.singular }}</th>
                <th v-if="entity === 'colors'">Применимость</th>
                <th v-else>Связи</th>
                <th v-if="showParametersColumn">Параметры</th>
                <th>Код</th>
                <th>{{ entity === 'colors' ? 'Дата изменения' : 'Состояние' }}</th>
                <th><span class="sr-only">Действия</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.id">
                <td>
                  <button type="button" class="se-entity-name" @click="openEdit(row.id)">{{ resourceTitle(row) }}</button>
                  <span
                    class="se-entity-meta"
                    :class="{ 'se-entity-meta--path': entity === 'categories' }"
                  >{{ resourceCaption(row) }}</span>
                </td>
                <td>{{ entity === 'colors' ? colorApplicabilityLabel(record(row).applicability) : resourceRelations(row) }}</td>
                <td v-if="showParametersColumn">{{ resourceParameters(row) }}</td>
                <td class="se-tabular">{{ row.code }}</td>
                <td>
                  <span v-if="entity === 'colors'" class="se-entity-meta">{{ formatDateTime(record(row).updated_at) }}</span>
                  <span v-else class="se-status" :class="statusClass(row)">{{ statusLabel(row) }}</span>
                </td>
                <td>
                  <div class="se-row-actions">
                    <button v-if="entity === 'colors'" type="button" class="se-button se-button--secondary se-button--small" :disabled="!canWrite || saving" @click="toggleColor(row)">{{ record(row).is_active === false ? 'Активировать' : 'Деактивировать' }}</button>
                    <button v-if="entity === 'units'" type="button" class="se-button se-button--secondary se-button--small" :disabled="!canWrite || saving" @click="openMergeModal(row)">Объединить</button>
                    <button type="button" class="se-button se-button--secondary se-button--small" @click="openEdit(row.id)">Открыть</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <footer class="se-registry-footer">
        <p class="se-result-count">Показано {{ rows.length }} из {{ pagination.total }}</p>
        <div class="se-pagination" aria-label="Страницы">
          <button type="button" class="se-page-button" aria-label="Предыдущая страница" :disabled="pagination.page <= 1" @click="changePage(pagination.page - 1)">
            <ChevronLeftIcon aria-hidden="true" />
          </button>
          <span class="se-page-button" aria-current="page">{{ pagination.page }}</span>
          <button type="button" class="se-page-button" aria-label="Следующая страница" :disabled="pagination.page >= pagination.pages" @click="changePage(pagination.page + 1)">
            <ChevronRightIcon aria-hidden="true" />
          </button>
        </div>
      </footer>
    </section>

    <CatalogCorrectionDrawer
      :open="drawerOpen"
      :mode="drawerMode"
      :title="drawerTitle"
      :subtitle="drawerSubtitle"
      :dirty="dirty"
      :busy="saving"
      :save-disabled="saveDisabled"
      :can-delete="canWrite"
      @close="closeDrawer"
      @save="save"
      @delete="openCascadeDeleteFromDrawer"
    >
      <div v-if="versionConflict" class="se-version-conflict" role="alert">
        <ExclamationTriangleIcon aria-hidden="true" />
        <div>
          <strong>Запись изменилась на сервере</strong>
          <p>Локальные правки сохранены в форме. Загрузите актуальную версию и повторите изменения.</p>
        </div>
        <button type="button" class="se-button se-button--secondary se-button--small" @click="reloadCurrent">
          Загрузить актуальную версию
        </button>
      </div>
      <CatalogCorrectionForm
        :key="drawerSession"
        v-model="draft"
        :entity="entity"
        :mode="drawerMode"
        :categories="categories"
        :marks="marks"
        :models="dependent.models.value"
        :modifications="dependent.modifications.value"
        :attributes="attributes"
        :attributes-loading="attributesLoading"
        :attributes-error-message="attributesErrorMessage"
        :groups="groups"
        :units="units"
        :sellers="sellers"
        :warehouses="warehouses"
        :warehouses-loading="warehousesLoading"
        :warehouses-error-message="warehousesErrorMessage"
        :body-color-options="bodyColorOptions"
        :interior-color-options="interiorColorOptions"
        :models-loading="dependent.modelsLoading.value"
        :modifications-loading="dependent.modificationsLoading.value"
        :selected-modification="selectedModification"
        :selected-product-trim-attributes="selectedProductTrimAttributes"
        :selected-product-trim-attributes-loading="selectedProductTrimAttributesLoading"
        :selected-product-trim-attributes-error-message="selectedProductTrimAttributesErrorMessage"
        :trims="trims"
        :trims-loading="trimsLoading"
        :trim-required="trimRequired"
        :trim-attribute-candidate-groups="trimAttributeCandidateGroups"
        :trim-attribute-candidates-loading="trimAttributeCandidatesLoading"
        :trim-attribute-candidates-error-message="trimAttributeCandidatesErrorMessage"
        :error-message="saveError"
        @mark-change="dependent.loadModels"
        @model-change="dependent.loadModifications"
        @modification-change="loadSelectedModification"
        @trim-change="loadSelectedProductTrimAttributes"
        @trim-candidates-retry="loadTrimAttributeCandidates"
        @retry-attributes="loadDirectories"
        @retry-warehouses="loadWarehouses"
      />

      <fieldset v-if="entity === 'products' || entity === 'categories'" class="se-form-section">
        <legend>{{ entity === 'products' ? 'Фотографии объявления' : 'Изображение категории' }}</legend>
        <p class="se-section-help">Главное изображение объявления выбирается отдельно и не связано с категориями.</p>
        <SpecialEquipmentImageEditor
          :existing-images="visibleImages"
          :pending-files="pendingFiles"
          :single="entity === 'categories'"
          :category-image-url="entity === 'categories' ? categoryImageUrl : null"
          :readonly="!canWrite"
          @add-files="addPendingFiles"
          @remove-pending="pendingFiles.splice($event, 1)"
          @remove-image="removeDraftImage"
          @remove-category-image="categoryImageRemoved = true"
          @move="moveDraftImage"
          @make-primary="makePrimary"
          @change-alt="changeImageDescription"
        />
      </fieldset>
    </CatalogCorrectionDrawer>

    <CatalogCascadeDeleteModal
      :show="deleteModalOpen"
      :entity="deleteEntity"
      :entity-id="deleteEntityId"
      :entity-name="deleteEntityName"
      :entity-code="deleteEntityCode"
      :etag="deleteEntityEtag"
      :api="api"
      @close="deleteModalOpen = false"
      @deleted="onCascadeDeleted"
    />

    <CatalogUnitMergeModal
      :show="mergeModalOpen"
      :source-unit="mergeSourceUnit"
      :units="units"
      :etag="mergeSourceEtag"
      @close="mergeModalOpen = false"
      @confirm="confirmMerge"
    />
  </main>
</template>

<script setup lang="ts">
import {
  ArrowUpTrayIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  RectangleStackIcon,
} from '@heroicons/vue/24/outline'
import { useHydrationReady } from '~/composables/useHydrationReady'
import { useAuthStore } from '~/features/auth/store/auth'
import { isUuid, type UUID } from '~/types/ids'
import SpecialEquipmentImageEditor from '../components/SpecialEquipmentImageEditor.vue'
import type { RegistryImage } from '../types'
import { createCatalogCorrectionApi } from './api'
import { isCatalogAttributeOptionsSaveInvalid } from './catalogCode'
import { isCatalogAttributeFilterCompatible } from './catalogAttributeFilter'
import {
  resumeCatalogCreateMedia,
  type CatalogCreateMediaCheckpoint,
} from './catalogCreateMediaRetry'
import { normalizeCatalogInteger } from './catalogInteger'
import { isPositiveCatalogPrice, normalizeCatalogPrice } from './catalogPrice'
import {
  categoryIsInAttachmentBranch,
  productCategoriesShareClassification,
} from './catalogProductCategories'
import { buildCatalogCorrectionPayload } from './catalogPayload'
import { loadCatalogSectionCounts } from './catalogSectionCounts'
import {
  buildCategoryRegistryQuery,
  buildProductRegistryQuery,
  categoryOptionsForLevel,
  categoryLevelsFromQuery,
  categorySortFromQuery,
  replaceCategoryLevel,
  visibleCategoryLevelCount,
  visibleProductCategoryLevelCount,
} from './registryQuery'
import CatalogCorrectionDrawer from './CatalogCorrectionDrawer.vue'
import CatalogCascadeDeleteModal from './CatalogCascadeDeleteModal.vue'
import CatalogCorrectionForm from './CatalogCorrectionForm.vue'
import CatalogSearchableSelect from './CatalogSearchableSelect.vue'
import CatalogTabsScroller from './CatalogTabsScroller.vue'
import { useDependentCatalogDirectories } from './useDependentCatalogDirectories'
import type {
  CatalogAttribute,
  CatalogActiveWarehouse,
  CatalogAttributeGroup,
  CatalogCategory,
  CatalogColorApplicability,
  CatalogColorSelectItem,
  CatalogDraft,
  CatalogEntity,
  CatalogMark,
  CatalogModel,
  CatalogModification,
  CatalogProduct,
  CatalogProductAttachmentInput,
  CatalogProductAttachmentLink,
  CatalogProductCreateRequest,
  CatalogResource,
  CatalogSellerCompany,
  CatalogSuperstructureAttribute,
  CatalogTrim,
  CatalogTrimLifecycleItem,
  CatalogTrimAttributeAssignment,
  CatalogTrimAttributeCandidateGroup,
  CatalogTrimAttributeValue,
  CatalogUnit,
} from './types'
import { syncCatalogProductRelations } from './productRelationSync'
import { groupTrimAttributeCandidates } from './trimAttributeCandidates'
import {
  advanceTrimAttributeCheckpoint,
  planTrimAttributeSync,
} from './trimAttributeSync'
import CatalogUnitMergeModal from './CatalogUnitMergeModal.vue'
import '../registry.css'

const tabs: Array<{
  entity: CatalogEntity
  label: string
  singular: string
  createLabel: string
}> = [
  { entity: 'products', label: 'Объявления', singular: 'Объявление', createLabel: 'Создать объявление' },
  { entity: 'categories', label: 'Категории', singular: 'Категория', createLabel: 'Создать категорию' },
  { entity: 'marks', label: 'Марки', singular: 'Марка', createLabel: 'Создать марку' },
  { entity: 'models', label: 'Модели', singular: 'Модель', createLabel: 'Создать модель' },
  { entity: 'modifications', label: 'Модификации', singular: 'Модификация', createLabel: 'Создать модификацию' },
  { entity: 'trims', label: 'Комплектации', singular: 'Комплектация', createLabel: 'Создать комплектацию' },
  { entity: 'attributes', label: 'Характеристики', singular: 'Характеристика', createLabel: 'Создать характеристику' },
  { entity: 'attribute-groups', label: 'Группы характеристик', singular: 'Группа', createLabel: 'Создать группу' },
  { entity: 'colors', label: 'Цвета', singular: 'Цвет', createLabel: 'Создать цвет' },
  { entity: 'units', label: 'Единицы измерения', singular: 'Единица измерения', createLabel: 'Создать единицу измерения' },
  { entity: 'superstructures', label: 'Надстройки', singular: 'Тип надстройки', createLabel: 'Создать тип надстройки' },
]

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const authHydrationReady = useHydrationReady()
const api = createCatalogCorrectionApi(useRuntimeConfig())
const dependent = useDependentCatalogDirectories(api)
const toast = useToast()
const entity = computed<CatalogEntity>(() => {
  const candidate = typeof route.query.section === 'string'
    ? route.query.section
    : typeof route.query.entity === 'string'
      ? route.query.entity
      : ''
  return tabs.some(tab => tab.entity === candidate) ? candidate as CatalogEntity : 'products'
})
const activeTab = computed(() => tabs.find(tab => tab.entity === entity.value) ?? tabs[0]!)
const canWrite = computed(() =>
  authHydrationReady.value && authStore.hasScope('special-equipment-catalog:write'))
const rows = ref<CatalogResource[]>([])
const counts = reactive<Partial<Record<CatalogEntity, number>>>({})
const loading = ref(false)
const loadError = ref('')
const searchInput = ref(typeof route.query.q === 'string' ? route.query.q : '')
const search = computed(() => typeof route.query.q === 'string' ? route.query.q : '')
const pagination = ref({ page: 1, page_size: 30, total: 0, pages: 1 })
let listController: AbortController | null = null
let countsController: AbortController | null = null
let listSequence = 0
let directoriesSequence = 0

const categories = ref<CatalogCategory[]>([])
const marks = ref<CatalogMark[]>([])
const registryModels = ref<CatalogModel[]>([])
const registryModelsLoading = ref(false)
const attributes = ref<CatalogAttribute[]>([])
const attributesLoading = ref(false)
const attributesErrorMessage = ref('')
const groups = ref<CatalogAttributeGroup[]>([])
const units = ref<CatalogUnit[]>([])
const mergeModalOpen = ref(false)
const mergeSourceUnit = ref<CatalogUnit | null>(null)
const mergeSourceEtag = ref('')
const sellers = ref<CatalogSellerCompany[]>([])
const warehouses = ref<CatalogActiveWarehouse[]>([])
const warehousesLoading = ref(false)
const warehousesErrorMessage = ref('')
const bodyColors = ref<CatalogColorSelectItem[]>([])
const interiorColors = ref<CatalogColorSelectItem[]>([])
const bodyColorOptions = computed(() => bodyColors.value)
const interiorColorOptions = computed(() => interiorColors.value)
const drawerOpen = ref(false)
const drawerMode = ref<'create' | 'edit'>('create')
const drawerSession = ref(0)
const draft = ref<CatalogDraft>({ code: '' })
const initialSnapshot = ref('')
const currentEtag = ref('')
const saving = ref(false)
const saveError = ref('')
const versionConflict = ref(false)
const initialAttachmentSnapshot = ref('[]')
const initialComponentSnapshot = ref('[]')
const selectedModification = ref<CatalogModification | null>(null)
const trims = ref<CatalogTrimLifecycleItem[]>([])
const trimsLoading = ref(false)
const trimRequired = ref(false)
const selectedProductTrimAttributes = ref<CatalogTrimAttributeAssignment[]>([])
const selectedProductTrimAttributesLoading = ref(false)
const selectedProductTrimAttributesErrorMessage = ref('')
let selectedProductTrimRequest = 0
const trimAttributeCandidateGroups = ref<CatalogTrimAttributeCandidateGroup[]>([])
const trimAttributeCandidatesLoading = ref(false)
const trimAttributeCandidatesErrorMessage = ref('')
let trimAttributeCandidateController: AbortController | null = null
let trimAttributeCandidateRequest = 0
const trimStateEtag = ref('')
const initialTrimAttributesSnapshot = ref('[]')
const initialTrimAttributeValuesSnapshot = ref('[]')
const pendingFiles = ref<File[]>([])
const removedImageIds = ref<Set<UUID>>(new Set())
const categoryImageRemoved = ref(false)
const createIdempotencyKey = ref('')
const createdResourceCheckpoint = ref<CatalogCreateMediaCheckpoint<CatalogResource> | null>(null)
const registryMarkId = computed<UUID | ''>(() =>
  typeof route.query.mark_id === 'string' ? route.query.mark_id as UUID : '')
const registryModelId = computed<UUID | ''>(() =>
  typeof route.query.model_id === 'string' ? route.query.model_id as UUID : '')
const registryAttributeGroupId = computed<UUID | ''>(() => {
  const value = route.query.attribute_group_id
  return typeof value === 'string' && isUuid(value) ? value : ''
})
const categoryLevelIds = computed<UUID[]>(() => categoryLevelsFromQuery(route.query))
const categorySort = computed(() => categorySortFromQuery(route.query.sort))
const pageFromRouteQuery = (value: unknown): number => {
  const candidate = typeof value === 'string' ? value : ''
  if (!/^\d+$/.test(candidate) || candidate === '0') return 1
  const parsed = candidate.split('').reduce((total, digit) => total * 10 + (digit.charCodeAt(0) - 48), 0)
  return parsed > 0 && parsed <= 9007199254740991 ? parsed : 1
}
const visibleCategoryLevels = computed(() => Array.from(
  { length: visibleCategoryLevelCount(categoryLevelIds.value) },
  (_, index) => index + 1,
))
const visibleProductCategoryLevels = computed(() => Array.from(
  { length: visibleProductCategoryLevelCount(categoryLevelIds.value, categories.value) },
  (_, index) => index + 1,
))
const filteredCategoryParentIds = computed<UUID[]>(() => {
  const deepestSelectedCategoryId = categoryLevelIds.value.at(-1)
  return deepestSelectedCategoryId ? [deepestSelectedCategoryId] : []
})
const categoryLevelOptions = (index: number): CatalogCategory[] => {
  return categoryOptionsForLevel(categories.value, categoryLevelIds.value, index)
}
const normalizationState = computed(() => {
  const value = route.query.normalization_state
  return value === 'normalized' || value === 'legacy' || value === 'conflict' ? value : ''
})
const colorApplicabilityFilter = computed<CatalogColorApplicability | ''>(() => {
  const value = route.query.applicability
  return value === 'body' || value === 'interior' || value === 'both' ? value : ''
})
const colorActiveFilter = computed<'' | 'true' | 'false'>(() => {
  const value = route.query.is_active
  return value === 'true' || value === 'false' ? value : ''
})
const showParametersColumn = computed(() =>
  entity.value !== 'marks' && entity.value !== 'models' && entity.value !== 'attribute-groups' && entity.value !== 'colors' && entity.value !== 'units')
const missingRegistryFilter = computed(() => {
  if (entity.value === 'models' && !registryMarkId.value) {
    return 'Выберите марку, чтобы загрузить только её модели.'
  }
  if ((entity.value === 'modifications' || entity.value === 'trims') && !registryModelId.value) {
    return 'Выберите марку и модель, чтобы загрузить только модификации этой модели.'
  }
  return ''
})

const record = (value: CatalogResource | CatalogDraft): Record<string, unknown> =>
  value as Record<string, unknown>
const valueName = (value: unknown): string =>
  value && typeof value === 'object' && typeof (value as { name?: unknown }).name === 'string'
    ? (value as { name: string }).name
    : ''
const resourceTitle = (row: CatalogResource): string => {
  const item = record(row)
  if (entity.value === 'products') {
    if (typeof item.title === 'string' && item.title.trim()) {
      return item.title
    }
    const modification = item.modification
    if (modification && typeof modification === 'object') {
      const model = (modification as { model?: unknown }).model
      return [valueName(model), valueName(modification)].filter(Boolean).join(' ') || row.code
    }
    return row.code
  }
  return typeof item.name === 'string' ? item.name : row.code
}
const resourceCaption = (row: CatalogResource): string => {
  const item = record(row)
  if (entity.value === 'categories') return typeof item.canonical_path === 'string'
    ? item.canonical_path
    : 'Категория'
  if (entity.value === 'products') return valueName((item.modification as { model?: { mark?: unknown } } | undefined)?.model?.mark) || 'Объявление'
  if (entity.value === 'models') return valueName(item.mark) || 'Модель'
  if (entity.value === 'modifications') return valueName(item.model) || 'Модификация'
  if (entity.value === 'trims') {
    return [
      valueName(item.mark) || String(item.mark_name ?? ''),
      valueName(item.model) || String(item.model_name ?? ''),
      valueName(item.modification) || String(item.modification_name ?? ''),
    ].filter(Boolean).join(' / ') || 'Модификация'
  }
  return activeTab.value.singular
}
const plural = (count: number, one: string, few: string, many: string): string => {
  const mod100 = count % 100
  const mod10 = count % 10
  return `${count} ${mod100 >= 11 && mod100 <= 14 ? many : mod10 === 1 ? one : mod10 >= 2 && mod10 <= 4 ? few : many}`
}
const colorApplicabilityLabel = (value: unknown): string => ({
  body: 'Кузов',
  interior: 'Салон',
  both: 'Кузов и салон',
})[String(value)] ?? '—'
const formatDateTime = (value: unknown): string => {
  if (typeof value !== 'string' || !value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU')
}
const colorInUseMessage = (detail: Record<string, unknown>): string => {
  const total = typeof detail.used_in_products_count === 'number' ? detail.used_in_products_count : null
  const body = typeof detail.body_products_count === 'number' ? detail.body_products_count : null
  const interior = typeof detail.interior_products_count === 'number' ? detail.interior_products_count : null
  if (total === null) return 'Цвет уже используется и не может быть удалён. Деактивируйте цвет вместо удаления.'
  return [
    `Используется в объявлениях: ${total}.`,
    body !== null ? `Кузов: ${body}.` : '',
    interior !== null ? `Салон: ${interior}.` : '',
    'Деактивируйте цвет вместо удаления.',
  ].filter(Boolean).join(' ')
}
const resourceRelations = (row: CatalogResource): string => {
  const item = record(row)
  if (entity.value === 'categories') return plural(Array.isArray(item.parent_ids) ? item.parent_ids.length : 0, 'категория', 'категории', 'категорий')
  if (entity.value === 'marks') return plural(typeof item.model_count === 'number' ? item.model_count : 0, 'модель', 'модели', 'моделей')
  if (entity.value === 'models') return valueName(item.mark) || 'Марка не указана'
  if (entity.value === 'modifications') return plural(Array.isArray(item.category_ids) ? item.category_ids.length : 0, 'категория', 'категории', 'категорий')
  if (entity.value === 'trims') return valueName(item.modification) || String(item.modification_name ?? 'Модификация')
  if (entity.value === 'products') return plural(Array.isArray(item.category_ids) ? item.category_ids.length : 0, 'категория', 'категории', 'категорий')
  if (entity.value === 'attributes') return plural(typeof item.category_count === 'number' ? item.category_count : 0, 'категория', 'категории', 'категорий')
  if (entity.value === 'units') return plural(typeof item.attribute_count === 'number' ? item.attribute_count : 0, 'характеристика', 'характеристики', 'характеристик')
  if (entity.value === 'superstructures') return plural(typeof item.product_count === 'number' ? item.product_count : 0, 'комплект', 'комплекта', 'комплектов')
  return plural(typeof item.category_attribute_count === 'number' ? item.category_attribute_count : 0, 'связь', 'связи', 'связей')
}
const resourceParameters = (row: CatalogResource): string => {
  const item = record(row)
  if (entity.value === 'categories') return item.usage_metric === 'mileage_km' ? 'Пробег' : 'Моточасы'
  if (entity.value === 'products') return item.condition === 'used' ? 'С пробегом' : 'Новое'
  if (entity.value === 'modifications') {
    const from = typeof item.year_from === 'number' ? item.year_from : '…'
    const to = typeof item.year_to === 'number' ? item.year_to : '…'
    return `${from}—${to}`
  }
  if (entity.value === 'trims' || entity.value === 'superstructures') return plural(typeof item.attribute_count === 'number' ? item.attribute_count : 0, 'характеристика', 'характеристики', 'характеристик')
  if (entity.value === 'attributes') return ({
    number: 'Число',
    text: 'Текст',
    boolean: 'Да / Нет',
    select: 'Выбор из вариантов',
  } as Record<string, string>)[String(item.data_type)] ?? '—'
  return '—'
}
const statusLabel = (row: CatalogResource): string => {
  const item = record(row)
  if (entity.value === 'products') return ({
    available: 'В наличии',
    on_order: 'Под заказ',
    reserved: 'Зарезервировано',
    sold: 'Продано',
    unavailable: 'Недоступно',
  } as Record<string, string>)[String(item.sale_status)] ?? 'Недоступно'
  return item.is_active === false ? 'Неактивно' : 'Активно'
}
const statusClass = (row: CatalogResource): string => {
  const item = record(row)
  if (entity.value === 'products') return item.sale_status === 'available'
    ? 'se-status--success'
    : item.sale_status === 'reserved' || item.sale_status === 'on_order'
      ? 'se-status--warning'
      : 'se-status--muted'
  return item.is_active === false ? 'se-status--muted' : 'se-status--success'
}

const failureMessage = (error: unknown): string => {
  if (!error || typeof error !== 'object') return 'Неизвестная ошибка'
  const failure = error as {
    message?: string
    data?: {
      error?: {
        code?: string
        message?: string
        detail?: Record<string, unknown> | null
        field_errors?: Array<{ field?: string; message?: string; code?: string }>
      }
      detail?: string | {
        detail?: string
        entity_code?: string | null
        entity_name?: string | null
        dependencies?: Array<{ name?: string; code?: string; count?: number }>
      }
      message?: string
      dependencies?: Array<{ name?: string; code?: string; count?: number }>
    }
  }
  if (failure.data?.error) {
    const envelope = failure.data.error
    const fieldErrors = envelope.field_errors?.map(item =>
      [item.field, item.message || item.code].filter(Boolean).join(': ')).filter(Boolean).join('; ')
    const detail = envelope.code === 'color_in_use' && envelope.detail
      ? colorInUseMessage(envelope.detail)
      : ''
    return [envelope.message, detail, fieldErrors].filter(Boolean).join(' ')
  }
  const structured = failure.data?.detail && typeof failure.data.detail === 'object'
    ? failure.data.detail
    : null
  const dependencyText = (structured?.dependencies ?? failure.data?.dependencies)?.map(item =>
    `${item.name || item.code || 'Зависимая запись'}${item.count ? ` (${item.count})` : ''}`).join(', ')
  const subject = structured
    ? [structured.entity_name, structured.entity_code].filter(Boolean).join(' · ')
    : ''
  const detailMessage = structured?.detail
    || failure.data?.message
    || (typeof failure.data?.detail === 'string' ? failure.data.detail : '')
    || failure.message
    || 'Не удалось выполнить запрос'
  return [
    detailMessage,
    subject ? `Объект: ${subject}` : '',
    dependencyText ? `Зависимости: ${dependencyText}` : '',
  ].filter(Boolean).join(' ')
}
const failureStatus = (error: unknown): number | null => {
  if (!error || typeof error !== 'object') return null
  const value = error as { status?: unknown; statusCode?: unknown; response?: { status?: unknown } }
  if (typeof value.statusCode === 'number') return value.statusCode
  if (typeof value.status === 'number') return value.status
  return typeof value.response?.status === 'number' ? value.response.status : null
}

const loadRows = async () => {
  listController?.abort()
  if (missingRegistryFilter.value) {
    rows.value = []
    pagination.value = { page: 1, page_size: 30, total: 0, pages: 1 }
    loadError.value = ''
    loading.value = false
    return
  }
  const controller = new AbortController()
  listController = controller
  const sequence = ++listSequence
  loading.value = true
  loadError.value = ''
  try {
    if (entity.value === 'trims' && registryModelId.value) {
      const modifications = await api.listAll<CatalogModification>(
        'modifications',
        { model_id: registryModelId.value },
        controller.signal,
      )
      const lists = await Promise.all(modifications.map(async (modification) => ({
        modification,
        items: (await api.getTrimsByModification(modification.id, controller.signal)).allItems,
      })))
      if (sequence !== listSequence) return
      const normalizedSearch = search.value.trim().toLocaleLowerCase('ru-RU')
      const allRows = lists.flatMap(({ modification, items }) => {
        const model = modification.model
        const mark = model?.mark
        if (!model || !mark) return []
        return items.map((item): CatalogTrim => ({
          ...item,
          code: item.name,
          slug: '',
          modification_name: modification.name,
          model_id: modification.model_id,
          model_name: model.name,
          mark_id: mark.id,
          mark_name: mark.name,
          sort_order: 0,
        }))
      }).filter(item => !normalizedSearch
        || item.name.toLocaleLowerCase('ru-RU').includes(normalizedSearch))
        .sort((left, right) => left.name.localeCompare(right.name, 'ru-RU')
          || left.id.localeCompare(right.id))
      const page = pageFromRouteQuery(route.query.page)
      const pageSize = 30
      const offset = (page - 1) * pageSize
      rows.value = allRows.slice(offset, offset + pageSize)
      pagination.value = {
        page,
        page_size: pageSize,
        total: allRows.length,
        pages: allRows.length === 0 ? 0 : Math.ceil(allRows.length / pageSize),
      }
      return
    }
    const result = await api.list(
      entity.value,
      {
        search: search.value || undefined,
        page: pageFromRouteQuery(route.query.page),
        mark_id: entity.value === 'models' ? registryMarkId.value || undefined : undefined,
        model_id: entity.value === 'modifications' || entity.value === 'trims' ? registryModelId.value || undefined : undefined,
        attribute_group_id: entity.value === 'attributes'
          ? registryAttributeGroupId.value || undefined
          : undefined,
        level_1_id: entity.value === 'categories' || entity.value === 'products' ? categoryLevelIds.value[0] || undefined : undefined,
        level_2_id: entity.value === 'categories' || entity.value === 'products' ? categoryLevelIds.value[1] || undefined : undefined,
        level_3_id: entity.value === 'categories' || entity.value === 'products' ? categoryLevelIds.value[2] || undefined : undefined,
        level_4_id: entity.value === 'categories' || entity.value === 'products' ? categoryLevelIds.value[3] || undefined : undefined,
        level_5_id: entity.value === 'categories' || entity.value === 'products' ? categoryLevelIds.value[4] || undefined : undefined,
        sort: entity.value === 'categories' ? categorySort.value : undefined,
        normalization_state: entity.value === 'products' ? normalizationState.value || undefined : undefined,
        applicability: entity.value === 'colors' ? colorApplicabilityFilter.value || undefined : undefined,
        is_active: entity.value === 'colors' && colorActiveFilter.value ? colorActiveFilter.value === 'true' : undefined,
      },
      controller.signal,
    )
    if (sequence !== listSequence) return
    rows.value = result.items
    pagination.value = result.pagination
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    if (sequence === listSequence) loadError.value = failureMessage(error)
  } finally {
    if (sequence === listSequence) loading.value = false
  }
}
const loadSectionCounts = async () => {
  countsController?.abort()
  const controller = new AbortController()
  countsController = controller
  try {
    const nextCounts = await loadCatalogSectionCounts(api, controller.signal)
    if (!controller.signal.aborted) Object.assign(counts, nextCounts)
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === 'AbortError') return
  }
}
const loadDirectories = async () => {
  const sequence = ++directoriesSequence
  attributesLoading.value = true
  attributesErrorMessage.value = ''
  warehousesLoading.value = true
  warehousesErrorMessage.value = ''
  const [
    categoriesResult,
    marksResult,
    attributesResult,
    groupsResult,
    sellersResult,
    warehousesResult,
    bodyColorsResult,
    interiorColorsResult,
    unitsResult,
  ] = await Promise.allSettled([
    api.listAll<CatalogCategory>('categories'),
    api.listAll<CatalogMark>('marks'),
    api.listAll<CatalogAttribute>('attributes'),
    api.listAll<CatalogAttributeGroup>('attribute-groups'),
    api.listSellerCompanies(),
    api.listActiveWarehouses(),
    api.listColorOptions({ applicability: 'body' }),
    api.listColorOptions({ applicability: 'interior' }),
    api.listAll<CatalogUnit>('units'),
  ])
  if (sequence !== directoriesSequence) return
  if (categoriesResult.status === 'fulfilled') categories.value = categoriesResult.value
  if (marksResult.status === 'fulfilled') marks.value = marksResult.value
  if (attributesResult.status === 'fulfilled') attributes.value = attributesResult.value
  if (groupsResult.status === 'fulfilled') groups.value = groupsResult.value
  if (sellersResult.status === 'fulfilled') sellers.value = sellersResult.value.items
  if (warehousesResult.status === 'fulfilled') warehouses.value = warehousesResult.value
  else warehousesErrorMessage.value = 'Не удалось загрузить активные склады.'
  if (bodyColorsResult.status === 'fulfilled') bodyColors.value = bodyColorsResult.value.items
  if (interiorColorsResult.status === 'fulfilled') interiorColors.value = interiorColorsResult.value.items
  if (unitsResult.status === 'fulfilled') units.value = unitsResult.value
  const attributeDirectoryFailures = [
    attributesResult.status === 'rejected'
      ? `Характеристики: ${failureMessage(attributesResult.reason)}`
      : '',
    groupsResult.status === 'rejected'
      ? `Группы: ${failureMessage(groupsResult.reason)}`
      : '',
  ].filter(Boolean)
  attributesErrorMessage.value = attributeDirectoryFailures.join(' ')
  attributesLoading.value = false
  warehousesLoading.value = false
}
const loadWarehouses = async () => {
  warehousesLoading.value = true
  warehousesErrorMessage.value = ''
  try { warehouses.value = await api.listActiveWarehouses() }
  catch { warehousesErrorMessage.value = 'Не удалось загрузить активные склады.' }
  finally { warehousesLoading.value = false }
}
const loadRegistryModels = async () => {
  registryModels.value = []
  if ((entity.value !== 'modifications' && entity.value !== 'trims') || !registryMarkId.value) return
  registryModelsLoading.value = true
  try {
    registryModels.value = await api.listAll<CatalogModel>(
      'models',
      { mark_id: registryMarkId.value },
    )
  } catch (error: unknown) {
    loadError.value = failureMessage(error)
  } finally {
    registryModelsLoading.value = false
  }
}
watch(
  () => [entity.value, route.query.mark_id],
  () => { void loadRegistryModels() },
  { immediate: true },
)
watch(
  () => [
    entity.value,
    route.query.q,
    route.query.page,
    route.query.mark_id,
    route.query.model_id,
    route.query.modification_id,
    route.query.attribute_group_id,
    route.query.level_1_id,
    route.query.level_2_id,
    route.query.level_3_id,
    route.query.level_4_id,
    route.query.level_5_id,
    route.query.sort,
    route.query.normalization_state,
    route.query.applicability,
    route.query.is_active,
  ],
  () => { void loadRows() },
  { immediate: true },
)
onMounted(() => {
  void Promise.all([loadDirectories(), loadSectionCounts()])
})
onBeforeUnmount(() => {
  listController?.abort()
  countsController?.abort()
})

const selectEntity = (nextEntity: CatalogEntity) =>
  router.push({ query: { section: nextEntity } })
const changeRegistryMark = (value: UUID | null) => {
  const markId = value ?? ''
  return router.push({
    query: {
      section: entity.value,
      mark_id: markId || undefined,
    },
  })
}
const changeRegistryModel = (value: UUID | null) => {
  const modelId = value ?? ''
  return router.push({
    query: {
      section: entity.value,
      mark_id: registryMarkId.value || undefined,
      model_id: modelId || undefined,
    },
  })
}
const changeRegistryAttributeGroup = (value: UUID | null) => {
  const attributeGroupId = value ?? ''
  return router.push({
    query: {
      section: entity.value,
      attribute_group_id: attributeGroupId || undefined,
    },
  })
}
const categoryFilterQuery = (
  levels: readonly UUID[] = categoryLevelIds.value,
): Record<string, string | undefined> => buildCategoryRegistryQuery(levels, categorySort.value)
const productFilterQuery = (
  levels: readonly UUID[] = categoryLevelIds.value,
): Record<string, string | undefined> => buildProductRegistryQuery(levels, normalizationState.value)
const changeCategoryLevel = (index: number, selectedId: UUID | null) => {
  const levels = replaceCategoryLevel(categoryLevelIds.value, index, selectedId)
  return router.push({
    query: {
      section: entity.value,
      q: search.value || undefined,
      ...categoryFilterQuery(levels),
    },
  })
}
const changeProductCategoryLevel = (index: number, selectedId: UUID | null) => {
  const levels = replaceCategoryLevel(categoryLevelIds.value, index, selectedId)
  return router.push({
    query: {
      section: entity.value,
      q: search.value || undefined,
      ...productFilterQuery(levels),
    },
  })
}
const changeCategorySort = (event: Event) => router.push({
  query: {
    section: entity.value,
    q: search.value || undefined,
    ...buildCategoryRegistryQuery(
      categoryLevelIds.value,
      categorySortFromQuery((event.target as HTMLSelectElement).value),
    ),
  },
})
const changeNormalizationState = (event: Event) => router.push({
  query: {
    section: entity.value,
    q: search.value || undefined,
    ...buildProductRegistryQuery(
      categoryLevelIds.value,
      (event.target as HTMLSelectElement).value as typeof normalizationState.value,
    ),
  },
})
const changeColorApplicabilityFilter = (event: Event) => router.push({
  query: {
    section: entity.value,
    q: search.value || undefined,
    applicability: (event.target as HTMLSelectElement).value || undefined,
    is_active: colorActiveFilter.value || undefined,
  },
})
const changeColorActiveFilter = (event: Event) => router.push({
  query: {
    section: entity.value,
    q: search.value || undefined,
    applicability: colorApplicabilityFilter.value || undefined,
    is_active: (event.target as HTMLSelectElement).value || undefined,
  },
})
const applySearch = () => router.push({
  query: {
    section: entity.value,
    q: searchInput.value.trim() || undefined,
    mark_id: registryMarkId.value || undefined,
    model_id: registryModelId.value || undefined,
    attribute_group_id: entity.value === 'attributes'
      ? registryAttributeGroupId.value || undefined
      : undefined,
    ...(entity.value === 'categories' ? categoryFilterQuery() : {}),
    ...(entity.value === 'products' ? productFilterQuery() : {}),
    applicability: entity.value === 'colors' ? colorApplicabilityFilter.value || undefined : undefined,
    is_active: entity.value === 'colors' ? colorActiveFilter.value || undefined : undefined,
  },
})
const changePage = (page: number) => router.push({
  query: {
    section: entity.value,
    q: search.value || undefined,
    page: page > 1 ? String(page) : undefined,
    mark_id: registryMarkId.value || undefined,
    model_id: registryModelId.value || undefined,
    attribute_group_id: entity.value === 'attributes'
      ? registryAttributeGroupId.value || undefined
      : undefined,
    ...(entity.value === 'categories' ? categoryFilterQuery() : {}),
    ...(entity.value === 'products' ? productFilterQuery() : {}),
    applicability: entity.value === 'colors' ? colorApplicabilityFilter.value || undefined : undefined,
    is_active: entity.value === 'colors' ? colorActiveFilter.value || undefined : undefined,
  },
})

const createDraft = (): CatalogDraft => {
  const common = { code: '', name: '', is_active: true }
  if (entity.value === 'products') return {
    code: '',
    modification_id: '',
    selected_mark_id: '',
    selected_model_id: '',
    category_ids: [],
    price: '',
    special_price: '',
    price_on_request: false,
    price_from: '',
    warehouse_id: '',
    currency_code: 'RUB',
    manufacture_year: null,
    condition: 'new',
    owners_count: null,
    no_vin: false,
    mileage_km: null,
    engine_hours: null,
    sale_status: 'unavailable',
    publication_status: 'draft',
    seller_company_id: '',
    body_color_id: '',
    interior_color_id: '',
    description: '',
    vin: '',
    chassis_vin: '',
    superstructure_vin: '',
    images: [],
    compatible_attachments: [],
    components: [],
    creation_kind: 'vehicle',
    attachment_create_mode: null,
  }
  if (entity.value === 'categories') return {
    ...common,
    usage_metric: 'engine_hours',
    sort_order: 0,
    is_attachment_category: false,
    is_visible_in_catalog: true,
    parent_ids: filteredCategoryParentIds.value,
    attribute_links: [],
    image_url: null,
  }
  if (entity.value === 'models') return { ...common, mark_id: registryMarkId.value || '', category_id: '' }
  if (entity.value === 'modifications') return {
    ...common,
    selected_mark_id: registryMarkId.value || '',
    selected_model_id: registryModelId.value || '',
    model_id: registryModelId.value || '',
    year_from: null,
    year_to: null,
    category_ids: [],
    attribute_values: [],
  }
  if (entity.value === 'trims') return {
    ...common,
    selected_mark_id: registryMarkId.value || '',
    selected_model_id: registryModelId.value || '',
    modification_id: '',
    sort_order: 0,
    trim_attributes: [],
    trim_attribute_values: [],
  }
  if (entity.value === 'superstructures') return {
    ...common,
    attributes: [],
    category_ids: [],
  }
  if (entity.value === 'attributes') return {
    ...common,
    data_type: 'text',
    filter_kind: 'search',
    unit: '',
    unit_id: null,
    attribute_group_id: registryAttributeGroupId.value || null,
    options: [],
  }
  if (entity.value === 'attribute-groups') return { ...common, sort_order: 0, attribute_ids: [] }
  if (entity.value === 'colors') return { ...common, applicability: 'body' }
  return common
}
const resetMedia = () => {
  pendingFiles.value = []
  removedImageIds.value = new Set()
  categoryImageRemoved.value = false
}
const resetCreateMediaCheckpoint = () => {
  createIdempotencyKey.value = ''
  createdResourceCheckpoint.value = null
}
const resetRelationSnapshots = () => {
  initialAttachmentSnapshot.value = '[]'
  initialComponentSnapshot.value = '[]'
}
const resetSelectedProductTrimAttributes = () => {
  selectedProductTrimRequest += 1
  selectedProductTrimAttributes.value = []
  selectedProductTrimAttributesLoading.value = false
  selectedProductTrimAttributesErrorMessage.value = ''
}
const resetTrimState = () => {
  trimAttributeCandidateController?.abort()
  trimAttributeCandidateController = null
  trimAttributeCandidateRequest += 1
  trims.value = []
  trimRequired.value = false
  resetSelectedProductTrimAttributes()
  trimAttributeCandidateGroups.value = []
  trimAttributeCandidatesErrorMessage.value = ''
  trimAttributeCandidatesLoading.value = false
  trimStateEtag.value = ''
  initialTrimAttributesSnapshot.value = '[]'
  initialTrimAttributeValuesSnapshot.value = '[]'
}
const openCreate = async () => {
  drawerSession.value += 1
  drawerMode.value = 'create'
  resetCreateMediaCheckpoint()
  createIdempotencyKey.value = crypto.randomUUID()
  draft.value = createDraft()
  initialSnapshot.value = JSON.stringify(draft.value)
  currentEtag.value = ''
  saveError.value = ''
  versionConflict.value = false
  selectedModification.value = null
  resetTrimState()
  dependent.clearModels()
  dependent.clearModifications()
  if (entity.value === 'modifications' && registryMarkId.value) {
    await dependent.loadModels(registryMarkId.value)
  }
  if (entity.value === 'trims' || entity.value === 'superstructures') {
    if (registryMarkId.value) await dependent.loadModels(registryMarkId.value)
    if (registryModelId.value) await dependent.loadModifications(registryModelId.value)
  }
  if (entity.value === 'products' && draft.value.selected_mark_id) {
    await dependent.loadModels(draft.value.selected_mark_id as UUID)
  }
  resetMedia()
  resetRelationSnapshots()
  drawerOpen.value = true
}
const hydrateCascade = async (resource: CatalogResource) => {
  const item = record(resource)
  if (entity.value === 'models') {
    const categoryId = (item.category_id as UUID | undefined) || (item.category as { id?: UUID } | undefined)?.id || ''
    draft.value = {
      ...draft.value,
      category_id: categoryId,
    }
    return
  }
  if (entity.value === 'modifications') {
    const model = item.model as { id?: UUID; mark?: { id?: UUID } } | undefined
    if (!model?.id || !model.mark?.id) return
    draft.value = { ...draft.value, selected_mark_id: model.mark.id, selected_model_id: model.id }
    await dependent.loadModels(model.mark.id)
    return
  }
  if (entity.value === 'products') {
    const isKit = (Boolean(item.superstructure_id) && Boolean(item.model_id)) || Boolean(item.is_kit)
    if (isKit) {
      const model = item.model as { id?: UUID; mark?: { id?: UUID } } | undefined
      const modification = item.modification as {
        id?: UUID
        model?: { id?: UUID; mark?: { id?: UUID } }
      } | undefined
      const markId = modification?.model?.mark?.id || model?.mark?.id || (typeof item.mark_id === 'string' ? item.mark_id as UUID : '')
      const modelId = modification?.model?.id || model?.id || (typeof item.model_id === 'string' ? item.model_id as UUID : '')
      const modificationId = modification?.id || (typeof item.modification_id === 'string' ? item.modification_id as UUID : '')
      draft.value = {
        ...draft.value,
        is_kit: true,
        selected_mark_id: markId,
        selected_model_id: modelId,
        model_id: modelId,
        modification_id: modificationId || null,
        chassis_values: Array.isArray(item.chassis_values) ? item.chassis_values : [],
        superstructure_values: Array.isArray(item.superstructure_values) ? item.superstructure_values : [],
      }
      if (markId) await dependent.loadModels(markId)
      if (modelId) {
        await dependent.loadModifications(modelId)
        if (modificationId) await loadSelectedModification(modificationId)
      }
      return
    }
    const modification = item.modification as {
      id?: UUID
      model?: { id?: UUID; mark?: { id?: UUID } }
    } | undefined
    const markId = modification?.model?.mark?.id
    const modelId = modification?.model?.id
    if (!markId || !modelId || !modification?.id) return
    draft.value = { ...draft.value, selected_mark_id: markId, selected_model_id: modelId }
    await dependent.loadModels(markId)
    await dependent.loadModifications(modelId)
    await loadSelectedModification(modification.id)
    return
  }
  if (entity.value === 'trims') {
    const modification = item.modification as {
      id?: UUID
      model?: { id?: UUID; mark?: { id?: UUID } }
    } | undefined
    const markId = modification?.model?.mark?.id || (typeof item.mark_id === 'string' ? item.mark_id as UUID : '')
    const modelId = modification?.model?.id || (typeof item.model_id === 'string' ? item.model_id as UUID : '')
    const modificationId = modification?.id || (typeof item.modification_id === 'string' ? item.modification_id as UUID : '')
    if (!markId || !modelId || !modificationId) return
    draft.value = { ...draft.value, selected_mark_id: markId, selected_model_id: modelId, modification_id: modificationId }
    await dependent.loadModels(markId)
    await dependent.loadModifications(modelId)
    await loadSelectedModification(modificationId)
    await loadTrimAttributes(resource.id)
    return
  }
  if (entity.value === 'superstructures') {
    draft.value = {
      ...draft.value,
      attributes: Array.isArray(item.attributes) ? item.attributes : [],
      category_ids: Array.isArray(item.category_ids) ? item.category_ids : [],
    }
    return
  }
}
const openEdit = async (id: UUID) => {
  drawerSession.value += 1
  drawerMode.value = 'edit'
  resetCreateMediaCheckpoint()
  saving.value = true
  saveError.value = ''
  versionConflict.value = false
  resetMedia()
  resetSelectedProductTrimAttributes()
  try {
    const response = await api.get(entity.value, id)
    let hydrated = structuredClone(response.data) as CatalogDraft
    if (entity.value === 'products') {
      const isOrdinary = !hydrated.superstructure_id && !hydrated.is_kit && !hydrated.is_attachment
      if (isOrdinary) {
        const attachments = await api.getProductAttachments(id)
        hydrated = {
          ...hydrated,
          compatible_attachments: attachments.data.items,
        }
        initialAttachmentSnapshot.value = JSON.stringify(attachments.data.items)
      } else {
        hydrated = {
          ...hydrated,
          compatible_attachments: [],
        }
        initialAttachmentSnapshot.value = JSON.stringify([])
      }
    } else resetRelationSnapshots()
    draft.value = hydrated
    currentEtag.value = response.etag
    selectedModification.value = null
    await hydrateCascade(response.data)
    initialSnapshot.value = JSON.stringify(draft.value)
    drawerOpen.value = true
  } catch (error: unknown) {
    toast.error(failureMessage(error))
  } finally {
    saving.value = false
  }
}
const closeDrawer = () => {
  drawerOpen.value = false
  saveError.value = ''
  versionConflict.value = false
  resetMedia()
  resetCreateMediaCheckpoint()
  resetTrimState()
}
const dirty = computed(() =>
  JSON.stringify(draft.value) !== initialSnapshot.value
  || pendingFiles.value.length > 0
  || removedImageIds.value.size > 0
  || categoryImageRemoved.value)
const drawerTitle = computed(() => drawerMode.value === 'create'
  ? activeTab.value.createLabel
  : resourceTitle(draft.value as CatalogResource))
const drawerSubtitle = computed(() => drawerMode.value === 'edit'
  ? `Код: ${draft.value.code}`
  : 'Заполните обязательные поля')
const saveDisabled = computed(() => {
  if (!canWrite.value || (entity.value !== 'trims' && !draft.value.code.trim())) return true
  if (entity.value !== 'products' && !String(draft.value.name ?? '').trim()) return true
  if (isCatalogAttributeOptionsSaveInvalid({
    entity: entity.value,
    dataType: draft.value.data_type,
    options: draft.value.options,
  })) return true
  if (
    entity.value === 'attributes'
    && !isCatalogAttributeFilterCompatible(draft.value.data_type, draft.value.filter_kind)
  ) return true
  if (entity.value === 'models' && (!draft.value.mark_id || !draft.value.category_id)) return true
  if (entity.value === 'superstructures') {
    const attrs = Array.isArray(draft.value.attributes)
      ? draft.value.attributes as CatalogSuperstructureAttribute[]
      : []
    const visibleCount = attrs.filter(a => a.is_visible).length
    if (visibleCount > 6) return true
    if (attrs.some(a => normalizeCatalogInteger(a.sort_order) === null)) return true
  }
  if (entity.value === 'trims') {
    if (!draft.value.modification_id) return true
    if (drawerMode.value === 'create') return false
    if (normalizeCatalogInteger(draft.value.sort_order) === null) return true
    const assignments = Array.isArray(draft.value.trim_attributes)
      ? draft.value.trim_attributes as CatalogTrimAttributeAssignment[]
      : []
    if (assignments.some(link => normalizeCatalogInteger(link.sort_order) === null)) return true
  }
  if (
    (entity.value === 'categories' || entity.value === 'attribute-groups')
    && normalizeCatalogInteger(draft.value.sort_order) === null
  ) return true
  if (entity.value === 'categories' && Array.isArray(draft.value.attribute_links)) {
    const invalidSortOrder = draft.value.attribute_links.some(link =>
      normalizeCatalogInteger((link as Record<string, unknown>).sort_order) === null)
    if (invalidSortOrder) return true
  }
  if (entity.value === 'modifications') {
    if (!draft.value.model_id) return true
    if (!Array.isArray(draft.value.category_ids) || draft.value.category_ids.length === 0) return true
    const yearFromEmpty = draft.value.year_from === null || draft.value.year_from === '' || draft.value.year_from === undefined
    const yearToEmpty = draft.value.year_to === null || draft.value.year_to === '' || draft.value.year_to === undefined
    const yearFrom = yearFromEmpty
      ? null
      : normalizeCatalogInteger(draft.value.year_from, { min: 1900, max: 2200 })
    const yearTo = yearToEmpty
      ? null
      : normalizeCatalogInteger(draft.value.year_to, { min: 1900, max: 2200 })
    if (!yearFromEmpty && yearFrom === null) return true
    if (!yearToEmpty && yearTo === null) return true
    if (yearFrom !== null && yearTo !== null && yearFrom > yearTo) return true
  }
  if (entity.value === 'products') {
    const isKit = Boolean(draft.value.is_kit)
      || (draft.value.creation_kind === 'attachment' && draft.value.attachment_create_mode === 'kit')
      || (Boolean(draft.value.superstructure_id) && Boolean(draft.value.model_id))
    const requiresWarehouse = draft.value.no_vin !== true
      && draft.value.sale_status === 'available'
    if (requiresWarehouse && (!draft.value.warehouse_id || warehousesErrorMessage.value)) return true
    const attachments = Array.isArray(draft.value.compatible_attachments)
      ? draft.value.compatible_attachments as CatalogProductAttachmentLink[]
      : []
    if (draft.value.is_attachment === true && attachments.length > 0) return true
    if (attachments.some(item => item.attachment_product_id === draft.value.id)) return true
    if (isKit) {
      if (!draft.value.model_id) return true
      if (!Array.isArray(draft.value.category_ids) || draft.value.category_ids.length === 0) return true
      if (!draft.value.superstructure_id) return true
      if (draft.value.no_vin !== true && !String(draft.value.chassis_vin ?? '').trim()) return true
      const isExisting = draft.value.superstructure_source_mode === 'existing'
        || (draft.value.superstructure_source_mode !== 'manual' && Boolean(draft.value.superstructure_source_product_id))
      if (isExisting) {
        if (!draft.value.superstructure_source_product_id) return true
      } else {
        if (!String(draft.value.superstructure_name ?? '').trim()) return true
        if (!String(draft.value.superstructure_manufacturer ?? '').trim()) return true
      }
      const selectedCategoryIds = draft.value.category_ids as UUID[]
      const selectedCategories = categories.value.filter(category => selectedCategoryIds.includes(category.id))
      if (selectedCategories.length !== selectedCategoryIds.length) return true
      if (selectedCategories.some(category => category.is_active === false)) return true
      if (!productCategoriesShareClassification(selectedCategoryIds, categories.value)) return true
      if (selectedCategoryIds.some(categoryId =>
        categoryIsInAttachmentBranch(categoryId, categories.value))) return true
    } else {
      const expectsAttachment = draft.value.creation_kind === 'attachment'
        || (drawerMode.value === 'edit' && draft.value.is_attachment === true)
      if (expectsAttachment && !draft.value.superstructure_id) return true
      if (!draft.value.modification_id || !Array.isArray(draft.value.category_ids) || draft.value.category_ids.length === 0) return true
      if (trimRequired.value && !draft.value.trim_id) return true
      const selectedCategoryIds = draft.value.category_ids as UUID[]
      const selectedCategories = categories.value.filter(category => selectedCategoryIds.includes(category.id))
      if (selectedCategories.length !== selectedCategoryIds.length) return true
      if (selectedCategories.some(category => category.is_active === false)) return true
      if (!productCategoriesShareClassification(selectedCategoryIds, categories.value)) return true
      if (selectedCategoryIds.some(categoryId =>
        categoryIsInAttachmentBranch(categoryId, categories.value) !== expectsAttachment)) return true
    }
    const hasPrice = typeof draft.value.price === 'string' && draft.value.price.trim() !== ''
    if (hasPrice && !isPositiveCatalogPrice(draft.value.price)) return true
    const hasSpecialPrice = typeof draft.value.special_price === 'string'
      && draft.value.special_price.trim() !== ''
    const specialPrice = normalizeCatalogPrice(draft.value.special_price)
    if (hasSpecialPrice && !isPositiveCatalogPrice(draft.value.special_price)) return true
    if (specialPrice !== null) {
      const basePrice = normalizeCatalogPrice(draft.value.price)
      if (basePrice === null || Number(specialPrice) >= Number(basePrice)) return true
    }
    const priceOnRequest = draft.value.price_on_request === true
    const priceFromPresent = typeof draft.value.price_from === 'string'
      && draft.value.price_from.trim() !== ''
    if (priceOnRequest && priceFromPresent && !isPositiveCatalogPrice(draft.value.price_from)) return true
    if (draft.value.sale_status === 'on_order'
      && !priceOnRequest
      && !isPositiveCatalogPrice(draft.value.price)) return true
    if (true) {
      if (draft.value.condition !== 'new' && draft.value.condition !== 'used') return true
      const metrics = new Set(categories.value
        .filter(category => (draft.value.category_ids as UUID[]).includes(category.id))
        .map(category => category.usage_metric))
      if (metrics.size !== 1) return true
      if (draft.value.condition === 'used') {
        if (!Number.isSafeInteger(draft.value.owners_count) || (draft.value.owners_count as number) < 0) return true
        const metric = [...metrics][0]
        if (metric === 'mileage_km' && normalizeCatalogInteger(draft.value.mileage_km) === null) return true
        if (metric === 'engine_hours' && normalizeCatalogInteger(draft.value.engine_hours) === null) return true
      }
      const manufactureYearEmpty = draft.value.manufacture_year === null
        || draft.value.manufacture_year === ''
        || draft.value.manufacture_year === undefined
      if (!manufactureYearEmpty
        && normalizeCatalogInteger(draft.value.manufacture_year, { min: 1900, max: 2200 }) === null) return true
      if (draft.value.no_vin !== true && !String(draft.value.vin ?? '').trim()) return true
      if (String(draft.value.vin ?? '').length > 17) return true
    }
  }
  return false
})

const sanitizedPayload = (): Record<string, unknown> =>
  buildCatalogCorrectionPayload({
    entity: entity.value,
    mode: drawerMode.value,
    draft: draft.value,
    categories: categories.value,
  })

const visibleImages = computed<RegistryImage[]>(() => {
  const images = Array.isArray(draft.value.images) ? draft.value.images as RegistryImage[] : []
  return [...images]
    .filter(image => !removedImageIds.value.has(image.id))
    .sort((left, right) => left.sort_order - right.sort_order)
})
const categoryImageUrl = computed(() =>
  categoryImageRemoved.value ? null : typeof draft.value.image_url === 'string' ? draft.value.image_url : null)
const addPendingFiles = (files: File[]) => {
  pendingFiles.value.push(...files)
}
const removeDraftImage = (imageId: UUID) => {
  removedImageIds.value = new Set([...removedImageIds.value, imageId])
}
const replaceImages = (images: RegistryImage[]) => {
  draft.value = { ...draft.value, images }
}
const moveDraftImage = (imageId: UUID, direction: -1 | 1) => {
  const images = [...visibleImages.value]
  const index = images.findIndex(image => image.id === imageId)
  const target = index + direction
  if (index < 0 || target < 0 || target >= images.length) return
  ;[images[index], images[target]] = [images[target]!, images[index]!]
  replaceImages(images.map((image, position) => ({ ...image, sort_order: position })))
}
const makePrimary = (imageId: UUID) =>
  replaceImages(visibleImages.value.map(image => ({ ...image, is_primary: image.id === imageId })))
const changeImageDescription = (imageId: UUID, value: string) =>
  replaceImages(visibleImages.value.map(image =>
    image.id === imageId ? { ...image, alt_text: value || null } : image))

const syncMedia = async (
  resource: CatalogResource,
  etag: string,
  onProgress: (etag: string) => void = () => {},
): Promise<string> => {
  let nextEtag = etag
  const checkpoint = (value: string) => {
    nextEtag = value
    currentEtag.value = value
    onProgress(value)
  }
  if (entity.value === 'categories') {
    if (categoryImageRemoved.value && draft.value.image_url) {
      const response = await api.deleteCategoryImage(resource.id, nextEtag)
      categoryImageRemoved.value = false
      draft.value = { ...draft.value, image_url: null }
      checkpoint(response.etag)
    }
    const file = pendingFiles.value[0]
    if (file) {
      const response = await api.uploadCategoryImage(resource.id, file, nextEtag)
      pendingFiles.value.splice(0, 1)
      checkpoint(response.etag)
    }
    return nextEtag
  }
  if (entity.value !== 'products') return nextEtag
  for (const imageId of [...removedImageIds.value]) {
    const response = await api.deleteProductImage(resource.id, imageId, nextEtag)
    removedImageIds.value = new Set([...removedImageIds.value].filter(id => id !== imageId))
    replaceImages((Array.isArray(draft.value.images) ? draft.value.images as RegistryImage[] : [])
      .filter(image => image.id !== imageId))
    checkpoint(response.etag)
  }
  for (const image of [...visibleImages.value]) {
    const response = await api.updateProductImage(
      resource.id,
      image.id,
      {
        alt_text: image.alt_text,
        is_primary: image.is_primary,
        sort_order: image.sort_order,
      },
      nextEtag,
    )
    replaceImages((Array.isArray(draft.value.images) ? draft.value.images as RegistryImage[] : [])
      .map(item => item.id === image.id ? response.data : item))
    checkpoint(response.etag)
  }
  for (const file of [...pendingFiles.value]) {
    const response = await api.uploadProductImage(resource.id, file, nextEtag)
    const uploadedImage = response.data.image
    if (!uploadedImage) throw new Error('API реестра не вернул загруженное изображение')
    const position = pendingFiles.value.indexOf(file)
    if (position >= 0) pendingFiles.value.splice(position, 1)
    const images = Array.isArray(draft.value.images) ? draft.value.images as RegistryImage[] : []
    replaceImages([...images, uploadedImage])
    checkpoint(response.etag)
  }
  return nextEtag
}
const currentAttachmentLinks = (): CatalogProductAttachmentLink[] =>
  Array.isArray(draft.value.compatible_attachments)
    ? draft.value.compatible_attachments as CatalogProductAttachmentLink[]
    : []
const attachmentPayload = (): CatalogProductAttachmentInput[] =>
  currentAttachmentLinks().map((item, position) => ({
    attachment_product_id: item.attachment_product_id,
    position,
  }))
const syncProductRelations = async (productId: UUID, etag: string): Promise<string> => {
  const attachmentsChanged = JSON.stringify(currentAttachmentLinks()) !== initialAttachmentSnapshot.value
  return syncCatalogProductRelations({
    initialEtag: etag,
    attachmentsChanged,
    replaceAttachments: nextEtag => api.replaceProductAttachments(
      productId,
      attachmentPayload(),
      nextEtag,
    ),
    commitEtag: (nextEtag) => { currentEtag.value = nextEtag },
  })
}
const createCurrentResource = (idempotencyKey: string) => {
  const payload = sanitizedPayload()
  if (entity.value !== 'products') return api.create(entity.value, payload, idempotencyKey)
  const isOrdinary = !draft.value.superstructure_id && !draft.value.is_kit && !draft.value.is_attachment
  return api.createProduct({
    ...payload,
    ...(isOrdinary ? { compatible_attachments: attachmentPayload() } : {}),
  } as CatalogProductCreateRequest, idempotencyKey)
}
const save = async () => {
  if (saveDisabled.value || saving.value) return
  saving.value = true
  saveError.value = ''
  versionConflict.value = false
  let createdTrimThisSave = false
  try {
    if (drawerMode.value === 'create') {
      if (entity.value === 'trims') {
        const payload = sanitizedPayload()
        if (typeof payload.modification_id !== 'string' || typeof payload.name !== 'string') {
          throw new Error('Укажите модификацию и название комплектации')
        }
        const created = await api.createTrim({
          modification_id: payload.modification_id as UUID,
          name: payload.name,
        }, createIdempotencyKey.value)
        const stagedAssignments = trimAttributeAssignments()
        const stagedValues = trimAttributeValues()
        const fresh = await api.get<CatalogTrim>('trims', created.id)
        currentEtag.value = fresh.etag
        drawerMode.value = 'edit'
        draft.value = {
          ...draft.value,
          ...fresh.data,
          trim_attributes: [],
          trim_attribute_values: [],
        }
        await hydrateCascade(fresh.data)
        const persistedScalarDraft = {
          ...draft.value,
          trim_attributes: [],
          trim_attribute_values: [],
        }
        initialSnapshot.value = JSON.stringify(persistedScalarDraft)
        draft.value = {
          ...persistedScalarDraft,
          trim_attributes: stagedAssignments,
          trim_attribute_values: stagedValues,
        }
        resetCreateMediaCheckpoint()
        await syncTrimAttributes(fresh.data.id)
        createdTrimThisSave = true
      } else {
        const completed = await resumeCatalogCreateMedia({
          checkpoint: createdResourceCheckpoint.value,
          idempotencyKey: createIdempotencyKey.value,
          create: createCurrentResource,
          syncMedia,
          commit: (checkpoint) => {
            createdResourceCheckpoint.value = checkpoint
            currentEtag.value = checkpoint.etag
            draft.value = { ...draft.value, id: checkpoint.resource.id }
          },
        })
        currentEtag.value = completed.etag
      }
    } else {
      const response = await api.update(entity.value, draft.value.id!, sanitizedPayload(), currentEtag.value)
      currentEtag.value = await syncMedia(response.data, response.etag)
      if (entity.value === 'trims') {
        trimStateEtag.value = currentEtag.value
        await syncTrimAttributes(response.data.id)
      }
      if (entity.value === 'products') {
        const isOrdinary = !draft.value.superstructure_id && !draft.value.is_kit && !draft.value.is_attachment
        if (isOrdinary) {
          currentEtag.value = await syncProductRelations(response.data.id, currentEtag.value)
        }
      }
    }
    toast.success(createdTrimThisSave
      ? 'Комплектация создана'
      : drawerMode.value === 'create' ? 'Запись создана' : 'Изменения сохранены')
    closeDrawer()
    await Promise.all([loadRows(), loadDirectories(), loadSectionCounts()])
  } catch (error: unknown) {
    const failure = failureMessage(error)
    const status = failureStatus(error)
    if (entity.value === 'trims' && draft.value.id && status !== 412) {
      try {
        await refreshTrimAttributeCheckpoint(draft.value.id)
      } catch {
        // Keep the last acknowledged checkpoint when the recovery GET also fails.
      }
    }
    if (status === 412 && draft.value.id) {
      // Keep the backend detail visible and offer an explicit reload instead of
      // silently retrying a stale mutation.
      versionConflict.value = true
      saveError.value = `${failure} Данные на сервере изменились; загрузите актуальную версию. Локальные правки не удалены.`
    } else if (status === 409 && draft.value.id) {
      versionConflict.value = true
      saveError.value = `${failure} Локальные правки не удалены.`
    } else if (drawerMode.value === 'create' && createdResourceCheckpoint.value) {
      saveError.value = `Объявление уже создано. Не удалось завершить загрузку фотографий: ${failure}. Повторное сохранение продолжит загрузку без повторного создания объявления.`
    } else {
      saveError.value = failure
    }
  } finally {
    saving.value = false
  }
}
const deleteModalOpen = ref(false)
const deleteEntity = ref<CatalogEntity | string>('categories')
const deleteEntityId = ref('')
const deleteEntityName = ref('')
const deleteEntityCode = ref('')
const deleteEntityEtag = ref('')

const openCascadeDeleteFromDrawer = () => {
  if (!draft.value.id || !canWrite.value || saving.value) return
  deleteEntity.value = entity.value
  deleteEntityId.value = draft.value.id
  deleteEntityName.value = typeof draft.value.name === 'string' ? draft.value.name : ''
  deleteEntityCode.value = typeof draft.value.code === 'string' ? draft.value.code : ''
  deleteEntityEtag.value = currentEtag.value
  deleteModalOpen.value = true
}

const onCascadeDeleted = async () => {
  deleteModalOpen.value = false
  if (drawerOpen.value) {
    closeDrawer()
  }
  await Promise.all([loadRows(), loadDirectories(), loadSectionCounts()])
}

const toggleColor = async (row: CatalogResource) => {
  if (entity.value !== 'colors' || !canWrite.value || saving.value) return
  saving.value = true
  try {
    const fresh = await api.getColor(row.id)
    await api.updateColor(row.id, { is_active: !fresh.data.is_active }, fresh.etag)
    toast.success(fresh.data.is_active ? 'Цвет деактивирован' : 'Цвет активирован')
    await Promise.all([loadRows(), loadDirectories(), loadSectionCounts()])
  } catch (error: unknown) {
    toast.error(failureMessage(error))
  } finally {
    saving.value = false
  }
}

const openMergeModal = async (row: CatalogResource) => {
  if (entity.value !== 'units' || !canWrite.value || saving.value) return
  saving.value = true
  try {
    const fresh = await api.get<CatalogUnit>('units', row.id)
    mergeSourceUnit.value = fresh.data
    mergeSourceEtag.value = fresh.etag
    mergeModalOpen.value = true
  } catch (error: unknown) {
    toast.error(failureMessage(error))
  } finally {
    saving.value = false
  }
}

const confirmMerge = async (targetUnitId: UUID) => {
  if (!mergeSourceUnit.value || !mergeSourceEtag.value) return
  saving.value = true
  try {
    await api.mergeUnit(mergeSourceUnit.value.id, targetUnitId, mergeSourceEtag.value)
    toast.success('Единицы измерения успешно объединены')
    mergeModalOpen.value = false
    await Promise.all([loadRows(), loadDirectories(), loadSectionCounts()])
  } catch (error: unknown) {
    toast.error(failureMessage(error))
  } finally {
    saving.value = false
  }
}
const reloadCurrent = async () => {
  if (!draft.value.id || saving.value) return
  await openEdit(draft.value.id)
}
const loadTrimsForModification = async (modificationId: UUID | null) => {
  trims.value = []
  trimRequired.value = false
  if (!modificationId) return
  trimsLoading.value = true
  try {
    const response = await api.getTrimsByModification(modificationId)
    if (draft.value.modification_id === modificationId) {
      const currentArchived = response.allItems.find(item =>
        item.id === draft.value.trim_id && !item.is_active)
      trims.value = currentArchived ? [...response.items, currentArchived] : response.items
      trimRequired.value = response.required
    }
  } catch (error: unknown) {
    saveError.value = failureMessage(error)
  } finally {
    trimsLoading.value = false
  }
}
const loadSelectedProductTrimAttributes = async (trimId: UUID | null) => {
  const requestId = ++selectedProductTrimRequest
  selectedProductTrimAttributes.value = []
  selectedProductTrimAttributesErrorMessage.value = ''
  selectedProductTrimAttributesLoading.value = Boolean(trimId)
  if (!trimId) return
  try {
    const response = await api.getTrimAttributes(trimId)
    if (
      requestId === selectedProductTrimRequest
      && entity.value === 'products'
      && draft.value.trim_id === trimId
    ) {
      selectedProductTrimAttributes.value = response.data.items
    }
  } catch (error: unknown) {
    if (requestId === selectedProductTrimRequest && draft.value.trim_id === trimId) {
      selectedProductTrimAttributesErrorMessage.value = failureMessage(error)
    }
  } finally {
    if (requestId === selectedProductTrimRequest) {
      selectedProductTrimAttributesLoading.value = false
    }
  }
}
const loadTrimAttributeCandidates = async (modificationId: UUID | null) => {
  trimAttributeCandidateController?.abort()
  const requestId = ++trimAttributeCandidateRequest
  trimAttributeCandidateGroups.value = []
  trimAttributeCandidatesErrorMessage.value = ''
  trimAttributeCandidatesLoading.value = Boolean(modificationId)
  if (!modificationId) return
  const controller = new AbortController()
  trimAttributeCandidateController = controller
  const trimId = entity.value === 'trims'
    && drawerMode.value === 'edit'
    && typeof draft.value.id === 'string'
    && isUuid(draft.value.id)
    ? draft.value.id
    : null
  try {
    const response = trimId
      ? await api.getTrimAttributeCandidates(trimId, controller.signal)
      : await api.getTrimAttributeCandidatesByModification(modificationId, controller.signal)
    if (
      requestId === trimAttributeCandidateRequest
      && entity.value === 'trims'
      && draft.value.modification_id === modificationId
      && (!trimId || draft.value.id === trimId)
    ) {
      trimAttributeCandidateGroups.value = groupTrimAttributeCandidates(response.candidates)
    }
  } catch (error: unknown) {
    if (
      requestId === trimAttributeCandidateRequest
      && !(error instanceof Error && error.name === 'AbortError')
    ) {
      trimAttributeCandidatesErrorMessage.value = failureMessage(error)
    }
  } finally {
    if (requestId === trimAttributeCandidateRequest) {
      trimAttributeCandidatesLoading.value = false
      trimAttributeCandidateController = null
    }
  }
}
const trimAttributeAssignments = (): CatalogTrimAttributeAssignment[] =>
  (Array.isArray(draft.value.trim_attributes)
    ? draft.value.trim_attributes as CatalogTrimAttributeAssignment[]
    : []).map((assignment) => {
      const candidate = trimAttributeCandidateGroups.value
        .flatMap(group => group.attributes)
        .find(item => item.attribute_id === assignment.attribute_id)
      return candidate
        ? {
            ...assignment,
            attribute_code: assignment.attribute_code ?? candidate.attribute_code,
            attribute_name: assignment.attribute_name ?? candidate.attribute_name,
            data_type: assignment.data_type ?? candidate.data_type,
            unit: assignment.unit ?? candidate.unit,
            options: assignment.options ?? candidate.options,
          }
        : assignment
    })
const trimAttributeValues = (): CatalogTrimAttributeValue[] =>
  Array.isArray(draft.value.trim_attribute_values)
    ? draft.value.trim_attribute_values as CatalogTrimAttributeValue[]
    : []
const trimValuesFromAssignments = (
  items: CatalogTrimAttributeAssignment[],
): CatalogTrimAttributeValue[] => items.map(item => ({
  attribute_id: item.attribute_id,
  value_number: item.value_number ?? null,
  value_text: item.value_text ?? null,
  value_boolean: item.value_boolean ?? null,
  option_id: item.option_id ?? null,
}))
const commitTrimAttributeCheckpoint = (
  items: CatalogTrimAttributeAssignment[],
  etag: string,
): CatalogTrimAttributeValue[] => {
  const values = trimValuesFromAssignments(items)
  currentEtag.value = etag
  trimStateEtag.value = etag
  initialTrimAttributesSnapshot.value = JSON.stringify(items)
  initialTrimAttributeValuesSnapshot.value = JSON.stringify(values)
  return values
}
const refreshTrimAttributeCheckpoint = async (trimId: UUID): Promise<void> => {
  const response = await api.getTrimAttributes(trimId)
  commitTrimAttributeCheckpoint(response.data.items, response.etag)
}
const loadTrimAttributes = async (trimId: UUID) => {
  const response = await api.getTrimAttributes(trimId)
  draft.value = { ...draft.value, trim_attributes: response.data.items }
  const values = commitTrimAttributeCheckpoint(response.data.items, response.etag)
  draft.value = { ...draft.value, trim_attribute_values: values }
}
const syncTrimAttributes = async (trimId: UUID): Promise<void> => {
  if (entity.value !== 'trims') return
  const assignments = trimAttributeAssignments()
  const values = trimAttributeValues()
  const initialAssignments = JSON.parse(initialTrimAttributesSnapshot.value) as CatalogTrimAttributeAssignment[]
  const initialValues = JSON.parse(initialTrimAttributeValuesSnapshot.value) as CatalogTrimAttributeValue[]
  const plan = planTrimAttributeSync({ initialAssignments, assignments, initialValues, values })
  let checkpoint = { assignments: initialAssignments, values: initialValues }
  let etag = trimStateEtag.value
  if (!etag) {
    const response = await api.getTrimAttributes(trimId)
    etag = response.etag
  }
  const commitCheckpoint = (nextEtag: string) => {
    etag = nextEtag
    currentEtag.value = nextEtag
    trimStateEtag.value = nextEtag
    initialTrimAttributesSnapshot.value = JSON.stringify(checkpoint.assignments)
    initialTrimAttributeValuesSnapshot.value = JSON.stringify(checkpoint.values)
  }
  for (const attributeId of plan.remove) {
    const response = await api.deleteTrimAttribute(trimId, attributeId, etag)
    checkpoint = advanceTrimAttributeCheckpoint(checkpoint, {
      type: 'remove',
      attributeId,
    })
    commitCheckpoint(response.etag)
  }
  for (const assignment of plan.add) {
    const response = await api.addTrimAttribute(trimId, assignment, etag)
    checkpoint = advanceTrimAttributeCheckpoint(checkpoint, {
      type: 'add',
      assignment: response.data.item,
    })
    commitCheckpoint(response.etag)
  }
  if (plan.values.length > 0) {
    const response = await api.patchTrimAttributeValues(trimId, plan.values, etag)
    checkpoint = advanceTrimAttributeCheckpoint(checkpoint, {
      type: 'values',
      values: response.data.saved,
    })
    commitCheckpoint(response.etag)
  }
  if (plan.remove.length > 0 || plan.add.length > 0 || plan.values.length > 0) {
    await loadTrimAttributes(trimId)
  }
}
const loadSelectedModification = async (modificationId: UUID | null) => {
  selectedModification.value = null
  resetSelectedProductTrimAttributes()
  const trimCandidatesRequest = entity.value === 'trims'
    ? loadTrimAttributeCandidates(modificationId)
    : Promise.resolve()
  if (!modificationId) {
    trims.value = []
    trimRequired.value = false
    await trimCandidatesRequest
    return
  }
  try {
    const response = await api.getModification(modificationId)
    if (draft.value.modification_id !== modificationId) return
    selectedModification.value = response.data
    if (entity.value === 'products') {
      await loadTrimsForModification(modificationId)
      const trimId = typeof draft.value.trim_id === 'string' && isUuid(draft.value.trim_id)
        ? draft.value.trim_id
        : null
      await loadSelectedProductTrimAttributes(trimId)
    }
    await trimCandidatesRequest
  } catch (error: unknown) {
    saveError.value = failureMessage(error)
  }
}
</script>
