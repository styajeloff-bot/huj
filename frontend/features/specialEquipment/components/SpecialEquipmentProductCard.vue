<template>
  <article data-storefront-block="equipment.card" class="group relative grid grid-cols-[minmax(12rem,32%)_minmax(0,1fr)] overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface text-storefront-text">
    <div class="relative aspect-[4/3] min-w-0 self-start overflow-hidden bg-storefront-image">
      <NuxtLink :to="productUrl" class="block h-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-storefront-focus">
        <img
          v-if="imageUrl && !imageFailed"
          :src="imageUrl"
          :alt="product.primary_image?.alt_text || productTitle"
          class="h-full w-full object-contain transition-transform duration-200 group-hover:scale-[1.02] motion-reduce:transition-none"
          width="640"
          height="480"
          loading="lazy"
          @error="imageFailed = true"
        >
        <div v-else class="grid h-full place-items-center text-storefront-text-muted">
          <TruckIcon class="h-14 w-14 text-storefront-icon" aria-hidden="true" />
          <span class="sr-only">Изображение отсутствует</span>
        </div>
      </NuxtLink>
      <span
        data-testid="equipment-card-status"
        class="absolute left-3 top-3 rounded-full px-2.5 py-1 text-xs font-semibold"
        :class="statusClass"
      >
        {{ statusLabel }}
      </span>
    </div>

    <button
      type="button"
      class="absolute right-3 top-3 grid h-11 w-11 place-items-center rounded-full bg-storefront-surface/95 text-storefront-text-muted storefront-shadow-sm hover:text-storefront-favorite-icon focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus disabled:cursor-not-allowed disabled:opacity-50"
      :class="isFavorite ? 'storefront-favorite' : 'storefront-action-ghost'"
      :disabled="favoritePending || !product.capabilities.can_favorite"
      :aria-label="isFavorite ? 'Удалить из избранного' : 'Добавить в избранное'"
      :aria-pressed="isFavorite"
      @click="emit('toggle-favorite', product.id)"
    >
      <ArrowPathIcon v-if="favoritePending" class="h-5 w-5 animate-spin motion-reduce:animate-none text-storefront-icon" aria-hidden="true" />
      <HeartIcon v-else class="h-5 w-5 text-storefront-icon" :class="isFavorite ? 'fill-current' : ''" aria-hidden="true" />
    </button>

    <div class="min-w-0 p-4">
      <div class="pr-12">
        <p v-if="product.terminal_category" class="mb-1 break-words text-xs font-semibold uppercase tracking-wide text-storefront-text-muted">
          {{ product.terminal_category.name }}
        </p>
        <h2 data-testid="equipment-card-title" class="break-words text-lg font-bold leading-snug text-storefront-title">
          <NuxtLink :to="productUrl" class="rounded-sm hover:text-storefront-link-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-link">
            {{ cardHeading }}
          </NuxtLink>
        </h2>
        <p v-if="cardSubtitle" class="mt-1 break-words text-sm leading-snug text-storefront-text-muted">
          {{ cardSubtitle }}
        </p>
      </div>

      <dl class="mt-3 flex flex-wrap gap-x-3 gap-y-1 bg-storefront-surface-muted text-xs text-storefront-value">
        <div class="flex items-center gap-1.5">
          <SparklesIcon class="h-4 w-4 text-storefront-icon-muted" aria-hidden="true" />
          <dt class="sr-only">Состояние</dt>
          <dd>{{ product.condition === 'used' ? 'С пробегом' : 'Новое' }}</dd>
        </div>
        <div v-if="product.manufacture_year" class="flex items-center gap-1.5">
          <CalendarDaysIcon class="h-4 w-4 text-storefront-icon-muted" aria-hidden="true" />
          <dt class="sr-only">Год выпуска</dt>
          <dd>{{ product.manufacture_year }} г.</dd>
        </div>
        <div v-if="usageLabel" class="flex items-center gap-1.5">
          <ClockIcon class="h-4 w-4 text-storefront-icon-muted" aria-hidden="true" />
          <dt class="sr-only">Наработка</dt>
          <dd>{{ usageLabel }}</dd>
        </div>
        <div v-if="product.body_color" class="flex min-w-0 items-center gap-1.5">
          <span
            v-if="bodyColorCode"
            class="h-4 w-4 shrink-0 rounded-full border border-storefront-border"
            :style="{ backgroundColor: bodyColorCode }"
            aria-hidden="true"
          />
          <PaintBrushIcon v-else class="h-4 w-4 shrink-0 text-storefront-icon-muted" aria-hidden="true" />
          <dt class="sr-only">Цвет кузова</dt>
          <dd class="min-w-0 break-words">{{ product.body_color.name }}</dd>
        </div>
      </dl>

      <dl v-if="cardAttributes.length" data-testid="equipment-card-attributes" class="mt-3 grid grid-cols-3 gap-x-3 gap-y-2 border-t border-storefront-border bg-storefront-surface-muted pt-3 text-xs leading-snug">
        <div v-for="attribute in cardAttributes" :key="attribute.id" class="min-w-0">
          <dt class="break-words text-storefront-label">{{ attribute.name }}</dt>
          <dd class="mt-0.5 break-words font-semibold text-storefront-value">{{ attribute.formatted_value }}</dd>
        </div>
      </dl>

      <div class="mt-3 border-t border-storefront-border pt-3">
        <div class="grid grid-cols-2 items-end gap-3">
          <div v-if="warehouseSummary" data-testid="equipment-card-stock" class="flex min-w-0 items-start gap-1.5 text-xs leading-snug text-storefront-text-muted">
            <BuildingStorefrontIcon class="mt-0.5 h-4 w-4 shrink-0 text-storefront-icon-muted" aria-hidden="true" />
            <p class="min-w-0 break-words">{{ warehouseSummary }}</p>
          </div>
          <div data-testid="equipment-card-price" class="col-start-2 min-w-0 text-right">
            <template v-if="product.price !== null || product.price_on_request">
              <p class="break-words text-xl font-bold leading-tight tabular-nums text-storefront-price">{{ specialEquipmentPriceLabel(product) }}</p>
              <p v-if="hasSpecialOffer && product.base_price !== null" class="mt-0.5 text-xs tabular-nums text-storefront-text-muted line-through">
                {{ formatPrice(product.base_price) }}
              </p>
              <p v-if="hasSpecialOffer" class="mt-0.5 text-xs font-bold uppercase tracking-wide text-storefront-success-text">
                Спецпредложение
              </p>
            </template>
            <p v-else class="text-lg font-bold leading-tight text-storefront-price">Цена по запросу</p>
          </div>
        </div>

        <div class="mt-3 grid grid-cols-2 gap-2">
          <NuxtLink
            :to="productUrl"
            class="inline-flex min-h-11 items-center justify-center rounded-lg border border-storefront-border px-3 text-sm font-semibold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
          >
            Подробнее
          </NuxtLink>
          <button
            type="button"
            class="inline-flex min-h-11 items-center justify-center rounded-lg border px-3 text-sm font-semibold transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:border-storefront-disabled-border disabled:bg-storefront-disabled disabled:text-storefront-disabled-foreground"
            :class="isInCart
              ? 'storefront-action-destructive border-storefront-error-border bg-storefront-error text-storefront-error-text hover:bg-storefront-error-hover'
              : 'storefront-action-primary border-storefront-primary-border bg-storefront-primary text-storefront-primary-foreground hover:border-storefront-primary-border hover:bg-storefront-primary-hover'"
            :disabled="cartPending || (!isInCart && !product.capabilities.can_add_to_cart)"
            :aria-pressed="isInCart"
            :aria-label="isInCart ? 'Убрать из корзины' : 'Добавить в корзину'"
            @click="emit('toggle-cart', product.id)"
          >
            <ArrowPathIcon v-if="cartPending" class="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none text-storefront-icon" aria-hidden="true" />
            {{ cartPending ? 'Обновляем…' : isInCart ? 'Убрать' : 'В корзину' }}
          </button>
        </div>
        <p v-if="product.capabilities.reason && !product.capabilities.can_add_to_cart" class="mt-2 text-sm text-storefront-text-muted">
          {{ product.capabilities.reason }}
        </p>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowPathIcon,
  CalendarDaysIcon,
  ClockIcon,
  HeartIcon,
  BuildingStorefrontIcon,
  PaintBrushIcon,
  SparklesIcon,
  TruckIcon,
} from '@heroicons/vue/24/outline'
import { useFormatPrice } from '~/composables/useFormatPrice'
import type { UUID } from '~/types/ids'
import { getColorCode } from '~/utils/colorCode'
import type { PublicRouteBuilder } from '~/utils/storefrontRoute'
import type { SpecialEquipmentProductCard } from '../types'
import { specialEquipmentProductPath } from '../categoryNavigation'
import { toSpecialEquipmentProxyUrl } from '../media'
import { specialEquipmentPriceLabel } from '../priceOnRequest'
import { formatSpecialEquipmentAttribute } from '../attributeDisplay'

