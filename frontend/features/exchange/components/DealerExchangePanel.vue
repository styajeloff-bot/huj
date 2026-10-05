<template>
  <div class="space-y-6">
    <!-- Header -->
    <div>
      <h2 class="text-2xl font-bold text-gray-900">Биржа ТС</h2>
      <p class="text-sm text-gray-500 mt-1">Заявки от лизинговых компаний</p>
    </div>

    <!-- Status pills -->
    <div class="flex flex-wrap items-center gap-2 bg-gray-50 p-1.5 rounded-xl border border-gray-200 w-fit">
      <button
        v-for="tab in statusTabs"
        :key="tab.value"
        @click="changeStatus(tab.value)"
        :class="[
          'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all',
          statusFilter === tab.value
            ? 'bg-white text-blue-700 shadow-sm'
            : 'text-gray-600 hover:text-gray-900'
        ]"
      >
        <component :is="tab.icon" class="w-4 h-4" />
        {{ tab.label }}
        <span
          v-if="store.statusCounts[tab.value] > 0"
          :class="[
            'ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-semibold rounded-full',
            statusFilter === tab.value ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'
          ]"
        >
          {{ store.statusCounts[tab.value] }}
        </span>
      </button>
    </div>

    <!-- Detail view (priority over loading to avoid remount loop) -->
    <div v-if="selectedRequestId">
      <button
        @click="handleDetailClose"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-blue-600 mb-4 transition-colors"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        Назад к списку
      </button>
      <ExchangeRequestDetail
        :key="`${selectedRequestId}:${notificationCompanyId || ''}`"
        :request-id="selectedRequestId"
        :notification-company-id="notificationCompanyId"
        :is-lc="false"
        @close="handleDetailClose"
      />
    </div>

    <!-- Loading -->
    <div v-else-if="store.loading" class="flex justify-center py-16">
      <div class="animate-spin rounded-full h-10 w-10 border-2 border-gray-200 border-t-blue-600"></div>
    </div>

    <!-- Request list -->
    <div v-else-if="store.requests && store.requests.length > 0" class="space-y-3">
      <ExchangeRequestCard
        v-for="request in store.requests"
        :key="request.id"
        :request="request"
        :is-lc="false"
        @view="openDetail(request.id)"
      />

      <!-- Pagination -->
      <div v-if="store.pagination.pages > 1" class="flex justify-center mt-6 gap-1.5">
        <button
          v-for="page in store.pagination.pages"
          :key="page"
          @click="store.fetchDealerRequests(statusFilter, page, notificationCompanyId)"
          :class="[
            'min-w-[36px] h-9 px-3 rounded-lg text-sm font-medium transition-colors',
            page === store.pagination.page
              ? 'bg-blue-600 text-white'
              : 'bg-white border border-gray-200 text-gray-700 hover:border-blue-400 hover:text-blue-600'
          ]"
        >
          {{ page }}
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="text-center py-16 bg-white rounded-2xl border border-dashed border-gray-300">
      <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-50 text-blue-500 mb-4">
        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      </div>
      <h3 class="text-base font-semibold text-gray-900 mb-1">Нет доступных заявок</h3>
      <p class="text-sm text-gray-500 max-w-sm mx-auto">Заявки от лизинговых компаний, связанные с вашими складами, появятся здесь.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import ExchangeRequestCard from './ExchangeRequestCard.vue'
import ExchangeRequestDetail from './ExchangeRequestDetail.vue'
import { useExchangeRequestsStore } from '../store/exchangeRequests'
import type { ExchangeRequestId, ExchangeRequestStatus } from '../types'
import { isUuid } from '~/types/ids'

const store = useExchangeRequestsStore()
const route = useRoute()
const router = useRouter()
const notificationCompanyId = computed(() => isUuid(route.query.notification_company_id) ? route.query.notification_company_id : undefined)
const statusFilter = ref<ExchangeRequestStatus>('open')
const selectedRequestId = ref<ExchangeRequestId | null>(null)

const Icon = (path: string) => () => h('svg', { fill: 'none', stroke: 'currentColor', viewBox: '0 0 24 24' }, [
  h('path', { 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-width': '2', d: path })
])

const statusTabs = [
  { value: 'open' as const, label: 'Открытые', icon: Icon('M13 10V3L4 14h7v7l9-11h-7z') },
  { value: 'deal' as const, label: 'Сделки', icon: Icon('M5 13l4 4L19 7') },
]

function openDetail(id: ExchangeRequestId) {
  return router.push({ query: { ...route.query, request: id } })
}

function changeStatus(status: ExchangeRequestStatus) {
  statusFilter.value = status
  void handleDetailClose()
}

async function handleDetailClose() {
  selectedRequestId.value = null
  if (route.query.request) {
    const query = { ...route.query }
    delete query.request
    delete query.notification_company_id
    await router.replace({ query })
  }
  store.fetchDealerRequests(statusFilter.value)
}

watch(() => route.query.request, requestId => {
  selectedRequestId.value = isUuid(requestId) ? requestId : null
}, { immediate: true })

watch(notificationCompanyId, company => { void store.fetchDealerRequests(statusFilter.value, 1, company) }, { immediate: true })
</script>
