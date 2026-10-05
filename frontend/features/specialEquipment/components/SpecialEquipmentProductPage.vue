<template>
  <div data-storefront-block="equipment.detail" class="min-h-screen bg-storefront-background text-storefront-text">
    <div v-if="pending" class="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8" aria-label="Загрузка карточки техники">
      <div class="h-5 w-72 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
      <div class="mt-7 grid gap-8 lg:grid-cols-2">
        <div class="aspect-[4/3] animate-pulse rounded-xl bg-storefront-skeleton motion-reduce:animate-none" />
        <div class="flex flex-col gap-4">
          <div class="h-4 w-1/4 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
          <div class="h-10 w-4/5 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
          <div class="h-6 w-2/3 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
          <div class="mt-8 h-12 w-1/2 animate-pulse rounded bg-storefront-skeleton motion-reduce:animate-none" />
        </div>
      </div>
    </div>

    <div v-else-if="error || !product" class="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6" role="alert">
      <ExclamationTriangleIcon class="mx-auto h-14 w-14 text-storefront-warning-icon" aria-hidden="true" />
      <h1 class="mt-5 text-3xl font-bold tracking-tight text-storefront-title">Техника не найдена</h1>
      <p class="mx-auto mt-3 max-w-lg text-base leading-relaxed text-storefront-text-muted">
        Предложение могло быть снято с публикации или адрес указан неверно.
      </p>
      <div class="mt-7 flex flex-wrap justify-center gap-3">
        <NuxtLink :to="publicRoute('/special-equipment')" class="inline-flex min-h-11 items-center rounded-lg bg-storefront-primary px-5 text-sm font-bold text-storefront-primary-foreground hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-primary">
          Вернуться в каталог
        </NuxtLink>
        <button type="button" class="min-h-11 rounded-lg border border-storefront-border bg-storefront-surface px-5 text-sm font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary" @click="refresh()">
          Повторить
        </button>
      </div>
    </div>

    <template v-else>
      <div class="border-b border-storefront-border bg-storefront-surface">
        <div class="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <nav class="overflow-x-auto text-sm text-storefront-text-muted" aria-label="Хлебные крошки">
            <ol class="flex min-w-max items-center gap-2">
              <li><NuxtLink :to="publicRoute('/')" class="hover:text-storefront-link-hover storefront-link">{{ pageTitle('home') }}</NuxtLink></li>
              <li aria-hidden="true">/</li>
              <li><NuxtLink :to="publicRoute('/special-equipment')" class="hover:text-storefront-link-hover storefront-link">{{ pageTitle('special_equipment_catalog') }}</NuxtLink></li>
              <template v-for="(category, index) in resolvedCategoryPath" :key="`${category.id}-${index}`">
                <li aria-hidden="true">/</li>
                <li>
                  <NuxtLink
                    :to="publicRoute(specialEquipmentCategoryPath(resolvedCategoryPath.slice(0, index + 1).map(item => item.slug)))"
                    class="hover:text-storefront-link-hover storefront-link"
                  >
                    {{ category.name }}
                  </NuxtLink>
                </li>
              </template>
              <li aria-hidden="true">/</li>
              <li class="max-w-64 truncate text-storefront-text" aria-current="page">
                {{ isCategoryRouteProduct ? productBreadcrumbTitle : productDisplayHeading }}
              </li>
            </ol>
          </nav>
        </div>
      </div>

      <article class="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
        <div class="grid items-start gap-8 lg:grid-cols-2 lg:gap-12">
          <SpecialEquipmentGallery :images="product.images" :title="productTitle" />

          <div data-storefront-block="equipment.detail.info" class="text-storefront-text">
            <div class="flex flex-wrap items-center gap-2">
              <span class="text-sm font-bold text-storefront-link">{{ productModel(product).mark.name }}</span>
              <span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="statusClass">
                {{ statusLabel }}
              </span>
            </div>
            <h1 class="mt-3 text-3xl font-bold tracking-tight text-storefront-title sm:text-4xl">{{ productDisplayHeading }}</h1>
            <p v-if="productSubtitle" class="mt-2 text-lg leading-relaxed text-storefront-text-muted">{{ productSubtitle }}</p>

            <dl data-testid="detail-basic-parameters" class="mt-5 flex flex-wrap gap-x-6 gap-y-2 bg-storefront-surface-muted text-sm text-storefront-label">
              <div v-if="product.terminal_category" class="flex gap-2">
                <dt class="text-storefront-label">Категория</dt>
                <dd class="font-semibold text-storefront-value">{{ product.terminal_category.name }}</dd>
              </div>
              <div class="flex gap-2">
                <dt class="text-storefront-label">Состояние</dt>
                <dd class="font-semibold text-storefront-value">{{ product.condition === 'used' ? 'С пробегом' : 'Новое' }}</dd>
              </div>
              <div v-if="product.manufacture_year" class="flex gap-2">
                <dt class="text-storefront-label">Год выпуска</dt>
                <dd class="font-semibold text-storefront-value">{{ product.manufacture_year }}</dd>
              </div>
              <div v-if="product.body_color" class="flex gap-2">
                <dt class="text-storefront-label">Цвет кузова</dt>
                <dd class="font-semibold text-storefront-value">{{ product.body_color.name }}</dd>
              </div>
              <div v-if="product.interior_color" class="flex gap-2">
                <dt class="text-storefront-label">Цвет салона</dt>
                <dd class="font-semibold text-storefront-value">{{ product.interior_color.name }}</dd>
              </div>
              <div v-if="product.mileage_km !== null" class="flex gap-2">
                <dt class="text-storefront-label">Пробег</dt>
                <dd class="font-semibold text-storefront-value">{{ product.mileage_km.toLocaleString('ru-RU') }} км</dd>
              </div>
              <div v-if="product.engine_hours !== null" class="flex gap-2">
                <dt class="text-storefront-label">Моточасы</dt>
                <dd class="font-semibold text-storefront-value">{{ product.engine_hours.toLocaleString('ru-RU') }} м/ч</dd>
              </div>
              <div v-if="product.condition === 'used' && product.owners_count !== null && product.owners_count !== undefined" class="flex gap-2">
                <dt class="text-storefront-label">Владельцев</dt>
                <dd class="font-semibold text-storefront-value">{{ product.owners_count }}</dd>
              </div>
            </dl>

            <div class="mt-7 border-y border-storefront-border py-6">
              <div v-if="product.price !== null || product.price_on_request">
                <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <p class="text-3xl font-bold tabular-nums text-storefront-price">{{ specialEquipmentPriceLabel(product) }}</p>
                  <p v-if="hasSpecialOffer && product.base_price !== null" class="text-lg tabular-nums text-storefront-text-muted line-through">
                    {{ formatPrice(product.base_price) }}
                  </p>
                </div>
                <p v-if="hasSpecialOffer" class="mt-2 text-sm font-bold uppercase tracking-wide text-storefront-success-text">
                  Спецпредложение
                </p>
              </div>
              <div v-else>
                <p class="text-2xl font-bold text-storefront-price">Цена по запросу</p>
                <p class="mt-1 text-sm text-storefront-text-muted">Уточним актуальную стоимость у продавца.</p>
              </div>
              <p v-if="product.price_on_request" class="mt-1 text-sm text-storefront-text-muted">Точную стоимость согласует дилер после подачи заявки на лизинг.</p>
              <p v-else-if="product.price !== null" class="mt-1 text-sm text-storefront-text-muted">Финальные условия зависят от выбранного способа оформления.</p>
              <SpecialEquipmentActions
                class="mt-5"
                :product="product"
                :is-favorite="commerceStateReady && commerce.isFavorite(product.id)"
                :is-in-cart="commerceStateReady && commerce.isStandaloneInCart(product.id)"
                :favorite-pending="commerce.isFavoritePending(product.id)"
                :cart-pending="commerce.isCartPending(product.id)"
                @toggle-favorite="commerce.toggleFavorite($event, product.capabilities.can_favorite)"
                @toggle-cart="handleCartToggle"
              />
            </div>

            <section
              v-if="product.available_count > 0 || product.sale_status === 'on_order'"
              data-testid="detail-quantity"
              class="mt-6 flex flex-wrap items-end gap-4 rounded-xl border border-storefront-border bg-storefront-surface p-4"
              aria-label="Наличие и количество техники"
            >
              <p v-if="product.sale_status === 'on_order'" class="basis-full text-sm text-storefront-text-muted">
                Доступно оформление под заказ
              </p>
              <ul v-if="warehouseStock.length" data-testid="detail-warehouse-stock" class="grid min-w-0 flex-1 basis-56 gap-3">
                <li
                  v-for="stock in warehouseStock"
                  :key="stock.warehouse_id"
                  data-testid="detail-warehouse-row"
                  class="min-w-0 break-words text-sm"
                >
                  <p class="font-semibold text-storefront-text">Дилер: {{ stock.owner_company_name }}</p>
                  <p class="mt-1 text-storefront-text-muted">Склад: {{ stock.address }}</p>
                  <p data-testid="detail-stock-count" class="mt-1 font-semibold tabular-nums text-storefront-text">
                    <template v-if="product.sale_status !== 'on_order'">В наличии: </template>{{ formatCount(stock.count) }} шт.
                  </p>
                </li>
              </ul>
              <p v-else-if="product.sale_status !== 'on_order'" class="min-w-0 flex-1 basis-56 text-sm text-storefront-text-muted">
                В наличии: {{ formatCount(product.available_count) }} шт.
              </p>
              <SpecialEquipmentQuantityPicker
                v-model="productQuantity"
                class="ml-auto"
                :max="productQuantityLimit"
                label="Количество"
              />
            </section>

            <section v-if="cardAttributes.length" class="mt-6 rounded-xl border border-storefront-border bg-storefront-surface p-4" aria-labelledby="card-attributes-title">
              <h2 id="card-attributes-title" class="text-sm font-bold text-storefront-title">Ключевые характеристики</h2>
              <dl class="mt-3 grid gap-2 text-sm">
                <div v-for="attribute in cardAttributes" :key="attribute.id" class="flex items-start justify-between gap-4">
                  <dt class="text-storefront-label">{{ attribute.name }}</dt>
                  <dd v-if="attribute.formatted_value !== null" class="text-right font-semibold text-storefront-value">{{ attribute.formatted_value }}</dd>
                  <dd v-else class="sr-only">выбрано</dd>
                </div>
              </dl>
            </section>
          </div>
        </div>

        <SpecialEquipmentCompatibleAttachments
          v-model="selectedAttachments"
          class="mt-12"
          :items="compatibleAttachments"
          :is-loading="attachmentsPending"
          :has-error="Boolean(attachmentsError)"
          :public-route="publicRoute"
          @retry="refreshAttachments()"
        />

        <div class="mt-12 grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
          <section v-if="product.description" data-storefront-block="equipment.detail.description" aria-labelledby="description-title" class="text-storefront-text">
            <h2 id="description-title" class="text-2xl font-bold tracking-tight text-storefront-title">Описание</h2>
            <p class="mt-4 max-w-3xl whitespace-pre-line text-base leading-7 text-storefront-text">{{ product.description }}</p>
          </section>

        </div>

        <div v-if="isKitProduct" data-storefront-block="equipment.detail.kit-specs" class="mt-12 flex flex-col gap-10 text-storefront-text">
          <section data-testid="detail-chassis-section" aria-labelledby="chassis-specs-title">
            <h2 id="chassis-specs-title" class="text-2xl font-bold tracking-tight text-storefront-title">Шасси</h2>
            <div v-if="chassisAttributeGroups.length > 0" class="mt-5 grid gap-6">
              <section v-for="group in chassisAttributeGroups" :key="group.id ?? group.name">
                <h3 class="text-base font-bold text-storefront-title">{{ group.name }}</h3>
                <dl class="mt-3 grid overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface sm:grid-cols-2">
                  <div
                    v-for="attribute in group.attributes"
                    :key="attribute.id"
                    class="flex min-h-14 items-center justify-between gap-4 border-b border-storefront-border px-4 py-3 last:border-b-0 sm:odd:border-r sm:[&:nth-last-child(-n+2)]:border-b-0"
                  >
                    <dt class="text-sm leading-relaxed text-storefront-label">{{ attribute.name }}</dt>
                    <dd v-if="attribute.formatted_value !== null" class="text-right text-sm font-semibold leading-relaxed text-storefront-value">{{ attribute.formatted_value }}</dd>
                    <dd v-else class="sr-only">выбрано</dd>
                  </div>
                </dl>
              </section>
            </div>
          </section>

          <section data-testid="detail-superstructure-section" aria-labelledby="superstructure-specs-title">
            <h2 id="superstructure-specs-title" class="text-2xl font-bold tracking-tight text-storefront-title">Надстройка</h2>
            <dl v-if="product.superstructure" data-testid="superstructure-summary" class="mt-4 flex flex-wrap gap-x-6 gap-y-2 bg-storefront-surface-muted text-sm text-storefront-label">
              <div v-if="product.superstructure.name" class="flex gap-2">
                <dt class="text-storefront-label">Название</dt>
                <dd class="font-semibold text-storefront-value">{{ product.superstructure.name }}</dd>
              </div>
              <div v-if="product.superstructure.type_name" class="flex gap-2">
                <dt class="text-storefront-label">Тип надстройки</dt>
                <dd class="font-semibold text-storefront-value">{{ product.superstructure.type_name }}</dd>
              </div>
              <div v-if="product.superstructure.manufacturer" class="flex gap-2">
                <dt class="text-storefront-label">Производитель</dt>
                <dd class="font-semibold text-storefront-value">{{ product.superstructure.manufacturer }}</dd>
              </div>
            </dl>
            <div v-if="superstructureAttributeGroups.length > 0" class="mt-5 grid gap-6">
              <section v-for="group in superstructureAttributeGroups" :key="group.id ?? group.name">
                <h3 class="text-base font-bold text-storefront-title">{{ group.name }}</h3>
                <dl class="mt-3 grid overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface sm:grid-cols-2">
                  <div
                    v-for="attribute in group.attributes"
                    :key="attribute.id"
                    class="flex min-h-14 items-center justify-between gap-4 border-b border-storefront-border px-4 py-3 last:border-b-0 sm:odd:border-r sm:[&:nth-last-child(-n+2)]:border-b-0"
                  >
                    <dt class="text-sm leading-relaxed text-storefront-label">{{ attribute.name }}</dt>
                    <dd v-if="attribute.formatted_value !== null" class="text-right text-sm font-semibold leading-relaxed text-storefront-value">{{ attribute.formatted_value }}</dd>
                    <dd v-else class="sr-only">выбрано</dd>
                  </div>
                </dl>
              </section>
            </div>
          </section>
        </div>
        <section v-else-if="allAttributeGroups.length > 0" data-storefront-block="equipment.detail.specs" class="mt-12 text-storefront-text" aria-labelledby="specifications-title">
          <h2 id="specifications-title" class="text-2xl font-bold tracking-tight text-storefront-title">Характеристики</h2>
          <div class="mt-5 grid gap-6">
            <section v-for="group in allAttributeGroups" :key="group.id ?? group.name">
              <h3 class="text-base font-bold text-storefront-title">{{ group.name }}</h3>
              <dl class="mt-3 grid overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface sm:grid-cols-2">
                <div
                  v-for="attribute in group.attributes"
                  :key="attribute.id"
                  class="flex min-h-14 items-center justify-between gap-4 border-b border-storefront-border px-4 py-3 last:border-b-0 sm:odd:border-r sm:[&:nth-last-child(-n+2)]:border-b-0"
                >
                  <dt class="text-sm leading-relaxed text-storefront-label">{{ attribute.name }}</dt>
                  <dd v-if="attribute.formatted_value !== null" class="text-right text-sm font-semibold leading-relaxed text-storefront-value">{{ attribute.formatted_value }}</dd>
                  <dd v-else class="sr-only">выбрано</dd>
                </div>
              </dl>
            </section>
          </div>
        </section>

        <section v-if="trimAttributeGroups.length > 0" data-storefront-block="equipment.detail.trim" class="mt-12 text-storefront-text" aria-labelledby="trim-specifications-title">
          <h2 id="trim-specifications-title" class="text-2xl font-bold tracking-tight text-storefront-title">Параметры комплектации</h2>
          <div class="mt-5 grid gap-6">
            <section v-for="group in trimAttributeGroups" :key="`${group.scope}-${group.id ?? group.name}`">
              <h3 class="text-lg font-bold text-storefront-title">{{ group.name }}</h3>
              <dl class="mt-3 grid overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface sm:grid-cols-2">
                <div
                  v-for="attribute in group.attributes"
                  :key="attribute.id"
                  class="flex min-h-14 items-center justify-between gap-4 border-b border-storefront-border px-4 py-3 last:border-b-0 sm:odd:border-r sm:[&:nth-last-child(-n+2)]:border-b-0"
                >
                  <dt class="text-sm leading-relaxed text-storefront-label">
                    {{ attribute.name }}
                  </dt>
                  <dd v-if="attribute.formatted_value !== null" class="text-right text-sm font-semibold leading-relaxed text-storefront-value">
                    {{ attribute.formatted_value }}
                  </dd>
                  <dd v-else class="sr-only">выбрано</dd>
                </div>
              </dl>
            </section>
          </div>
        </section>
      </article>
    </template>

    <AuthModal
      v-if="showAuthModal"
      @close="cancelAuthentication"
      @authenticated="handleAuthenticated"
    />
  </div>