const props = defineProps<{
  product: SpecialEquipmentProductCard
  isFavorite: boolean
  isInCart: boolean
  favoritePending: boolean
  cartPending: boolean
  categoryPath?: string[]
  publicRoute: PublicRouteBuilder
}>()

const emit = defineEmits<{
  'toggle-favorite': [productId: UUID]
  'toggle-cart': [productId: UUID]
}>()

const { formatPrice } = useFormatPrice()
const publicRoute = props.publicRoute
const imageFailed = ref(false)
const imageUrl = computed(() => toSpecialEquipmentProxyUrl(props.product.primary_image?.content_url))

const cardHeading = computed(() => {
  if (props.product.title) return props.product.title
  const model = props.product.model || props.product.modification?.model
  return [model?.mark?.name, model?.name].filter(Boolean).join(' ')
})

const modificationWithTrimLabel = computed(() => [
  props.product.modification?.name,
  props.product.trim?.name,
]
  .filter((part): part is string => typeof part === 'string' && part.trim().length > 0)
  .join(' · '))

const cardSubtitle = computed(() => {
  if (props.product.superstructure) {
    return [
      props.product.modification?.name,
      props.product.superstructure.type_name,
      props.product.superstructure.manufacturer ? `Производитель: ${props.product.superstructure.manufacturer}` : null,
    ].filter(Boolean).join(' · ')
  }
  return modificationWithTrimLabel.value
})

