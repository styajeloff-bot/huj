<template>
  <main data-storefront-block="client.order" class="min-h-screen bg-[color:rgb(var(--storefront-background-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8 sm:py-10">
    <div class="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
      <nav class="mb-6 text-sm text-[color:var(--storefront-text-muted,#4b5563)]" aria-label="Хлебные крошки"><ol class="flex flex-wrap items-center gap-2"><li><NuxtLink :to="publicRoute('/cabinet?tab=my-cars')" class="hover:text-[color:var(--storefront-link-hover,#1e40af)]">Мои заказы</NuxtLink></li><li aria-hidden="true">/</li><li aria-current="page" class="text-[color:var(--storefront-text,#111827)]">Заказ</li></ol></nav>
      <div v-if="loading" class="flex flex-col gap-4" aria-label="Загрузка заказа" aria-busy="true"><div class="h-40 animate-pulse rounded-xl bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" /><div class="h-64 animate-pulse rounded-xl bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" /></div>
      <section v-else-if="error || !order" class="rounded-xl border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-6" role="alert"><h1 class="text-2xl font-bold text-[color:var(--storefront-error-text,#450a0a)]">Заказ недоступен</h1><p class="mt-2 text-sm leading-relaxed text-[color:var(--storefront-error-text,#7f1d1d)]">{{ error }}</p><button type="button" class="storefront-action-secondary mt-4 min-h-11 rounded-lg border border-[color:var(--storefront-destructive-border,#fca5a5)] bg-[color:rgb(var(--storefront-destructive-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-destructive-foreground,#991b1b)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_226_226)/var(--tw-bg-opacity,1))]" @click="loadOrder">Повторить</button></section>
      <template v-else><h1 class="mb-6 text-2xl font-bold tracking-tight text-[color:var(--storefront-title,#030712)] sm:text-3xl">Информация о заказе</h1><CommerceOrderCard :order="order" :has-companies="hasCompanies" expanded-by-default @updated="order = $event" /></template>
    </div>
  </main>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { useAuthStore } from '~/features/auth/store/auth'
import { isUuid, type UUID } from '~/types/ids'
import { isCommerceItemType } from '../adapters/commerceAdapters'
import { createCommerceApi } from '../api/commerceApi'
import { commerceFailureMessage } from '../composables/commerceErrors'
import type { CommerceItemType, CommerceOrder } from '../types'
import CommerceOrderCard from './CommerceOrderCard.vue'

const props = defineProps<{ itemType?: CommerceItemType }>()
const route = useRoute()
const api = createCommerceApi(useRuntimeConfig())
const { publicRoute } = useStorefront()
const authStore = useAuthStore()
const order = ref<CommerceOrder | null>(null)
const loading = ref(true)
const error = ref('')

const orderType = computed<CommerceItemType | null>(() => {
  if (props.itemType) return props.itemType
  const value = Array.isArray(route.params.type) ? route.params.type[0] : route.params.type
  return isCommerceItemType(value) ? value : null
})
const orderId = computed<UUID | null>(() => {
  const value = Array.isArray(route.params.id) ? route.params.id[0] : route.params.id
  return typeof value === 'string' && isUuid(value) ? value : null
})
const hasCompanies = computed(() => Boolean(authStore.user?.company_id))

const loadOrder = async (): Promise<void> => {
  if (!orderType.value || !orderId.value) {
    error.value = 'В адресе указан некорректный тип или идентификатор заказа.'
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    const response = await api.getOrder(orderType.value, orderId.value)
    order.value = response.order
  } catch (requestError: unknown) {
    error.value = commerceFailureMessage(requestError, 'Проверьте подключение и повторите попытку.')
  } finally {
    loading.value = false
  }
}

onMounted(() => { void loadOrder() })
watch([orderType, orderId], ([type, id], [previousType, previousId]) => {
  if (type === previousType && id === previousId) return
  order.value = null
  void loadOrder()
})
useSeoMeta({ title: 'Заказ — CarCraft Multileasing', robots: 'noindex, nofollow' })
</script>
