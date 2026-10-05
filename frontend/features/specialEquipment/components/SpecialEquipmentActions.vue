<template>
  <div data-testid="detail-actions" data-storefront-block="equipment.actions" class="flex flex-col gap-3 text-storefront-text">
    <div class="flex gap-2">
      <button
        type="button"
        class="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-storefront-border text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="favoritePending || !product.capabilities.can_favorite"
        :aria-pressed="isFavorite"
        :aria-label="isFavorite ? 'Убрать из избранного' : 'Добавить в избранное'"
        :class="isFavorite ? 'storefront-favorite' : 'storefront-action-ghost'"
        @click="emit('toggle-favorite', product.id)"
      >
        <ArrowPathIcon v-if="favoritePending" class="h-5 w-5 animate-spin motion-reduce:animate-none text-storefront-icon" aria-hidden="true" />
        <HeartIcon v-else class="h-5 w-5 text-storefront-icon" :class="isFavorite ? 'fill-current text-storefront-favorite-icon' : ''" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="inline-flex min-h-12 min-w-0 flex-1 items-center justify-center gap-2 rounded-lg border px-4 text-base font-bold transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus disabled:cursor-not-allowed disabled:border-storefront-disabled-border disabled:bg-storefront-disabled disabled:text-storefront-disabled-foreground"
        :class="isInCart
          ? 'storefront-action-destructive border-storefront-error-border bg-storefront-error text-storefront-error-text hover:bg-storefront-error-hover'
          : 'storefront-action-primary border-storefront-primary-border bg-storefront-primary text-storefront-primary-foreground hover:bg-storefront-primary-hover'"
        :disabled="cartPending || (!isInCart && !product.capabilities.can_add_to_cart)"
        :aria-pressed="isInCart"
        :aria-label="isInCart ? 'Убрать из корзины' : 'Добавить в корзину'"
        @click="emit('toggle-cart', product.id)"
      >
        <ArrowPathIcon v-if="cartPending" class="h-5 w-5 animate-spin motion-reduce:animate-none text-storefront-icon" aria-hidden="true" />
        <ShoppingCartIcon v-else class="h-5 w-5 text-storefront-icon" aria-hidden="true" />
        {{ cartPending ? 'Обновляем…' : isInCart ? 'Убрать из корзины' : 'Добавить в корзину' }}
      </button>
    </div>

    <p v-if="product.capabilities.reason" class="text-sm leading-relaxed text-storefront-text-muted">
      {{ product.capabilities.reason }}
    </p>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowPathIcon,
  HeartIcon,
  ShoppingCartIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type { SpecialEquipmentProductDetail } from '../types'

defineProps<{
  product: SpecialEquipmentProductDetail
  isFavorite: boolean
  isInCart: boolean
  favoritePending: boolean
  cartPending: boolean
}>()

const emit = defineEmits<{
  'toggle-favorite': [productId: UUID]
  'toggle-cart': [productId: UUID]
}>()
</script>
