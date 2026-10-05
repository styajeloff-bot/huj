<template>
  <section data-storefront-block="equipment.category" :aria-labelledby="navigation.selected && navigation.visibleCategories.length ? titleId : undefined" class="text-storefront-text">
    <h2
      v-if="navigation.selected && navigation.visibleCategories.length > 0"
      :id="titleId"
      class="mb-3 text-lg font-bold tracking-tight text-storefront-text sm:text-xl"
    >
      Подкатегории
    </h2>

    <div v-if="isLoading" class="flex gap-3 overflow-hidden" aria-label="Загрузка категорий">
      <div
        v-for="index in 6"
        :key="index"
        class="h-44 w-40 shrink-0 animate-pulse rounded-lg bg-storefront-skeleton motion-reduce:animate-none lg:min-w-0 lg:flex-1"
      />
    </div>

    <div v-else-if="hasError" class="rounded-lg border border-storefront-error-border bg-storefront-error p-4 text-sm text-storefront-error-text" role="alert">
      <p>Категории временно недоступны.</p>
      <button
        type="button"
        class="mt-2 min-h-11 font-bold text-storefront-error-text underline underline-offset-2"
        @click="emit('retry')"
      >
        Повторить
      </button>
    </div>

    <div v-else-if="navigation.visibleCategories.length > 0" class="category-strip">
      <NuxtLink
        v-for="placement in navigation.visibleCategories"
        :key="placement.path.join('/')"
        :to="{ path: toPublicRoute(specialEquipmentCategoryPath(placement.path)), query: query }"
        class="category-card border-storefront-border bg-storefront-surface hover:border-storefront-primary-border"
      >
        <span
          class="relative block aspect-[3/2] w-full overflow-hidden rounded-md"
          :class="'bg-storefront-image'"
        >
          <img
            v-if="categoryImageUrl(placement.category)"
            :src="categoryImageUrl(placement.category) ?? undefined"
            alt=""
            aria-hidden="true"
            width="160"
            height="107"
            class="h-full w-full object-contain"
            @error="markImageBroken(placement.category.id)"
          >
          <span v-else class="grid h-full w-full place-items-center text-storefront-text-muted" aria-hidden="true">
            <PhotoIcon class="h-6 w-6 text-storefront-icon" />
          </span>
        </span>
        <span class="mt-2 block line-clamp-2 text-sm font-bold leading-tight text-storefront-text">
          {{ placement.category.name }}
        </span>
        <span v-if="placement.category.product_count !== undefined" class="mt-1 block text-xs text-storefront-text-muted">
          {{ formatProductCount(placement.category.product_count) }}
        </span>
        <span v-if="placement.category.child_ids.length > 0" class="mt-0.5 block text-xs text-storefront-text-muted">
          Есть подразделы
        </span>
      </NuxtLink>
    </div>

    <section
      v-if="!isLoading && !hasError && navigation.attachmentCategories.length > 0"
      class="mt-7 border-t border-storefront-primary-border pt-6"
      :aria-labelledby="attachmentTitleId"
    >
      <div class="mb-3">
        <h2 :id="attachmentTitleId" class="text-lg font-bold tracking-tight text-storefront-title sm:text-xl">
          Варианты надстроек
        </h2>
        <p class="mt-1 text-sm leading-relaxed text-storefront-text-muted">
          Выберите подходящую надстройку для техники из этой категории.
        </p>
      </div>

      <div class="category-strip">
        <NuxtLink
          v-for="placement in navigation.attachmentCategories"
          :key="placement.path.join('/')"
          :to="{ path: toPublicRoute(specialEquipmentCategoryPath(placement.path)), query: query }"
          class="category-card border-storefront-primary-border bg-storefront-selected/40 hover:border-storefront-primary-border hover:bg-storefront-selected"
        >
          <span
            class="relative block aspect-[3/2] w-full overflow-hidden rounded-md"
            :class="'bg-storefront-image'"
          >
            <img
              v-if="categoryImageUrl(placement.category)"
              :src="categoryImageUrl(placement.category) ?? undefined"
              alt=""
              aria-hidden="true"
              width="160"
              height="107"
              class="h-full w-full object-contain"
              @error="markImageBroken(placement.category.id)"
            >
            <span v-else class="grid h-full w-full place-items-center text-storefront-link" aria-hidden="true">
              <PhotoIcon class="h-6 w-6 text-storefront-icon" />
            </span>
          </span>
          <span class="mt-2 block line-clamp-2 text-sm font-bold leading-tight text-storefront-text">
            {{ placement.category.name }}
          </span>
          <span v-if="placement.category.product_count !== undefined" class="mt-1 block text-xs text-storefront-text-muted">
            {{ formatProductCount(placement.category.product_count) }}
          </span>
          <span v-if="placement.category.child_ids.length > 0" class="mt-0.5 block text-xs text-storefront-text-muted">
            Есть подразделы
          </span>
        </NuxtLink>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { PhotoIcon } from '@heroicons/vue/24/outline'
