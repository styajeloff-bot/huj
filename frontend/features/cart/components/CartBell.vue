<template>
  <div data-storefront-block="client.cart" class="relative">
    <button
      type="button"
      class="storefront-action-ghost group relative grid min-h-[44px] min-w-[44px] place-items-center rounded-lg p-[8px] text-[color:var(--storefront-primary-foreground,#4b5563)] transition-colors duration-200 hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] hover:text-[color:var(--storefront-primary-hover-foreground,#2563eb)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
      title="Корзина"
      :aria-label="count > 0 ? `Корзина, ${count}` : 'Корзина'"
      :aria-expanded="showCart"
      @click="toggleCart"
    >
      <svg class="h-[20px] w-[20px] transition-transform duration-200 group-hover:scale-110" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6h13.5l-1.5 9H8.5L6 6z" />
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6L4 4H2" />
        <circle cx="9" cy="20" r="1.5" stroke-width="2" />
        <circle cx="18" cy="20" r="1.5" stroke-width="2" />
      </svg>

      <span
        v-if="count > 0"
        class="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-[color:rgb(var(--storefront-primary-rgb,59_130_246)/var(--tw-bg-opacity,1))] px-1 text-xs font-medium text-[color:var(--storefront-primary-foreground,#ffffff)]"
        aria-hidden="true"
      >
        {{ count > 99 ? '99+' : count }}
      </span>
    </button>

    <div
      v-if="showCart"
      class="fixed inset-x-2 top-[4.5rem] z-50 max-h-[calc(100dvh-5rem)] w-auto overflow-hidden rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-2xl lg:absolute lg:inset-x-auto lg:right-0 lg:top-full lg:mt-2 lg:max-h-[32rem] lg:w-96"
    >
      <div class="border-b border-[color:var(--storefront-border,#f3f4f6)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4">
        <div class="flex items-center justify-between">
          <h3 class="flex items-center text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
            <svg class="mr-2 h-5 w-5 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6h13.5l-1.5 9H8.5L6 6z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6L4 4H2" />
              <circle cx="9" cy="20" r="1.5" stroke-width="2" />
              <circle cx="18" cy="20" r="1.5" stroke-width="2" />
            </svg>
            Корзина
          </h3>
          <button
            type="button"
            class="storefront-action-ghost grid min-h-11 min-w-11 place-items-center rounded-full transition-colors duration-200 hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,229_231_235)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
            aria-label="Закрыть корзину"
            @click="showCart = false"
          >
            <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ count }} {{ getItemsText(count) }}</p>
      </div>

      <div class="max-h-72 overflow-y-auto overscroll-contain">
        <div v-if="loading" class="grid gap-3 p-4" aria-busy="true" aria-label="Загрузка корзины">
          <div v-for="index in Math.max(count, 1)" :key="index" class="h-20 animate-pulse rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" />
        </div>

        <div v-else-if="isEmpty" class="p-6 text-center">
          <svg class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6 6h13.5l-1.5 9H8.5L6 6z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6 6L4 4H2" />
            <circle cx="9" cy="20" r="1.5" stroke-width="1.5" />
            <circle cx="18" cy="20" r="1.5" stroke-width="1.5" />
          </svg>
          <p class="mt-4 font-medium text-[color:var(--storefront-text-muted,#4b5563)]">Корзина пуста</p>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Добавьте транспортное средство для оформления</p>
        </div>

        <div v-else class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
          <article
            v-for="item in items"
            :key="itemKey(item)"
            class="p-4 transition-colors duration-200 hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
          >
            <div class="flex items-start gap-3">
              <component
                :is="item.detail_url ? NuxtLink : 'div'"
                :to="item.detail_url ?? undefined"
                class="text-[color:var(--storefront-icon,inherit)] relative flex h-14 w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] transition-opacity duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
                :class="item.detail_url ? 'hover:opacity-80' : ''"
                @click="item.detail_url && (showCart = false)"
              >
                <img
                  v-if="item.image_url && !failedImages.has(itemKey(item))"
                  :src="item.image_url"
                  :alt="itemTitle(item)"
                  class="h-full w-full object-contain"
                  @error="markImageFailed(item)"
                >
                <svg v-else class="h-6 w-6 text-[color:var(--storefront-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M4 16l4.586-4.586a2 2 0 0 1 2.828 0L16 16m-2-2 1.586-1.586a2 2 0 0 1 2.828 0L20 14M6 20h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2Z" />
                </svg>
                <span v-if="item.year" class="absolute right-0.5 top-0.5 rounded bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.65)] px-1 py-0.5 text-[10px] font-medium leading-none text-[color:var(--storefront-text,#ffffff)]">
                  {{ item.year }} г.
                </span>
              </component>

              <div class="min-w-0 flex-1">
                <component
                  :is="item.detail_url ? NuxtLink : 'div'"
                  :to="item.detail_url ?? undefined"
                  class="text-[color:var(--storefront-icon,inherit)] block rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
                  @click="item.detail_url && (showCart = false)"
                >
                  <h4 class="truncate text-sm font-medium text-[color:var(--storefront-title,#111827)]" :class="item.detail_url ? 'hover:text-[color:var(--storefront-title,#2563eb)]' : ''">{{ itemTitle(item) }}</h4>
                </component>
                <p v-if="item.group_name" class="mt-1 truncate text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ item.group_name }}</p>
                <div class="mt-2 flex items-center justify-between gap-2">
                  <span class="text-sm font-semibold tabular-nums text-[color:var(--storefront-text,#111827)]">{{ formatPrice(commerceCartLinePrice(item)) }}</span>
                  <button
                    type="button"
                    class="storefront-action-ghost grid min-h-9 min-w-9 place-items-center rounded text-[color:var(--storefront-destructive-foreground,#ef4444)] transition-colors duration-200 hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))] hover:text-[color:var(--storefront-destructive-hover-foreground,#b91c1c)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#dc2626)] disabled:cursor-wait disabled:opacity-50"
                    :disabled="removingKeys.has(itemKey(item))"
                    :aria-label="`Удалить ${itemTitle(item)} из корзины`"
                    @click="removeLine(item)"
                  >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0 1 16.138 21H7.862a2 2 0 0 1-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </article>

          <div v-if="unresolvedCount > 0" class="flex min-h-20 items-center gap-3 p-4 text-sm text-[color:var(--storefront-text-muted,#4b5563)]" role="status">
            <span class="h-10 w-16 animate-pulse rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" aria-hidden="true" />
            Загружаем {{ unresolvedCount }} {{ getItemsText(unresolvedCount) }}
          </div>
        </div>
      </div>

      <div v-if="!isEmpty" class="border-t border-[color:var(--storefront-border,#f3f4f6)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4">
        <div class="flex gap-2">
          <button
            type="button"
            class="storefront-action-ghost min-h-11 flex-1 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] px-3 py-2 text-sm text-[color:var(--storefront-secondary-foreground,#4b5563)] transition-colors duration-200 hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] disabled:cursor-wait disabled:opacity-50"
            :disabled="clearing"
            @click="clearAll"
          >
            {{ clearing ? 'Очищаем…' : 'Очистить' }}
          </button>
          <NuxtLink
            :to="publicRoute('/cart')"
            class="storefront-action-primary inline-flex min-h-11 flex-1 items-center justify-center rounded-storefront-control bg-storefront-primary px-3 py-2 text-center text-sm text-storefront-primary-foreground transition-colors duration-200 hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2"
            @click="showCart = false; trackGoal('main_shopping_cart_enter')"
          >
            В корзину
          </NuxtLink>
        </div>
      </div>
    </div>

    <div v-if="showCart" class="fixed inset-0 z-40" aria-hidden="true" @click="showCart = false" />
  </div>
