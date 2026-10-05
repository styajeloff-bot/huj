<template>
  <div data-storefront-block="equipment.catalog" class="min-h-screen bg-storefront-background text-storefront-text">
    <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <nav class="mb-4 overflow-x-auto text-sm text-storefront-text-muted" aria-label="Хлебные крошки">
        <ol class="flex min-w-max items-center gap-2">
          <li><NuxtLink :to="publicRoute('/')" class="hover:text-storefront-link-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-link">{{ pageTitle('home') }}</NuxtLink></li>
          <li aria-hidden="true">/</li>
          <li v-if="selectedCategoryPath.length">
            <NuxtLink
              :to="publicRoute('/special-equipment')"
              class="hover:text-storefront-link-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-link"
            >
              {{ pageTitle('special_equipment_catalog') }}
            </NuxtLink>
          </li>
          <li v-else class="text-storefront-text" aria-current="page">
            {{ pageTitle('special_equipment_catalog') }}
          </li>
          <template v-for="(category, index) in selectedCategoryPath" :key="`${category.id}-${index}`">
            <li aria-hidden="true">/</li>
            <li v-if="index < selectedCategoryPath.length - 1">
              <NuxtLink
                :to="publicRoute(specialEquipmentCategoryPath(selectedCategoryPath.slice(0, index + 1).map(item => item.slug)))"
                class="hover:text-storefront-link-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-link"
              >
                {{ category.name }}
              </NuxtLink>
            </li>
            <li v-else class="text-storefront-text" aria-current="page">{{ category.name }}</li>
          </template>
        </ol>
      </nav>

      <header class="mb-7 max-w-3xl">
        <h1 class="text-3xl font-bold tracking-tight text-storefront-title sm:text-4xl">
          {{ selectedCategory?.name || pageTitle('special_equipment_catalog') }}
        </h1>
        <p class="mt-2 text-sm leading-relaxed text-storefront-text-muted sm:text-base">
          Подберите технику по назначению, характеристикам и доступным предложениям.
        </p>
      </header>

      <SpecialEquipmentCategoryNavigation
        :categories="categories"
        :selected-path="selectedCategoryPath"
        :query="categoryNavigationQuery"
        :is-loading="categoriesPending"
        :has-error="Boolean(categoriesError)"
        :public-route="publicRoute"
        @retry="refreshCategories()"
      />

      <SpecialEquipmentCatalogPanel
        :category-path="categoryPath"
        :usage-metric="usageMetric"
        :query-state="catalogQuery"
        :results-title="selectedCategory?.name || 'Вся техника'"
        :results-context="resultsContext"
        :public-route="publicRoute"
        @update:query-state="updateCatalogQueryState"
      />
    </main>
  </div>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { createSpecialEquipmentApi } from '../api/specialEquipmentApi'
import { specialEquipmentCatalogAsyncDataKeys } from '../catalogAsyncData'
import {
  pruneUnavailableSpecialEquipmentCategories,
  specialEquipmentCategoryPath,
} from '../categoryNavigation'
import {
  parseSpecialEquipmentCatalogQuery,
  resetSpecialEquipmentCategorySpecificFilters,
  serializeSpecialEquipmentCatalogQuery,
} from '../composables/catalogQuery'
import type {
  SpecialEquipmentCatalogQuery,
  SpecialEquipmentCategoryContextResponse,
} from '../types'
import SpecialEquipmentCatalogPanel from './SpecialEquipmentCatalogPanel.vue'
import SpecialEquipmentCategoryNavigation from './SpecialEquipmentCategoryNavigation.vue'

type CategoryContextState = Omit<SpecialEquipmentCategoryContextResponse, 'category'> & {
  category: SpecialEquipmentCategoryContextResponse['category'] | null
}

const props = withDefaults(defineProps<{ categoryPath?: string[] }>(), {
  categoryPath: () => [],
})
const { apiPath, pageTitle, publicRoute } = useStorefront()
const categoryPath = computed(() => props.categoryPath)
const asyncDataKeys = computed(() => specialEquipmentCatalogAsyncDataKeys(categoryPath.value))
const route = useRoute()
const router = useRouter()
const api = createSpecialEquipmentApi(useRuntimeConfig(), apiPath)
const catalogQuery = computed(() => parseSpecialEquipmentCatalogQuery(route.query))

const {
  data: categoryContext,
  error: categoryContextError,
} = await useAsyncData<CategoryContextState>(
  () => asyncDataKeys.value.categoryContext,
  () => categoryPath.value.length
    ? api.resolveCategoryPath(categoryPath.value)
    : Promise.resolve({ items: [], category: null }),
  { watch: [() => categoryPath.value.join('/')], dedupe: 'cancel' },
)

const httpStatus = (value: unknown): number | null => {
  if (!value || typeof value !== 'object') return null
  const errorValue = value as { statusCode?: unknown; status?: unknown }
  if (typeof errorValue.statusCode === 'number') return errorValue.statusCode
  return typeof errorValue.status === 'number' ? errorValue.status : null
}

if (categoryPath.value.length && httpStatus(categoryContextError.value) === 404) {
  throw createError({
    statusCode: 404,
    statusMessage: 'Категория специальной техники не найдена',
    fatal: true,
  })
}
watch(categoryContextError, (currentError) => {
  if (!categoryPath.value.length || httpStatus(currentError) !== 404) return
  showError({
    statusCode: 404,
    statusMessage: 'Категория специальной техники не найдена',
  })
})

const selectedCategoryPath = computed(() => categoryContext.value?.items ?? [])
const selectedCategory = computed(() => selectedCategoryPath.value.at(-1) ?? null)
const resultsContext = computed(() => selectedCategoryPath.value.length > 1
  ? selectedCategoryPath.value.slice(0, -1).map(category => category.name).join(' / ')
  : '')

const {
  data: categoryResult,
  pending: categoriesPending,
  error: categoriesError,
  refresh: refreshCategories,
} = await useAsyncData(
  'special-equipment-catalog-categories',
  () => api.getCategories(),
)

const categories = computed(() => pruneUnavailableSpecialEquipmentCategories(
  categoryResult.value?.items ?? [],
  selectedCategoryPath.value,
))
const selectedCategoryNode = computed(() =>
  categories.value.find(category => category.id === selectedCategory.value?.id) ?? null,
)
const usageMetric = computed(() => selectedCategoryNode.value?.usage_metric ?? null)
const categoryNavigationQuery = computed(() => serializeSpecialEquipmentCatalogQuery(
  resetSpecialEquipmentCategorySpecificFilters(catalogQuery.value),
))

const updateCatalogQueryState = async (next: SpecialEquipmentCatalogQuery) => {
  await router.push({ path: route.path, query: serializeSpecialEquipmentCatalogQuery(next) })
}

const config = useRuntimeConfig()
const canonicalPath = computed(() => categoryPath.value.length
  ? publicRoute(specialEquipmentCategoryPath(categoryPath.value))
  : publicRoute('/special-equipment'))
useSeoMeta({
  title: () => selectedCategory.value
    ? `${selectedCategory.value.name} — транспортные средства и специальная техника CarCraft Multileasing`
    : `${pageTitle('special_equipment_catalog')} — CarCraft Multileasing`,
  description: () => selectedCategory.value
    ? `${selectedCategory.value.name}: объявления, характеристики, стоимость и оформление в лизинг.`
    : 'Транспортные средства и специальная техника для бизнеса: характеристики, стоимость, покупка и оформление в лизинг.',
})
useHead(() => ({
  link: [{ rel: 'canonical', href: `${config.public.siteUrl}${canonicalPath.value}` }],
}))
</script>
