<template>
  <section data-storefront-block="equipment.detail.attachments"
    v-if="isLoading || hasError || availableItems.length > 0"
    :aria-labelledby="titleId"
    :aria-busy="isLoading"
   class="text-storefront-text">
    <div>
      <h2 :id="titleId" class="text-2xl font-bold tracking-tight text-storefront-title">Совместимые надстройки</h2>
      <p class="mt-2 max-w-3xl text-sm leading-relaxed text-storefront-text-muted">
        Надстройки не выбраны заранее. Отметьте только те, которые хотите добавить к технике.
      </p>
    </div>

    <div v-if="isLoading" class="mt-5 grid gap-3 sm:grid-cols-2" aria-label="Загрузка совместимых надстроек">
      <div v-for="index in 2" :key="index" class="h-48 animate-pulse rounded-xl bg-storefront-skeleton motion-reduce:animate-none" />
    </div>

    <div v-else-if="hasError" class="mt-5 rounded-xl border border-storefront-error-border bg-storefront-error p-5 text-sm text-storefront-error-text" role="alert">
      <p class="font-semibold">Не удалось загрузить совместимые надстройки.</p>
      <button
        type="button"
        class="mt-3 min-h-11 rounded-lg border border-storefront-error-border bg-storefront-surface px-4 font-bold hover:bg-storefront-error-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-destructive"
        @click="emit('retry')"
      >
        Повторить
      </button>
    </div>

    <div v-else class="mt-5 grid gap-3 sm:grid-cols-2">
      <article
        v-for="item in availableItems"
        :key="item.product.id"
        class="flex min-w-0 flex-col rounded-xl border bg-storefront-surface p-4"
        :class="isSelected(item.product.id) ? 'border-storefront-selected-border ring-1 ring-storefront-selected-border' : 'border-storefront-border'"
      >
        <div class="flex min-w-0 gap-3">
          <NuxtLink
            :to="attachmentPath(item)"
            class="grid h-20 w-24 shrink-0 place-items-center overflow-hidden rounded-lg bg-storefront-image focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
            :aria-label="`Открыть ${attachmentTitle(item.product)}`"
          >
            <img
              v-if="attachmentImage(item.product)"
              :src="attachmentImage(item.product) ?? undefined"
              :alt="item.product.primary_image?.alt_text || attachmentTitle(item.product)"
              class="h-full w-full object-contain"
              width="192"
              height="160"
              loading="lazy"
            >
            <WrenchScrewdriverIcon v-else class="h-8 w-8 text-storefront-icon-muted" aria-hidden="true" />
          </NuxtLink>
          <div class="flex min-w-0 flex-1 items-start gap-3">
            <input
              type="checkbox"
              class="mt-1 h-5 w-5 shrink-0 rounded border-storefront-border text-storefront-link focus:ring-storefront-focus storefront-control"
              :checked="isSelected(item.product.id)"
              :aria-label="`Добавить ${attachmentTitle(item.product)}`"
              @change="toggle(item.product.id, ($event.target as HTMLInputElement).checked)"
            >
            <div class="min-w-0">
              <NuxtLink
                :to="attachmentPath(item)"
                class="block text-sm font-bold leading-snug text-storefront-text underline-offset-2 hover:text-storefront-link-hover hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-link"
              >
                {{ attachmentTitle(item.product) }}
              </NuxtLink>
              <p v-if="item.primary_category?.name" class="mt-1 text-xs leading-snug text-storefront-text-muted">
                Конечная категория: <span class="font-semibold text-storefront-text">{{ item.primary_category.name }}</span>
              </p>
              <p class="mt-1 text-xs text-storefront-text-muted">{{ availabilityLabel(item.product) }}</p>
            </div>
          </div>
        </div>

        <dl class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-storefront-text-muted">
          <div class="flex gap-1">
            <dt>Состояние:</dt><dd class="font-semibold text-storefront-value">{{ item.product.condition === 'used' ? 'С пробегом' : 'Новое' }}</dd>
          </div>
          <div v-if="item.product.manufacture_year" class="flex gap-1">
            <dt>Год:</dt><dd class="font-semibold text-storefront-value">{{ item.product.manufacture_year }}</dd>
          </div>
          <div v-if="item.product.mileage_km !== null" class="flex gap-1">
            <dt>Пробег:</dt><dd class="font-semibold text-storefront-value">{{ formatMetric(item.product.mileage_km, 'км') }}</dd>
          </div>
          <div v-if="item.product.engine_hours !== null" class="flex gap-1">
            <dt>Моточасы:</dt><dd class="font-semibold text-storefront-value">{{ formatMetric(item.product.engine_hours, 'м/ч') }}</dd>
          </div>
          <div class="flex gap-1">
            <dt>Статус:</dt><dd class="font-semibold text-storefront-value">{{ statusLabel(item.product) }}</dd>
          </div>
        </dl>

        <div class="mt-auto flex flex-wrap items-end justify-between gap-3 border-t border-storefront-border pt-3">
          <div>
            <p v-if="item.product.price !== null || item.product.price_on_request" class="font-bold tabular-nums text-storefront-text">{{ specialEquipmentPriceLabel(item.product) }}</p>
            <p v-else class="font-bold text-storefront-text">Цена по запросу</p>
            <NuxtLink
              :to="attachmentPath(item)"
              class="mt-1 inline-flex min-h-9 items-center storefront-link text-sm font-semibold text-storefront-link underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
            >
              Открыть отдельно
            </NuxtLink>
          </div>
          <SpecialEquipmentQuantityPicker
            v-if="isSelected(item.product.id)"
            :model-value="selectedQuantity(item.product.id)"
            :max="quantityLimit(item.product)"
            label="Количество надстроек"
            @update:model-value="updateQuantity(item.product.id, $event)"
          />
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { WrenchScrewdriverIcon } from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type { PublicRouteBuilder } from '~/utils/storefrontRoute'
import { specialEquipmentProductPath } from '../categoryNavigation'
import { toSpecialEquipmentProxyUrl } from '../media'
import { specialEquipmentPriceLabel } from '../priceOnRequest'
import {
  productModel,
  type SpecialEquipmentAttachmentSelection,
  type SpecialEquipmentCompatibleAttachment,
  type SpecialEquipmentProductCard,
} from '../types'
import SpecialEquipmentQuantityPicker from './SpecialEquipmentQuantityPicker.vue'