</template>

<script setup lang="ts">
import { NuxtLink } from '#components'
import {
  commerceCartLinePrice,
  type CommerceCartLine,
} from '~/features/commerce/cartProjection'
import type { CommerceItemRef } from '~/features/commerce/types'
import type { UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'

const props = withDefaults(defineProps<{
  items?: readonly CommerceCartLine[]
  count?: number
  loadItems?: () => Promise<void>
  removeItem?: (item: CommerceItemRef, cartItemId?: UUID) => Promise<void>
  clearCart?: () => Promise<void>
}>(), {
  items: () => [],
  count: 0,
  loadItems: undefined,
  removeItem: undefined,
  clearCart: undefined,
})

const toast = useToast()
const { publicRoute } = useStorefront()
const { formatPrice } = useFormatPrice()
const showCart = ref(false)
const loading = ref(false)
const clearing = ref(false)
const removingKeys = ref<Set<string>>(new Set())
const failedImages = ref<Set<string>>(new Set())
const supportedItemTypes = new Set<CommerceItemRef['type']>(['vehicle', 'special_equipment'])

const isEmpty = computed(() => props.count === 0)
const unresolvedCount = computed(() => Math.max(0, props.count - props.items.length))

const itemKey = (item: CommerceCartLine) => `${item.ref.type}:${item.cart_id}`
const itemTitle = (item: CommerceCartLine) => `${item.mark_name} ${item.model_name}`.trim() || 'Транспортное средство'

const replaceSetValue = (target: Ref<Set<string>>, value: string, enabled: boolean) => {
  const next = new Set(target.value)
  if (enabled) next.add(value)
  else next.delete(value)
  target.value = next
}

const toggleCart = async () => {
  showCart.value = !showCart.value
  if (!showCart.value || !props.loadItems) return
  loading.value = true
  try {
    await props.loadItems()
  } catch {
    toast.error('Не удалось загрузить корзину')
  } finally {
    loading.value = false
  }
}

const removeLine = async (item: CommerceCartLine) => {
  if (!props.removeItem || !supportedItemTypes.has(item.ref.type)) return
  const key = itemKey(item)
  if (removingKeys.value.has(key)) return
  replaceSetValue(removingKeys, key, true)
  try {
    await props.removeItem(item.ref, item.cart_id)
    toast.success('Удалено из корзины')
  } catch {
    toast.error('Не удалось удалить позицию из корзины')
  } finally {
    replaceSetValue(removingKeys, key, false)
  }
}

const clearAll = async () => {
  if (!props.clearCart || clearing.value || !confirm('Очистить корзину?')) return
  clearing.value = true
  try {
    await props.clearCart()
    toast.success('Корзина очищена')
    showCart.value = false
  } catch {
    toast.error('Не удалось полностью очистить корзину')
  } finally {
    clearing.value = false
  }
}

const markImageFailed = (item: CommerceCartLine) => {
  replaceSetValue(failedImages, itemKey(item), true)
}

const getItemsText = (value: number) => {
  if (value % 10 === 1 && value % 100 !== 11) return 'позиция'
  if ([2, 3, 4].includes(value % 10) && ![12, 13, 14].includes(value % 100)) return 'позиции'
  return 'позиций'
}

const trackGoal = (goalName: string) => {
  if (typeof window !== 'undefined' && window.ym) window.ym(103750838, 'reachGoal', goalName)
}
</script>
