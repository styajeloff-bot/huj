<template>
  <section data-storefront-block="equipment.cart" class="rounded-xl border border-storefront-border bg-storefront-surface overflow-hidden storefront-shadow-sm text-storefront-text" aria-labelledby="special-equipment-cart-title" :aria-busy="shell.cartLoading">
    <div class="border-b border-storefront-border px-4 py-4 sm:px-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 id="special-equipment-cart-title" class="text-base font-semibold text-storefront-title">
          Спецтехника ({{ shell.cartCount }})
        </h2>
        <div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <NuxtLink
            v-if="authStore.isAuthenticated"
            :to="publicRoute('/cabinet?tab=my-cars')"
            class="inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-storefront-border bg-storefront-surface px-4 text-sm font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus sm:w-auto storefront-action-secondary"
          >
            Мои заказы
          </NuxtLink>
          <NuxtLink
            :to="publicRoute('/special-equipment')"
            class="inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-storefront-border bg-storefront-surface px-4 text-sm font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus sm:w-auto storefront-action-secondary"
          >
            В каталог
          </NuxtLink>
        </div>
      </div>
    </div>

    <div class="p-4 sm:p-6">
      <div v-if="shell.cartLoading && shell.cartProducts.length === 0" class="grid gap-3" aria-label="Загрузка спецтехники в корзине">
        <div v-for="index in 2" :key="index" class="h-40 animate-pulse rounded-xl bg-storefront-skeleton motion-reduce:animate-none" />
      </div>

      <div v-else-if="shell.cartError && shell.cartCount === 0" class="rounded-xl border border-storefront-error-border bg-storefront-error p-5" role="alert">
        <ExclamationTriangleIcon class="h-7 w-7 text-storefront-error-icon" aria-hidden="true" />
        <p class="mt-2 font-bold text-storefront-error-text">{{ shell.cartError }}</p>
        <button
          type="button"
          class="mt-4 min-h-11 rounded-lg border border-storefront-error-border bg-storefront-surface px-4 text-sm font-bold text-storefront-error-text hover:bg-storefront-error-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-destructive"
          @click="loadCart(true)"
        >
          Повторить
        </button>
      </div>

      <div v-else-if="shell.cartCount === 0" class="rounded-xl border border-dashed border-storefront-border bg-storefront-surface p-6 text-center">
        <TruckIcon class="mx-auto h-10 w-10 text-storefront-icon-muted" aria-hidden="true" />
        <p class="mt-3 font-bold text-storefront-text">Спецтехника пока не добавлена</p>
        <p class="mt-1 text-sm text-storefront-text-muted">Добавьте технику из каталога, чтобы оформить покупку или лизинг.</p>
      </div>

      <div v-else class="space-y-3">
        <div v-if="shell.cartError" class="rounded-lg border border-storefront-warning-border bg-storefront-warning px-4 py-3 text-sm text-storefront-warning-text" role="status">
          {{ shell.cartError }}
          <button type="button" class="ml-2 font-bold underline underline-offset-2" @click="loadCart(true)">Обновить</button>
        </div>

        <article
          v-for="product in shell.cartProducts"
          :key="product.id"
          class="grid gap-4 rounded-xl border border-storefront-border bg-storefront-surface p-4 sm:grid-cols-[8rem_minmax(0,1fr)] sm:p-5"
        >
          <component
            :is="specialEquipmentProductLocation(product, publicRoute) ? NuxtLink : 'div'"
            :to="specialEquipmentProductLocation(product, publicRoute) ?? undefined"
            class="block aspect-[4/3] overflow-hidden rounded-lg bg-storefront-image focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
          >
            <img
              v-if="imageUrl(product)"
              :src="imageUrl(product) ?? undefined"
              :alt="specialEquipmentProductTitle(product)"
              class="h-full w-full object-cover"
              width="320"
              height="240"
            >
            <span v-else class="grid h-full place-items-center bg-storefront-image text-storefront-text-muted">
              <TruckIcon class="h-9 w-9 text-storefront-icon" aria-hidden="true" />
              <span class="sr-only">Изображение отсутствует</span>
            </span>
          </component>

          <div class="min-w-0">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <component
                  :is="specialEquipmentProductLocation(product, publicRoute) ? NuxtLink : 'span'"
                  :to="specialEquipmentProductLocation(product, publicRoute) ?? undefined"
                  class="rounded-sm text-lg font-bold text-storefront-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
                  :class="specialEquipmentProductLocation(product, publicRoute) ? 'hover:text-storefront-link-hover' : ''"
                >
                  {{ specialEquipmentProductTitle(product) }}
                </component>
                <p v-if="product.manufacture_year" class="mt-1 text-sm text-storefront-text-muted">{{ product.manufacture_year }} год</p>
                <p class="mt-2 text-lg font-bold tabular-nums text-storefront-price">
                  {{ specialEquipmentPriceLabel(product) }}
                </p>
              </div>
              <button
                type="button"
                class="grid min-h-11 min-w-11 place-items-center rounded-lg text-storefront-text-muted hover:bg-storefront-error-hover hover:text-storefront-error-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus disabled:cursor-wait disabled:opacity-50 storefront-action-destructive"
                :disabled="removingIds.has(product.id)"
                :aria-label="`Удалить ${specialEquipmentProductTitle(product)} из корзины`"
                @click="removeProduct(product.id)"
              >
                <ArrowPathIcon v-if="removingIds.has(product.id)" class="h-5 w-5 animate-spin motion-reduce:animate-none text-storefront-icon" aria-hidden="true" />
                <TrashIcon v-else class="h-5 w-5 text-storefront-icon" aria-hidden="true" />
              </button>
            </div>

            <div class="mt-4 flex flex-wrap gap-2">
              <button
                v-if="product.capabilities.can_lease"
                type="button"
                class="inline-flex min-h-11 items-center justify-center rounded-lg bg-storefront-primary px-4 text-sm font-bold text-storefront-primary-foreground hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-primary"
                @click="openCheckout(product.id, 'leasing')"
              >
                Оформить в лизинг
                <ArrowRightIcon class="ml-2 h-4 w-4 text-storefront-icon" aria-hidden="true" />
              </button>
              <button
                v-if="product.capabilities.can_buy"
                type="button"
                class="inline-flex min-h-11 items-center justify-center rounded-lg border border-storefront-border px-4 text-sm font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
                @click="openPurchase(product.id, 'full_purchase')"
              >
                Купить
              </button>
              <button
                v-if="product.capabilities.can_preorder"
                type="button"
                class="inline-flex min-h-11 items-center justify-center rounded-lg border border-storefront-border px-4 text-sm font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
                @click="openPurchase(product.id, product.sale_status === 'on_order' ? 'preorder' : 'reservation')"
              >
                Внести предоплату
              </button>
            </div>
          </div>
        </article>

        <div
          v-for="productId in shell.unresolvedCartIds"
          :key="productId"
          class="flex flex-col gap-3 rounded-xl border border-storefront-warning-border bg-storefront-warning p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p class="font-bold text-storefront-warning-text">Карточка техники временно недоступна</p>
            <p class="mt-1 break-all font-mono text-xs text-storefront-warning-text">{{ productId }}</p>
          </div>
          <button type="button" class="min-h-11 rounded-lg border border-storefront-warning-border bg-storefront-surface px-4 text-sm font-bold text-storefront-warning-text hover:bg-storefront-warning-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus" :disabled="removingIds.has(productId)" @click="removeProduct(productId)">
            Удалить из корзины
          </button>
        </div>

        <p v-if="!authStore.isAuthenticated" class="rounded-lg bg-storefront-selected px-4 py-3 text-sm leading-relaxed text-storefront-link">
          Состав корзины сохранён в этом браузере. При оформлении потребуется войти — позиции будут перенесены в аккаунт.
        </p>
      </div>
    </div>

    <CommercePurchaseModal
      :show="purchaseProductId !== null"
      :items="purchaseItemRefs"
      :initial-purchase-type="purchaseType"
      @close="closePurchase"
      @success="handlePurchaseSuccess"
    />
    <AuthModal
      v-if="showAuthModal"
      @close="cancelAuthentication"
      @authenticated="handleAuthenticated"
    />
  </section>
