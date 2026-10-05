<template>
  <section data-storefront-block="client.order" aria-labelledby="commerce-orders-title">
    <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 id="commerce-orders-title" class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">Мои заказы</h2>
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          {{ isSpecialEquipmentCatalogVisible ? 'Автомобили и спецтехника в одном списке.' : 'Покупки автомобилей.' }}
        </p>
      </div>
      <div class="flex flex-col gap-3 sm:flex-row">
        <label v-if="isSpecialEquipmentCatalogVisible" class="text-sm text-[color:var(--storefront-label,#4b5563)]"><span class="mb-1 block">Тип техники</span><select v-model="typeFilter" class="storefront-control min-h-10 rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"><option value="">Все</option><option value="vehicle">Автомобили</option><option value="special_equipment">Спецтехника</option></select></label>
        <label class="text-sm text-[color:var(--storefront-label,#4b5563)]"><span class="mb-1 block">Статус</span><select v-model="statusFilter" class="storefront-control min-h-10 rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"><option value="">Все</option><option value="reserved">Зарезервировано</option><option value="purchased">Куплено</option><option v-if="hasCompanies" value="leasing_pending">Ждёт лизинга</option><option v-if="hasCompanies" value="leasing_active">В лизинге</option><option value="cancellation_requested">Запрос на отмену</option><option value="cancelled">Отменено</option></select></label>
      </div>
    </div>

    <div v-if="loading && orders.length === 0" class="mt-6 flex flex-col gap-4" aria-label="Загрузка заказов" aria-busy="true"><div v-for="index in 3" :key="index" class="h-44 animate-pulse rounded-xl bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" /></div>

    <div v-else-if="filteredOrders.length === 0" class="mt-6 rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-6 py-12 text-center">
      <ShoppingBagIcon class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#d1d5db)]" aria-hidden="true" />
      <h3 class="mt-4 text-lg font-medium text-[color:var(--storefront-title,#111827)]">{{ hasActiveFilters ? 'Нет заказов по выбранным фильтрам' : 'У вас пока нет покупок' }}</h3>
      <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ hasActiveFilters ? 'Измените фильтры, чтобы увидеть другие заказы.' : 'Выберите спецтехнику в каталоге.' }}</p>
      <div v-if="!hasActiveFilters" class="mt-5 flex flex-wrap justify-center gap-3">
        <NuxtLink :to="publicRoute('/special-equipment')" class="storefront-action-primary inline-flex min-h-11 items-center rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]">Каталог транспортных средств и специальной техники</NuxtLink>
      </div>
    </div>

    <div v-else class="mt-6 flex flex-col gap-4">
      <CommerceOrderCard v-for="order in filteredOrders" :key="`${order.item.type}:${order.id}`" :order="order" :has-companies="hasCompanies" @updated="replaceOrder" />
    </div>

    <div v-if="loadError" class="mt-4 rounded-lg border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-warning-text,#78350f)]" role="status">{{ loadError }} <button type="button" class="storefront-action-ghost ml-2 font-semibold underline" @click="loadOrders">Повторить</button></div>
  </section>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { ShoppingBagIcon } from '@heroicons/vue/24/outline'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { createCommerceApi } from '../api/commerceApi'
import { commerceFailureMessage } from '../composables/commerceErrors'
import type { CommerceItemType, CommerceOrder } from '../types'
import CommerceOrderCard from './CommerceOrderCard.vue'

withDefaults(defineProps<{ hasCompanies?: boolean }>(), { hasCompanies: false })

const api = createCommerceApi(useRuntimeConfig())
const { publicRoute } = useStorefront()
const visibilityStore = useSectionVisibilityStore()
const isSpecialEquipmentCatalogVisible = computed(() =>
  visibilityStore.isSectionVisible('public', 'special_equipment_catalog'),
)
const orders = ref<CommerceOrder[]>([])
const loading = ref(true)
const loadError = ref('')
const statusFilter = ref('')
const typeFilter = ref<CommerceItemType | ''>('')
const hasActiveFilters = computed(() => Boolean(statusFilter.value || typeFilter.value))

const visibleOrders = computed(() => orders.value.filter((order) => (
  isSpecialEquipmentCatalogVisible.value || order.item.type === 'vehicle'
)))
const filteredOrders = computed(() => visibleOrders.value.filter((order) => (
  (!statusFilter.value || order.status === statusFilter.value)
  && (!typeFilter.value || order.item.type === typeFilter.value)
)))

const orderTimestamp = (value: string | null): number => {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

const loadOrders = async (): Promise<void> => {
  loading.value = true
  loadError.value = ''
  const types: CommerceItemType[] = isSpecialEquipmentCatalogVisible.value
    ? ['vehicle', 'special_equipment']
    : ['vehicle']
  const responses = await Promise.allSettled(types.map((type) => api.getOrders(type)))
  const loaded: CommerceOrder[] = []
  const errors: string[] = []
  responses.forEach((response, index) => {
    if (response.status === 'fulfilled') loaded.push(...response.value.items)
    else errors.push(commerceFailureMessage(response.reason, `Не удалось загрузить ${types[index] === 'vehicle' ? 'автомобили' : 'спецтехнику'}.`))
  })
  orders.value = loaded.sort((left, right) => orderTimestamp(right.created_at) - orderTimestamp(left.created_at))
  loadError.value = errors.join(' ')
  loading.value = false
}

const replaceOrder = (updated: CommerceOrder): void => {
  orders.value = orders.value.map((order) => order.id === updated.id && order.item.type === updated.item.type ? updated : order)
}

onMounted(() => { void loadOrders() })
</script>