</template>

<script setup lang="ts">
import { ExclamationTriangleIcon } from '@heroicons/vue/24/outline'
import AuthModal from '~/features/auth/components/AuthModal.vue'
import { useStorefront } from '~/features/storefront'
import { isUuid, type UUID } from '~/types/ids'
import { createSpecialEquipmentApi } from '../api/specialEquipmentApi'
import {
  displayableSpecialEquipmentAttributeGroups,
  presentSpecialEquipmentDetailAttribute,
} from '../attributeDisplay'
import { specialEquipmentCategoryPath } from '../categoryNavigation'
import { useSpecialEquipmentCommerce } from '../composables/useSpecialEquipmentCommerce'
import { toSpecialEquipmentProxyUrl } from '../media'
import { specialEquipmentPriceLabel } from '../priceOnRequest'
import {
  productModel,
  type SpecialEquipmentCategoryContextResponse,
  type SpecialEquipmentAttachmentSelection,
} from '../types'
import SpecialEquipmentActions from './SpecialEquipmentActions.vue'
import SpecialEquipmentCompatibleAttachments from './SpecialEquipmentCompatibleAttachments.vue'
import SpecialEquipmentGallery from './SpecialEquipmentGallery.vue'
import SpecialEquipmentQuantityPicker from './SpecialEquipmentQuantityPicker.vue'

