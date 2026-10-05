<template>
  <section data-storefront-block="equipment.home"
    id="homepage-catalog"
    ref="moduleRoot"
    :data-homepage-catalog-hydrated="catalogHydrated"
    class="min-w-0 overflow-x-hidden bg-storefront-background py-10 [overflow-anchor:none] [overflow-wrap:anywhere] sm:py-14 lg:py-16 text-storefront-text"
    aria-labelledby="homepage-catalog-title"
  >
    <div class="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
      <header class="max-w-4xl">
        <h2 id="homepage-catalog-title" class="text-3xl font-bold tracking-tight text-storefront-title sm:text-4xl">
          Каталог транспортных средств и специальной техники
        </h2>
        <p class="mt-3 max-w-2xl text-base leading-relaxed text-storefront-text-muted">
          Выберите категорию, чтобы увидеть подходящие объявления и настроить параметры поиска.
        </p>
      </header>

      <div v-if="categoriesPending" class="mt-8 grid min-h-64 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Загрузка категорий" aria-busy="true">
        <div v-for="index in 8" :key="index" class="h-64 animate-pulse rounded-xl bg-storefront-skeleton motion-reduce:animate-none" />
      </div>

      <div v-else-if="categoriesError" class="mt-8 rounded-xl border border-storefront-error-border bg-storefront-error p-6 text-storefront-error-text" role="alert">
        <ExclamationTriangleIcon class="h-8 w-8 text-storefront-icon" aria-hidden="true" />
        <h3 class="mt-3 text-lg font-bold">Не удалось загрузить категории</h3>
        <p class="mt-1 text-sm leading-relaxed">Проверьте подключение и попробуйте ещё раз.</p>
        <button
          type="button"
          class="mt-4 min-h-11 rounded-lg border border-storefront-error-border bg-storefront-surface px-4 text-sm font-bold hover:bg-storefront-error-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-destructive"
          @click="refreshCategories()"
        >
          Повторить
        </button>
      </div>

      <div v-else-if="navigation.roots.length === 0" class="mt-8 rounded-xl border border-storefront-border bg-storefront-surface p-8 text-center">
        <h3 class="text-lg font-bold text-storefront-title">Категории пока не опубликованы</h3>
        <p class="mt-2 text-sm leading-relaxed text-storefront-text-muted">Вернитесь позже — доступные разделы появятся здесь.</p>
      </div>

      <div v-else-if="!navigation.selected" class="mt-8">
        <CategoryGrid
          :placements="navigation.roots"
          :categories="categories"
          :placements-data="placements"
          @select="selectPath"
        />
      </div>

      <div v-else class="mt-8">
        <nav aria-label="Путь по каталогу" class="overflow-x-auto pb-1 text-sm text-storefront-text-muted">
          <ol class="flex min-w-max items-center gap-2">
            <li>
              <button
                type="button"
                class="min-h-11 rounded-md px-1 font-semibold text-storefront-link hover:text-storefront-link-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
                @click="selectPath([], navigation.breadcrumbs[0]?.identity)"
              >
                Каталог
              </button>
            </li>
            <template v-for="(placement, index) in navigation.breadcrumbs" :key="placement.identity">
              <li aria-hidden="true">/</li>
              <li>
                <button
                  type="button"
                  class="min-h-11 rounded-md px-1 hover:text-storefront-link-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
                  :class="index === navigation.breadcrumbs.length - 1 ? 'font-bold text-storefront-text' : 'font-semibold text-storefront-link'"
                  :aria-current="index === navigation.breadcrumbs.length - 1 ? 'page' : undefined"
                  :data-homepage-active-category="index === navigation.breadcrumbs.length - 1 ? placement.identity : undefined"
                  @click="selectPath(placement.path)"
                >
                  {{ placement.category.name }}
                </button>
              </li>
            </template>
          </ol>
        </nav>

        <div class="mt-3 flex items-center gap-3">
          <button
            ref="backButton"
            type="button"
            class="inline-flex min-h-11 items-center gap-2 rounded-lg border border-storefront-border bg-storefront-surface px-4 text-sm font-bold text-storefront-text hover:border-storefront-secondary-hover-border hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-secondary"
            @click="goBack"
          >
            <ArrowLeftIcon class="h-5 w-5 text-storefront-icon" aria-hidden="true" />
            Назад
          </button>
        </div>

        <nav
          v-if="navigation.siblings.length > 1"
          class="mt-5 max-w-full overflow-x-visible pb-2"
          aria-label="Соседние категории"
        >
          <div role="tablist" class="flex min-w-0 flex-wrap gap-2">
            <button
              v-for="(placement, index) in navigation.siblings"
              :id="`homepage-category-tab-${index}`"
              :key="placement.identity"
              type="button"
              role="tab"
              :aria-selected="placement.identity === navigation.selected.identity"
              aria-controls="homepage-category-panel"
              :tabindex="placement.identity === navigation.selected.identity ? 0 : -1"
              :data-homepage-category-identity="placement.identity"
              class="min-h-11 max-w-xs rounded-lg border px-4 py-2 text-left text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2"
              :class="placement.identity === navigation.selected.identity
                ? 'border-storefront-selected-border bg-storefront-selected text-storefront-selected-foreground'
                : 'border-storefront-border bg-storefront-surface text-storefront-text hover:border-storefront-primary-border hover:bg-storefront-selected'"
              @click="selectPath(placement.path, placement.identity)"
              @keydown="handleTabKeydown($event, index)"
            >
              {{ placement.category.name }}
            </button>
          </div>
        </nav>

        <div
          id="homepage-category-panel"
          :role="navigation.siblings.length > 1 ? 'tabpanel' : undefined"
          :aria-labelledby="navigation.siblings.length > 1 ? activeTabId : undefined"
          class="mt-8"
        >
          <section v-if="navigation.standardChildren.length" aria-labelledby="homepage-standard-categories-title">
            <h3 id="homepage-standard-categories-title" class="text-xl font-bold tracking-tight text-storefront-title sm:text-2xl">
              Категории
            </h3>
            <CategoryGrid
              class="mt-4"
              :placements="navigation.standardChildren"
              :categories="categories"
              :placements-data="placements"
              @select="selectPath"
            />
          </section>

          <section
            v-if="navigation.attachmentChildren.length"
            class="mt-8 border-t border-storefront-primary-border pt-7"
            aria-labelledby="homepage-attachment-categories-title"
          >
            <h3 id="homepage-attachment-categories-title" class="text-xl font-bold tracking-tight text-storefront-title sm:text-2xl">
              Варианты надстроек
            </h3>
            <CategoryGrid
              class="mt-4"
              :placements="navigation.attachmentChildren"
              :categories="categories"
              :placements-data="placements"
              attachment
              @select="selectPath"
            />
          </section>

          <SpecialEquipmentCatalogPanel
            :key="navigation.selected.identity"
            class="mt-8"
            :category-path="navigation.activePath"
            :usage-metric="navigation.selected.category.usage_metric"
            :query-state="catalogQuery"
            :results-title="navigation.selected.category.name"
            :results-context="navigation.breadcrumbs.slice(0, -1).map(item => item.category.name).join(' / ')"
            results-id="homepage-special-equipment-results"
            :scroll-on-page-change="false"
            :public-route="publicRoute"
            @update:query-state="catalogQuery = $event"
          />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import {
  ArrowLeftIcon,
  ExclamationTriangleIcon,
} from '@heroicons/vue/24/outline'
import { createSpecialEquipmentApi } from '../api/specialEquipmentApi'
import { parseSpecialEquipmentCatalogQuery } from '../composables/catalogQuery'
import {
  projectSpecialEquipmentHomepageNavigation,
} from '../homepageCategoryNavigation'
import { resetHomepageCatalogQueryForBranch } from '../homepageCatalogPresentation'
import type { SpecialEquipmentCatalogQuery } from '../types'
import SpecialEquipmentCatalogPanel from './SpecialEquipmentCatalogPanel.vue'
import CategoryGrid from './SpecialEquipmentHomepageCategoryGrid.vue'

