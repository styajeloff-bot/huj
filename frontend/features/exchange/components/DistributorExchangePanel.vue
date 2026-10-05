<template>
  <section class="space-y-6">
    <header>
      <h1 class="text-2xl font-semibold text-gray-900">Биржа ТС</h1>
      <p class="mt-1 text-sm text-gray-600">Заявки связанных дилеров. Только просмотр.</p>
    </header>

    <div v-if="selectedRequestId">
      <button type="button" class="btn-secondary mb-4" @click="closeDetail">Назад к списку</button>
      <ExchangeRequestDetail :key="`${selectedRequestId}:${notificationCompanyId || ''}`" :request-id="selectedRequestId" :notification-company-id="notificationCompanyId" :is-lc="false" :is-distributor="true" @close="closeDetail" />
    </div>
    <template v-else>
      <div class="flex flex-wrap gap-2" aria-label="Статус заявки">
        <button v-for="tab in statusTabs" :key="tab.value" type="button"
          class="rounded-lg border px-4 py-2 text-sm font-medium focus-visible:ring-2 focus-visible:ring-blue-500"
          :class="statusFilter === tab.value ? 'border-blue-600 bg-blue-600 text-white' : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'"
          :aria-pressed="statusFilter === tab.value" @click="changeStatus(tab.value)">
          {{ tab.label }} ({{ counts[tab.value] }})
        </button>
      </div>
      <p v-if="loading" class="py-12 text-center text-gray-600" role="status">Загружаем заявки…</p>
      <div v-else-if="error" class="rounded-lg border border-red-200 bg-red-50 p-4" role="alert">
        <p class="text-sm text-red-700">{{ error }}</p>
        <button type="button" class="btn-secondary mt-3" @click="loadRequests(pagination.page)">Повторить</button>
      </div>
      <div v-else-if="requests.length" class="space-y-3">
        <ExchangeRequestCard v-for="request in requests" :key="request.id" :request="request" :is-lc="true" @view="openDetail(request.id)" />
        <nav v-if="pagination.pages > 1" class="flex items-center justify-center gap-4 pt-4" aria-label="Страницы заявок">
          <button type="button" class="btn-secondary" :disabled="pagination.page <= 1" @click="loadRequests(pagination.page - 1)">Назад</button>
          <span class="text-sm text-gray-600">{{ pagination.page }} / {{ pagination.pages }}</span>
          <button type="button" class="btn-secondary" :disabled="pagination.page >= pagination.pages" @click="loadRequests(pagination.page + 1)">Далее</button>
        </nav>
      </div>
      <p v-else class="rounded-lg border border-gray-200 bg-white p-12 text-center text-gray-600">В этом разделе нет доступных заявок связанных дилеров.</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { createExchangeApi } from '../api/exchangeApi'
import ExchangeRequestCard from './ExchangeRequestCard.vue'
import ExchangeRequestDetail from './ExchangeRequestDetail.vue'
import type { ExchangeRequest, ExchangeRequestId, ExchangeRequestStatus } from '../types'
import { isUuid } from '~/types/ids'

const route = useRoute()
const router = useRouter()
const notificationCompanyId = computed(() => isUuid(route.query.notification_company_id) ? route.query.notification_company_id : undefined)
const api = createExchangeApi(useRuntimeConfig(), () => notificationCompanyId.value)
const selectedRequestId = computed(() => isUuid(route.query.request) ? route.query.request : null)
const requests = ref<ExchangeRequest[]>([])
const counts = ref<Record<ExchangeRequestStatus, number>>({ open: 0, deal: 0, archived: 0 })
const statusFilter = ref<ExchangeRequestStatus>('open')
const pagination = ref({ page: 1, limit: 20, pages: 0, total: 0 })
const loading = ref(false)
const error = ref('')
const statusTabs = [
  { value: 'open', label: 'Открытые' }, { value: 'deal', label: 'Сделки' }, { value: 'archived', label: 'Архив' },
] as const
let requestVersion = 0

async function loadRequests(page = 1) {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const [list, totals] = await Promise.all([
      api.getDistributorRequests({ status: statusFilter.value, page, limit: 20 }),
      api.getDistributorStatusCounts(),
    ])
    if (version !== requestVersion) return
    requests.value = list.requests
    pagination.value = list.pagination
    counts.value = totals.counts
  } catch {
    if (version === requestVersion) error.value = 'Не удалось загрузить заявки. Проверьте доступ и повторите попытку.'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}

function changeStatus(value: ExchangeRequestStatus) { statusFilter.value = value; void loadRequests() }
function openDetail(id: ExchangeRequestId) { return router.push({ query: { ...route.query, request: id } }) }
async function closeDetail() {
  const query = { ...route.query }
  delete query.request
  delete query.notification_company_id
  await router.replace({ query })
}
watch([selectedRequestId, notificationCompanyId], () => { if (!selectedRequestId.value) void loadRequests() })
onMounted(() => { if (!selectedRequestId.value) void loadRequests() })
</script>