type CategoryContextState = Omit<SpecialEquipmentCategoryContextResponse, 'category'> & {
  category: SpecialEquipmentCategoryContextResponse['category'] | null
}

const props = withDefaults(defineProps<{
  productId?: UUID | null
  productSlug?: string
  categoryPath?: string[]
}>(), {
  productId: null,
  productSlug: '',
  categoryPath: () => [],
})
const route = useRoute()
const { apiPath, pageTitle, publicRoute } = useStorefront()
const api = createSpecialEquipmentApi(useRuntimeConfig(), apiPath)
const rawProductId = computed(() => props.productId
  ?? (typeof route.params.id === 'string' ? route.params.id : ''))
const productId = computed<UUID | null>(() => isUuid(rawProductId.value) ? rawProductId.value : null)
const productRequestKey = computed(() =>
  `${productId.value ?? 'invalid'}:${props.categoryPath.join('/')}`)

const showAuthModal = ref(false)
const productQuantity = ref(1)
const selectedAttachments = ref<SpecialEquipmentAttachmentSelection[]>([])
const commerce = useSpecialEquipmentCommerce({
  onAuthRequired: () => { showAuthModal.value = true },
})
// The header can restore guest storage before this async page hydrates.
// Apply membership after mounting so button text and attributes update together.
const commerceStateReady = ref(false)
onMounted(() => { commerceStateReady.value = true })