const props = defineProps<{
  items: SpecialEquipmentCompatibleAttachment[]
  modelValue: SpecialEquipmentAttachmentSelection[]
  isLoading: boolean
  hasError: boolean
  publicRoute: PublicRouteBuilder
}>()
const emit = defineEmits<{
  'update:modelValue': [value: SpecialEquipmentAttachmentSelection[]]
  retry: []
}>()
const publicRoute = props.publicRoute
const titleId = `special-equipment-compatible-attachments-${useId()}`
const availableItems = computed(() => props.items
  .filter(item => item.product.sale_status === 'available' || item.product.sale_status === 'on_order')
  .sort((left, right) => left.position - right.position))
const selected = computed(() => new Map(props.modelValue.map(item => [item.product_id, item.quantity])))

const isSelected = (productId: UUID) => selected.value.has(productId)
const selectedQuantity = (productId: UUID) => selected.value.get(productId) ?? 1
const quantityLimit = (product: SpecialEquipmentProductCard) =>
  Math.max(1, product.available_count)
const attachmentTitle = (product: SpecialEquipmentProductCard) => {
  if (product.title) return product.title
  const model = productModel(product)
  return [
    model.mark.name,
    model.name,
    product.modification?.name,
    product.trim?.name,
  ].filter(Boolean).join(' ')
}
const attachmentImage = (product: SpecialEquipmentProductCard) =>
  toSpecialEquipmentProxyUrl(product.primary_image?.content_url)
const attachmentPath = (item: SpecialEquipmentCompatibleAttachment): string =>
  publicRoute(specialEquipmentProductPath(item.product.id, item.product.slug))
const statusLabel = (product: SpecialEquipmentProductCard) =>
  product.sale_status === 'on_order' ? 'Под заказ' : 'В наличии'
const availabilityLabel = (product: SpecialEquipmentProductCard) => product.sale_status === 'on_order'
  ? 'Можно оформить под заказ'
  : `Доступно: ${new Intl.NumberFormat('ru-RU').format(Math.max(0, product.available_count))} шт.`
const formatMetric = (value: number, unit: string) => `${new Intl.NumberFormat('ru-RU').format(value)} ${unit}`

const toggle = (productId: UUID, checked: boolean) => {
  const next = props.modelValue.filter(item => item.product_id !== productId)
  emit('update:modelValue', checked ? [...next, { product_id: productId, quantity: 1 }] : next)
}
const updateQuantity = (productId: UUID, quantity: number) => emit(
  'update:modelValue',
  props.modelValue.map(item => item.product_id === productId ? { ...item, quantity } : item),
)
</script>