const { apiPath, publicRoute } = useStorefront()
const api = createSpecialEquipmentApi(useRuntimeConfig(), apiPath)
const moduleRoot = ref<HTMLElement | null>(null)
const catalogHydrated = ref('false')
const backButton = ref<HTMLButtonElement | null>(null)
const activePath = ref<string[]>([])
const catalogQuery = ref<SpecialEquipmentCatalogQuery>(parseSpecialEquipmentCatalogQuery({}))
let pendingFocusIdentity: string | null = null

onMounted(() => {
  catalogHydrated.value = 'true'
})

const {
  data: categoryResult,
  pending: categoriesPending,
  error: categoriesError,
  refresh: refreshCategories,
} = await useAsyncData(
  'special-equipment-homepage-categories',
  () => api.getCategories(),
)

const categories = computed(() => categoryResult.value?.items ?? [])
const placements = computed(() => categoryResult.value?.placements ?? [])
const rootItems = computed(() => categoryResult.value?.root_items ?? [])
const navigation = computed(() => projectSpecialEquipmentHomepageNavigation(
  categories.value,
  placements.value,
  activePath.value,
  rootItems.value,
))
const activeTabId = computed(() => {
  const index = navigation.value.siblings.findIndex(item => item.identity === navigation.value.selected?.identity)
  return index >= 0 ? `homepage-category-tab-${index}` : undefined
})