const {
  data: categoryContext,
  pending: categoryPending,
  error: categoryError,
} = await useAsyncData<CategoryContextState>(
  'special-equipment-product-category-context',
  () => props.categoryPath.length
    ? api.resolveCategoryPath(props.categoryPath)
    : Promise.resolve({ items: [], category: null }),
  { watch: [() => props.categoryPath.join('/')], dedupe: 'cancel' },
)

const {
  data: product,
  pending: productPending,
  error,
  refresh,
} = await useAsyncData(
  'special-equipment-product-detail',
  async () => {
    if (!productId.value) {
      throw createError({ statusCode: 404, statusMessage: 'Special equipment product not found' })
    }
    return api.getProduct(productId.value, props.categoryPath)
  },
  { watch: [productRequestKey], dedupe: 'cancel' },
)

const {
  data: attachmentsResult,
  pending: attachmentsPending,
  error: attachmentsError,
  refresh: refreshAttachments,
} = await useAsyncData(
  () => `special-equipment-compatible-attachments:${productId.value ?? 'invalid'}`,
  () => productId.value
    ? api.getCompatibleAttachments(productId.value)
    : Promise.resolve({ items: [] }),
  { watch: [productId], dedupe: 'cancel' },
)

const pending = computed(() => productPending.value || categoryPending.value)
const resolvedCategoryPath = computed(() => categoryContext.value?.items ?? [])
const compatibleAttachments = computed(() => attachmentsResult.value?.items ?? [])
const productQuantityLimit = computed(() => product.value?.sale_status === 'on_order'
  ? Math.max(1, product.value.available_count)
  : Math.max(1, product.value?.available_count ?? 1))