</template>

<script setup lang="ts">
import { NuxtLink } from '#components'
import {
  ArrowPathIcon,
  ArrowRightIcon,
  ExclamationTriangleIcon,
  TrashIcon,
  TruckIcon,
} from '@heroicons/vue/24/outline'
import AuthModal from '~/features/auth/components/AuthModal.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import CommercePurchaseModal from '~/features/commerce/components/CommercePurchaseModal.vue'
import type { CommerceCheckoutIntent, CommercePurchaseSelection, CommercePurchaseType } from '~/features/commerce/types'
import type { UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'
import {
  specialEquipmentCheckoutLocation,
  specialEquipmentProductLocation,
  specialEquipmentProductTitle,
} from '../composables/commerceShellAdapter'
import { specialEquipmentFailureMessage } from '../composables/checkout'
import { toSpecialEquipmentProxyUrl } from '../media'
import { useSpecialEquipmentCommerceShellStore } from '../store/commerceShell'
import type { SpecialEquipmentCommerceProduct } from '../types'
import { specialEquipmentPriceLabel } from '../priceOnRequest'

interface SectionState {
  ready: boolean
  loading: boolean
  count: number
  hasError: boolean
}

const emit = defineEmits<{
  stateChange: [state: SectionState]
}>()

const authStore = useAuthStore()
const { publicRoute } = useStorefront()
const shell = useSpecialEquipmentCommerceShellStore()
const toast = useToast()
const removingIds = ref<Set<UUID>>(new Set())
const purchaseProductId = ref<UUID | null>(null)
const purchaseType = ref<CommercePurchaseType | null>(null)
const showAuthModal = ref(false)
const pendingCheckout = ref<{ productId: UUID; intent: CommerceCheckoutIntent } | null>(null)
const purchaseItemRefs = computed<CommercePurchaseSelection[]>(() => purchaseProductId.value
  ? [{ item: { type: 'special_equipment', id: purchaseProductId.value }, quantity: 1 }]
  : [])

const imageUrl = (product: SpecialEquipmentCommerceProduct) =>
  toSpecialEquipmentProxyUrl(product.primary_image?.content_url)

const replaceRemoving = (productId: UUID, enabled: boolean) => {
  const next = new Set(removingIds.value)
  if (enabled) next.add(productId)
  else next.delete(productId)
  removingIds.value = next
}

const loadCart = async (force = false) => {
  await shell.loadCart({ force, resolveGuestProducts: true })
}

const removeProduct = async (productId: UUID) => {
  if (removingIds.value.has(productId)) return
  replaceRemoving(productId, true)
  try {
    await shell.removeProductCartItems(productId)
    toast.success('Спецтехника удалена из корзины')
  } catch (error: unknown) {
    toast.error(specialEquipmentFailureMessage(error, 'Не удалось удалить технику из корзины'))
  } finally {
    replaceRemoving(productId, false)
  }
}

const openCheckout = async (productId: UUID, intent: CommerceCheckoutIntent): Promise<void> => {
  if (!authStore.isAuthenticated) {
    pendingCheckout.value = { productId, intent }
    showAuthModal.value = true
    return
  }
  if (intent === 'leasing') {
    await navigateTo(specialEquipmentCheckoutLocation(productId, intent, publicRoute))
    return
  }
  purchaseProductId.value = productId
  purchaseType.value = intent
}

const openPurchase = (productId: UUID, intent: CommercePurchaseType): void => {
  void openCheckout(productId, intent)
}

const closePurchase = (): void => {
  purchaseProductId.value = null
  purchaseType.value = null
}

const handlePurchaseSuccess = async (): Promise<void> => {
  const productId = purchaseProductId.value
  if (productId) {
    try {
      await shell.removeProductCartItems(productId)
    } catch (error: unknown) {
      toast.error(specialEquipmentFailureMessage(error, 'Заказ создан, но позицию не удалось убрать из корзины'))
    }
  }
  await shell.loadCart({ force: true, resolveGuestProducts: true })
}

const handleAuthenticated = async (): Promise<void> => {
  showAuthModal.value = false
  await authStore.checkAuth(true)
  await shell.loadCart({ force: true, resolveGuestProducts: true })
  const pending = pendingCheckout.value
  pendingCheckout.value = null
  if (pending) await openCheckout(pending.productId, pending.intent)
}

const cancelAuthentication = (): void => {
  showAuthModal.value = false
  pendingCheckout.value = null
}

watch(
  [() => shell.cartInitialized, () => shell.cartLoading, () => shell.cartCount, () => shell.cartError],
  ([ready, loading, count, cartError]) => emit('stateChange', { ready, loading, count, hasError: Boolean(cartError) }),
  { immediate: true },
)

watch(() => authStore.isAuthenticated, () => loadCart(true))

onMounted(() => loadCart())
</script>