const resetQueryForBranch = () => {
  catalogQuery.value = resetHomepageCatalogQueryForBranch(catalogQuery.value)
}

const focusPendingPlacement = async () => {
  const identity = pendingFocusIdentity
  pendingFocusIdentity = null
  if (!identity) return
  await nextTick()
  if (identity === '__root__') {
    moduleRoot.value?.querySelector<HTMLElement>('[data-homepage-category-identity]')?.focus({ preventScroll: true })
    return
  }
  const escapedIdentity = typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
    ? CSS.escape(identity)
    : identity.replace(/[^a-zA-Z0-9_-]/g, '\\$&')
  const activeTab = moduleRoot.value?.querySelector<HTMLElement>(
    `[role="tab"][data-homepage-category-identity="${escapedIdentity}"]`,
  )
  const activeBreadcrumb = moduleRoot.value?.querySelector<HTMLElement>(
    `[data-homepage-active-category="${escapedIdentity}"]`,
  )
  const activeCard = moduleRoot.value?.querySelector<HTMLElement>(
    `[data-homepage-category-identity="${escapedIdentity}"]`,
  )
  const focusTarget = activeTab ?? activeBreadcrumb ?? activeCard
  if (focusTarget) focusTarget.focus({ preventScroll: true })
  else backButton.value?.focus({ preventScroll: true })
}

const selectPath = (path: string[], focusIdentity?: string) => {
  const nextIdentity = path.join('/')
  if (nextIdentity === activePath.value.join('/')) return
  pendingFocusIdentity = (focusIdentity ?? nextIdentity) || '__root__'
  activePath.value = [...path]
  resetQueryForBranch()
  void focusPendingPlacement()
}

const goBack = () => {
  const path = navigation.value.backPath ?? []
  const currentIdentity = navigation.value.selected?.identity
  selectPath(path, path.length ? undefined : currentIdentity)
}

const handleTabKeydown = (event: KeyboardEvent, index: number) => {
  const siblings = navigation.value.siblings
  if (!siblings.length) return
  let nextIndex: number | null = null
  if (event.key === 'ArrowRight') nextIndex = (index + 1) % siblings.length
  if (event.key === 'ArrowLeft') nextIndex = (index - 1 + siblings.length) % siblings.length
  if (event.key === 'Home') nextIndex = 0
  if (event.key === 'End') nextIndex = siblings.length - 1
  if (nextIndex === null) return
  event.preventDefault()
  const placement = siblings[nextIndex]
  if (placement) selectPath(placement.path, placement.identity)
}

watch([categories, placements], () => {
  if (!activePath.value.length || navigation.value.selected) return
  activePath.value = []
  resetQueryForBranch()
})

</script>