watch(productId, () => {
  productQuantity.value = 1
  selectedAttachments.value = []
})
watch(productQuantityLimit, (limit) => {
  productQuantity.value = Math.min(Math.max(1, productQuantity.value), limit)
})
watch(compatibleAttachments, (items) => {
  const availableIds = new Set(items.map(item => item.product.id))
  selectedAttachments.value = selectedAttachments.value.filter(item => availableIds.has(item.product_id))
})
const httpStatus = (value: unknown): number | null => {
  if (!value || typeof value !== 'object') return null
  const errorValue = value as { statusCode?: unknown; status?: unknown }
  if (typeof errorValue.statusCode === 'number') return errorValue.statusCode
  return typeof errorValue.status === 'number' ? errorValue.status : null
}
if (
  !productId.value
  || httpStatus(error.value) === 404
  || httpStatus(categoryError.value) === 404
) {
  throw createError({
    statusCode: 404,
    statusMessage: 'Техника не найдена',
    fatal: true,
  })
}
watch([error, categoryError], ([productError, contextError]) => {
  if (httpStatus(productError) !== 404 && httpStatus(contextError) !== 404) return
  showError({ statusCode: 404, statusMessage: 'Техника не найдена' })
})

const isCategoryRouteProduct = computed(() => props.categoryPath.length > 0)