const productTitle = computed(() =>
  [cardHeading.value, cardSubtitle.value]
    .filter((part): part is string => typeof part === 'string' && part.length > 0)
    .join(' '),
)

const productUrl = computed(() =>
  publicRoute(specialEquipmentProductPath(
    props.product.id,
    props.product.slug,
    props.categoryPath ?? [],
  )),
)
const usageLabel = computed(() => {
  if (props.product.condition !== 'used') return ''
  if (props.product.engine_hours !== null) {
    return `${new Intl.NumberFormat('ru-RU').format(props.product.engine_hours)} м/ч`
  }
  if (props.product.mileage_km !== null) {
    return `${new Intl.NumberFormat('ru-RU').format(props.product.mileage_km)} км`
  }
  return ''
})
const bodyColorCode = computed(() => getColorCode(props.product.body_color?.name))
const hasSpecialOffer = computed(() => !props.product.price_on_request
  && props.product.special_price !== null
  && props.product.special_price !== undefined)
const cardAttributes = computed(() => (props.product.card_attributes ?? [])
  .flatMap((attribute) => {
    const formattedValue = formatSpecialEquipmentAttribute(attribute)
    return formattedValue === null ? [] : [{ ...attribute, formatted_value: formattedValue }]
  })
  .slice(0, 6))
const warehouseSummary = computed(() => {
  const stocks = (props.product.warehouse_stock ?? []).filter(stock => stock.count > 0)
  if (!stocks.length) return props.product.warehouse_city_name
    ? `Город склада: ${props.product.warehouse_city_name}`
    : ''
  const locations = stocks.map(stock =>
    `${stock.address} — ${new Intl.NumberFormat('ru-RU').format(stock.count)} шт.`)
  return `Склад: ${locations.join('; ')}`
})

const statusLabel = computed(() => ({
  available: 'В наличии',
  on_order: 'Под заказ',
  reserved: 'Зарезервировано',
  sold: 'Продано',
  unavailable: 'Недоступно',
})[props.product.sale_status])

const statusClass = computed(() => ({
  available: 'bg-storefront-success text-storefront-success-text',
  on_order: 'bg-storefront-info text-storefront-info-text',
  reserved: 'bg-storefront-warning text-storefront-warning-text',
  sold: 'bg-storefront-neutral text-storefront-neutral-text',
  unavailable: 'bg-storefront-unavailable text-storefront-unavailable-text',
})[props.product.sale_status])
</script>