import type { LocationQueryRaw } from 'vue-router'
import type { UUID } from '~/types/ids'
import type { PublicRouteBuilder } from '~/utils/storefrontRoute'
import {
  createSpecialEquipmentCategoryNavigation,
  specialEquipmentCategoryPath,
} from '../categoryNavigation'
import { toSpecialEquipmentProxyUrl } from '../media'
import type {
  SpecialEquipmentCategoryNode,
  SpecialEquipmentCategoryRef,
} from '../types'

const props = defineProps<{
  categories: SpecialEquipmentCategoryNode[]
  selectedPath: SpecialEquipmentCategoryRef[]
  query: LocationQueryRaw
  isLoading: boolean
  hasError: boolean
  publicRoute: PublicRouteBuilder
}>()
const toPublicRoute = props.publicRoute

const emit = defineEmits<{ retry: [] }>()
const titleId = `special-equipment-category-navigation-${useId()}`
const attachmentTitleId = `special-equipment-attachment-navigation-${useId()}`
const brokenImageIds = ref<Set<UUID>>(new Set())
const navigation = computed(() => createSpecialEquipmentCategoryNavigation(
  props.categories,
  props.selectedPath,
))

const categoryImageUrl = (category: SpecialEquipmentCategoryNode): string | null =>
  brokenImageIds.value.has(category.id) ? null : toSpecialEquipmentProxyUrl(category.image_url)

const markImageBroken = (categoryId: UUID) => {
  brokenImageIds.value = new Set([...brokenImageIds.value, categoryId])
}

const formatProductCount = (count: number): string => {
  const mod100 = count % 100
  const mod10 = count % 10
  const noun = mod100 >= 11 && mod100 <= 14
    ? 'объявлений'
    : mod10 === 1
      ? 'объявление'
      : mod10 >= 2 && mod10 <= 4
        ? 'объявления'
        : 'объявлений'
  return `${new Intl.NumberFormat('ru-RU').format(count)} ${noun}`
}
</script>

<style scoped>
.category-strip {
  display: grid;
  width: auto;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin-right: 0;
  padding-right: 0;
  overflow: visible;
}

.category-card {
  width: auto;
  min-width: 0;
  min-height: 11rem;
  padding: 0.75rem;
  border-width: 1px;
  border-radius: 0.5rem;
  text-align: left;
  text-decoration: none;
  transition: border-color 160ms ease, background-color 160ms ease, transform 160ms ease;
}

.category-card:hover { transform: translateY(-1px); }
.category-card:focus-visible { outline: 3px solid rgb(var(--storefront-focus-rgb) / 35%); outline-offset: 2px; }

@media (min-width: 1120px) {
  .category-strip { grid-template-columns: repeat(6, minmax(0, 1fr)); }
}

@media (prefers-reduced-motion: reduce) {
  .category-card { transition-duration: 0.01ms; }
}
</style>