const normalizedTextPart = (value: string | null | undefined): string => value?.trim() ?? ''
const modelAlreadyContainsMark = (modelName: string, markName: string): boolean => {
  if (!modelName || !markName) return false
  const normalizedModelName = modelName.toLocaleLowerCase('ru-RU')
  const normalizedMarkName = markName.toLocaleLowerCase('ru-RU')
  return normalizedModelName === normalizedMarkName
    || normalizedModelName.startsWith(`${normalizedMarkName} `)
    || normalizedModelName.startsWith(`${normalizedMarkName}-`)
}

const isKitProduct = computed(() => Boolean(product.value?.superstructure))

const allAttributeGroups = computed(() =>
  displayableSpecialEquipmentAttributeGroups(product.value?.attribute_groups ?? []),
)

const chassisAttributeGroups = computed(() =>
  allAttributeGroups.value.filter(group => group.section !== 'superstructure'),
)

const superstructureAttributeGroups = computed(() =>
  allAttributeGroups.value.filter(group => group.section === 'superstructure'),
)

const productDisplayHeading = computed(() => {
  if (!product.value) return 'Спецтехника'
  if (product.value.title) return product.value.title
  return productModel(product.value).name
})

const productSubtitle = computed(() => {
  if (!product.value) return ''
  if (product.value.superstructure) {
    return [
      product.value.modification?.name,
      product.value.superstructure.type_name,
      product.value.superstructure.manufacturer ? `Производитель: ${product.value.superstructure.manufacturer}` : null,
    ].filter(Boolean).join(' · ')
  }
  return modificationWithTrimLabel.value
})

const productBreadcrumbTitle = computed(() => {
  if (!product.value) return 'Спецтехника'
  if (product.value.title) return product.value.title

  const markName = normalizedTextPart(productModel(product.value).mark.name)
  const modelName = normalizedTextPart(productModel(product.value).name)
  const modificationName = normalizedTextPart(product.value.modification?.name)
  const parts = [
    markName && !modelAlreadyContainsMark(modelName, markName) ? markName : '',
    modelName,
    modificationName,
  ].filter((part): part is string => part.length > 0)

  return parts.join(' ') || product.value.slug || product.value.code || 'Спецтехника'
})

const productTitle = computed(() => {
  if (!product.value) return 'Спецтехника'
  if (product.value.title) return product.value.title
  return [
    productModel(product.value).mark.name,
    productModel(product.value).name,
    modificationWithTrimLabel.value,
  ]
    .filter((part): part is string => typeof part === 'string' && part.length > 0)
    .join(' ')
})
const modificationWithTrimLabel = computed(() => {
  if (!product.value) return ''
  return [product.value.modification?.name, product.value.trim?.name]
    .filter((part): part is string => typeof part === 'string' && part.trim().length > 0)
    .join(' · ')
})
const hasSpecialOffer = computed(() => product.value?.price_on_request !== true
  && product.value?.special_price !== null
  && product.value?.special_price !== undefined)
const cardAttributes = computed(() => (product.value?.card_attributes ?? [])
  .flatMap((attribute) => {
    const presentedAttribute = presentSpecialEquipmentDetailAttribute(attribute)
    return presentedAttribute ? [presentedAttribute] : []
  })
  .slice(0, 6))
const warehouseStock = computed(() => (product.value?.warehouse_stock ?? []).filter(stock => stock.count > 0))
const trimAttributeGroups = computed<Array<
  ReturnType<typeof displayableSpecialEquipmentAttributeGroups>[number] & { scope: 'trim' }
>>(() => {
  if (!product.value?.trim_attribute_groups?.length) return []
  return displayableSpecialEquipmentAttributeGroups(product.value.trim_attribute_groups).map(group => ({
    ...group,
    name: group.id === null ? 'Без группы' : group.name,
    scope: 'trim' as const,
  }))
})

const statusLabel = computed(() => product.value ? ({
  available: 'В наличии',
  on_order: 'Под заказ',
  reserved: 'Зарезервировано',
  sold: 'Продано',
  unavailable: 'Недоступно',
})[product.value.sale_status] : '')

const statusClass = computed(() => product.value ? ({
  available: 'bg-storefront-success text-storefront-success-text',
  on_order: 'bg-storefront-info text-storefront-info-text',
  reserved: 'bg-storefront-warning text-storefront-warning-text',
  sold: 'bg-storefront-neutral text-storefront-neutral-text',
  unavailable: 'bg-storefront-unavailable text-storefront-unavailable-text',
})[product.value.sale_status] : '')

const selectedAttachmentProducts = computed(() => {
  const products = new Map(
    compatibleAttachments.value.map(item => [item.product.id, item.product]),
  )
  return selectedAttachments.value.flatMap((selection) => {
    const attachment = products.get(selection.product_id)
    return attachment ? [{ product: attachment, quantity: selection.quantity }] : []
  })
})

const handleCartToggle = async (): Promise<void> => {
  if (!product.value) return
  if (commerce.isStandaloneInCart(product.value.id)) {
    await commerce.removeStandaloneCartProduct(product.value.id)
    return
  }
  await commerce.addCartGroup(
    product.value,
    productQuantity.value,
    selectedAttachmentProducts.value,
    product.value.capabilities.can_add_to_cart,
  )
}

const handleAuthenticated = async () => {
  showAuthModal.value = false
  await commerce.handleAuthenticated()
}

const cancelAuthentication = () => {
  showAuthModal.value = false
}

const requestedProductSlug = computed(() => props.productSlug
  || (typeof route.params.slug === 'string' ? route.params.slug : ''))

if (product.value && requestedProductSlug.value !== product.value.slug) {
  throw createError({
    statusCode: 404,
    statusMessage: 'Объявление не найдено',
    fatal: true,
  })
}

watch([product, requestedProductSlug], ([nextProduct, nextSlug]) => {
  if (nextProduct && nextSlug !== nextProduct.slug) {
    showError({
      statusCode: 404,
      statusMessage: 'Объявление не найдено',
    })
  }
})

const { formatPrice } = useFormatPrice()
const formatCount = (count: number): string => new Intl.NumberFormat('ru-RU').format(Math.max(0, count))
const config = useRuntimeConfig()

useSeoMeta({
  title: () => `${productTitle.value} — спецтехника CarCraft Multileasing`,
  description: () => product.value?.description?.slice(0, 160)
    ?? `${productTitle.value}: характеристики, стоимость, покупка и оформление в лизинг.`,
  ogTitle: () => productTitle.value,
  ogDescription: () => product.value?.description?.slice(0, 160)
    ?? 'Характеристики, стоимость, покупка и оформление спецтехники в лизинг.',
  ogImage: () => toSpecialEquipmentProxyUrl(product.value?.primary_image?.content_url),
})

useHead(() => ({
  link: product.value ? [{
    rel: 'canonical',
    href: `${config.public.siteUrl}${publicRoute(`/special-equipment/products/${encodeURIComponent(product.value.id)}/${encodeURIComponent(product.value.slug)}`)}`,
  }] : [],
}))
</script>
