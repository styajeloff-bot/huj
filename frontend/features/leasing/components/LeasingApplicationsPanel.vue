<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Заявки на лизинг
      </h2>
      <div class="text-sm text-gray-600">
        Заявки, поданные в вашу лизинговую компанию
      </div>
    </div>

    <!-- Фильтры -->
    <div class="bg-white p-4 rounded-lg border border-gray-200 mb-6">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Статус</label>
          <select v-model="filters.status" class="select-field" :disabled="filters.kind === 'fast_deal'" @change="applyFilters">
            <option value="">Все статусы</option>
            <option value="submitted">Подана</option>
            <option value="under_review">На рассмотрении</option>
            <option value="under_review_with_docs">На рассмотрении с доп. документами</option>
            <option value="approved_scoring">Одобрено на скоринге</option>
            <option value="approved_scoring_another_cond">Одобрено на других условиях</option>
            <option value="rejected_prescoring">Отказано на скоринге</option>
            <option value="documents_required">Требуются доп доки</option>
            <option value="approved_final">Одобрение итоговое</option>
            <option value="approved_final_another_cond">Одобрение итоговое на других условиях</option>
            <option value="rejected_approved">Отказано после рассмотрения</option>
            <option value="selected_lc">Выбрана ЛК</option>
            <option value="deal">Профинансировано</option>
            <option value="closed">Закрыта клиентом</option>
          </select>
          <p v-if="statusFilterHint" class="mt-1 text-xs text-gray-500" data-testid="application-status-hint">{{ statusFilterHint }}</p>
        </div>
        <div>
          <label for="leasing-application-search" class="mb-1 block text-sm font-medium text-gray-700">Поиск</label>
          <input id="leasing-application-search" v-model="filters.search" class="input-field" type="search" placeholder="Номер заявки с префиксом или без" @input="debouncedSearch" @keydown.enter.prevent="applyFilters">
        </div>
      </div>
      <ApplicationKindFilter v-model="filters.kind" class="mt-4 max-w-xs" @update:model-value="applyFilters" />
      <ApplicationSourceFilter v-model="filters.sources" class="mt-4" @update:model-value="applyFilters" />
    </div>

    <!-- Список заявок -->
    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      <p class="mt-2 text-gray-600">Загружаем заявки...</p>
    </div>

    <div v-else-if="error" class="text-center py-8">
      <p class="text-red-600 mb-4">{{ error }}</p>
      <button class="btn-primary" @click="fetchApplications">
        Попробовать снова
      </button>
    </div>

    <div v-else-if="applications.length === 0" class="text-center py-12">
      <h3 class="text-lg font-medium text-gray-900 mb-2">
        {{ filters.kind === 'fast_deal' ? 'Быстрые регистрации не найдены' : 'Заявки не найдены' }}
      </h3>
      <p class="text-gray-600">
        {{ filters.kind === 'fast_deal' ? 'Сделки быстрой регистрации вашей лизинговой компании появятся здесь' : 'Пока нет заявок для вашей лизинговой компании' }}
      </p>
    </div>

    <div v-else class="space-y-4">
      <template v-for="application in applications" :key="application.id">
      <FastDealApplicationRow v-if="isFastDealRow(application)" :deal="application" />
      <div
        v-else
        class="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow"
      >
        <div class="flex items-start justify-between mb-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">
              Заявка {{ formatApplicationNumber(application) }}
            </h3>
            <ApplicationSourceBadge :source="application.source_type" class="mt-1" />
            <p class="text-sm text-gray-600 mt-1">
              {{ applicationDisplayDate(application) }}
            </p>
          </div>
          <span
            class="inline-flex px-3 py-1 text-xs font-semibold rounded-full"
            :class="getStatusColor(application.status)"
          >
            {{ getStatusLabel(application.status) }}
          </span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
          <div>
            <h4 class="text-sm font-medium text-gray-900 mb-2">
              Заявитель
            </h4>
            <div class="space-y-1 text-sm text-gray-600">
              <div v-if="application.company_name">
                <strong>Компания:</strong> {{ application.company_name }}
              </div>
              <div v-if="application.company_inn">
                <strong>ИНН:</strong> {{ application.company_inn }}
              </div>
              <div v-if="application.name">
                <strong>Контакт:</strong> {{ application.name }}
              </div>
              <div v-if="application.email">
                <strong>Email:</strong> {{ application.email }}
              </div>
            </div>
          </div>

          <div>
            <h4 class="text-sm font-medium text-gray-900 mb-2">
              Запрошенные параметры
            </h4>
            <div class="space-y-1 text-sm text-gray-600">
              <div v-if="application.total_amount">
                <strong>Сумма:</strong> {{ formatMoney(application.total_amount) }}
              </div>
              <div v-if="application.monthly_payment">
                <strong>Ежемесячный платёж:</strong> {{ formatMoney(application.monthly_payment) }}
              </div>
              <div v-if="application.down_payment_percent">
                <strong>Аванс:</strong> {{ application.down_payment_percent }}%
              </div>
              <div v-if="application.lease_term_months">
                <strong>Срок:</strong> {{ application.lease_term_months }} мес.
              </div>
            </div>
          </div>
        </div>

        <div class="flex justify-between items-center gap-2 pt-4 border-t border-gray-200 flex-wrap">
          <div class="text-xs text-gray-600 inline-flex items-center gap-1.5">
            <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <span>
              Прикреплённые документы:
              <strong class="text-gray-900">{{ application.attached_documents_count ?? 0 }}</strong>
            </span>
          </div>
          <div class="flex items-center gap-2">
            <NuxtLink
              :to="`/workspace/leasing-applications/${application.id}`"
              class="btn-primary text-sm"
            >
              Открыть заявку
            </NuxtLink>
          </div>
        </div>
      </div>
      </template>
    </div>

    <!-- Пагинация -->
    <div v-if="pagination.pages > 1" class="mt-6 flex justify-center">
      <div class="flex space-x-2">
        <button
          :disabled="pagination.page <= 1"
          class="btn-secondary disabled:opacity-50"
          @click="changePage(pagination.page - 1)"
        >
          Предыдущая
        </button>
        <span class="flex items-center px-3 py-2 text-sm text-gray-700">
          Страница {{ pagination.page }} из {{ pagination.pages }}
        </span>
        <button
          :disabled="pagination.page >= pagination.pages"
          class="btn-secondary disabled:opacity-50"
          @click="changePage(pagination.page + 1)"
        >
          Следующая
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import type { LeasingApplicationDisplay, PaginationInfo, LeasingAppStatus } from '~/features/leasing/types'
import { formatSourcedApplicationNumber as formatApplicationNumber, type SiteApplicationSourceType } from '~/features/applications/sourceType'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import ApplicationSourceFilter from '~/features/applications/components/ApplicationSourceFilter.vue'
import ApplicationKindFilter from '~/features/fast-deals/components/ApplicationKindFilter.vue'
import FastDealApplicationRow from '~/features/fast-deals/components/FastDealApplicationRow.vue'
import { asFastDealRow, isFastDealRow, kindQueryValue, type ApplicationListKind } from '~/features/fast-deals/mergedList'
import type { FastDealListItem } from '~/features/fast-deals/types'

/** The list holds applications of the LC and fast deals (`kind: 'fast_deal'`) in one order. */
type LeasingListRow = LeasingApplicationDisplay | FastDealListItem

interface LeasingLcApplicationEntry {
  link?: {
    id?: string
    leasing_company_id?: string
    status?: string | null
    submitted_at?: string | null
    updated_at?: string | null
  } | null
  application?: Partial<LeasingApplicationDisplay> | null
}

interface ApplicationsResponse {
  applications: LeasingLcApplicationEntry[]
  pagination: PaginationInfo
}

const config = useRuntimeConfig()
const authStore = useAuthStore()

const applications = ref<LeasingListRow[]>([])
const loading = ref(true)
const error = ref('')
const myLeasingCompanyName = ref<string>('')

const filters = ref({
  status: '',
  search: '',
  sources: [] as SiteApplicationSourceType[],
  kind: '' as ApplicationListKind | '',
})

// An ordinary status excludes fast deals on the server; while only fast deals are listed the
// ordinary status filter is not sent at all.
const statusFilterHint = computed(() => {
  if (filters.value.kind === 'fast_deal') return 'Статус быстрой регистрации выбирается в разделе «Регистрация сделки».'
  if (filters.value.status && filters.value.kind === '') return 'При выборе статуса показываются только заявки, быстрые регистрации скрыты.'
  return ''
})

const pagination = ref<PaginationInfo>({
  page: 1,
  limit: 10,
  total: 0,
  pages: 0,
})

const fetchApplications = async () => {
  loading.value = true
  error.value = ''

  try {
    const params = new URLSearchParams({
      page: pagination.value.page.toString(),
      limit: pagination.value.limit.toString(),
    })
    if (filters.value.status && filters.value.kind !== 'fast_deal') params.append('status', filters.value.status)
    if (filters.value.search.trim()) params.append('search', filters.value.search.trim())
    if (filters.value.sources.length) params.append('source_type', filters.value.sources.join(','))
    const kind = kindQueryValue(filters.value.kind)
    if (kind) params.append('kind', kind)

    const response = await $fetch<ApplicationsResponse>(
      `/api/v1/leasing/applications?${params.toString()}`,
      { baseURL: config.public.apiBase, credentials: 'include' },
    )

    applications.value = (response.applications || [])
      .map((entry): LeasingListRow | null => {
        const deal = asFastDealRow(entry)
        if (deal) return deal
        const app = entry?.application
        if (!app || typeof app.id !== 'string' || !app.id) return null
        const parentStatus = (app.status as string | undefined) || ''
        // Show "Submitted" until LC takes the app in work — at that point the
        // parent application transitions to under_review (Phase 1.4). Once
        // LC issues a КП the LCA status (prescoring/approved/rejected) takes
        // precedence, since it carries the per-LC decision state.
        const lcaStatus = (entry.link?.status as string | undefined) || ''
        const displayStatus =
          parentStatus === 'submitted'
            ? 'submitted'
            : lcaStatus || parentStatus
        return {
          ...app,
          id: app.id,
          status: displayStatus,
          parent_status: parentStatus,
          created_at: String(app.created_at ?? ''),
          submitted_at: String(entry.link?.submitted_at || app.submitted_at || ''),
          updated_at: String(entry.link?.updated_at || app.updated_at || ''),
          lca_id: entry.link?.id,
          attached_documents_count:
            (app as { attached_documents_count?: number }).attached_documents_count ?? 0,
        } as LeasingApplicationDisplay
      })
      .filter((a): a is LeasingListRow => a !== null)
      .sort(compareApplications)
    pagination.value = response.pagination
  } catch (err: unknown) {
    const logger = useLogger()
    logger.error('LeasingApplicationsPanel: Error fetching applications', err)
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке заявок'
  } finally {
    loading.value = false
  }
}

const applyFilters = () => {
  pagination.value.page = 1
  fetchApplications()
}
const { debounce } = useLodash()
const debouncedSearch = debounce(applyFilters, 300)
onBeforeUnmount(() => debouncedSearch.cancel())

const changePage = (page: number) => {
  pagination.value.page = page
  fetchApplications()
}

const applicationTimestamp = (application: LeasingListRow): number => {
  const value = String(
    isFastDealRow(application)
      ? application.updated_at || application.created_at || ''
      : application.updated_at || application.submitted_at || application.created_at || '',
  )
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const compareApplications = (a: LeasingListRow, b: LeasingListRow): number => (
  applicationTimestamp(b) - applicationTimestamp(a)
)

const applicationDisplayDate = (application: LeasingApplicationDisplay): string => (
  formatDate(String(application.updated_at || application.submitted_at || application.created_at || ''))
)

const getStatusLabel = (status: LeasingAppStatus | string): string => {
  const labels: Record<string, string> = {
    submitted: 'Подана',
    under_review: 'На рассмотрении',
    under_review_with_docs: 'На рассмотрении с доп. документами',
    approved_scoring: 'Одобрено на скоринге',
    approved_scoring_another_cond: 'Одобрено на других условиях',
    rejected_prescoring: 'Отказано на скоринге',
    documents_required: 'Требуются доп доки',
    approved_final: 'Одобрение итоговое',
    approved_final_another_cond: 'Одобрение итоговое на других условиях',
    rejected_approved: 'Отказано после рассмотрения',
    selected_lc: 'Выбрана ЛК',
    deal: 'Профинансировано',
    closed: 'Закрыта клиентом',
  }
  return labels[status] || status
}

const getStatusColor = (status: LeasingAppStatus | string): string => {
  const colors: Record<string, string> = {
    submitted: 'bg-blue-100 text-blue-800',
    under_review: 'bg-yellow-100 text-yellow-800',
    under_review_with_docs: 'bg-amber-100 text-amber-800',
    approved_scoring: 'bg-green-100 text-green-800',
    approved_scoring_another_cond: 'bg-emerald-100 text-emerald-800',
    rejected_prescoring: 'bg-red-100 text-red-800',
    documents_required: 'bg-orange-100 text-orange-800',
    approved_final: 'bg-green-100 text-green-800',
    approved_final_another_cond: 'bg-emerald-100 text-emerald-800',
    rejected_approved: 'bg-red-100 text-red-800',
    selected_lc: 'bg-purple-100 text-purple-800',
    deal: 'bg-teal-100 text-teal-800',
    closed: 'bg-gray-100 text-gray-800',
  }
  return colors[status] || 'bg-gray-100 text-gray-800'
}

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDateTime } = useFormatDate()

const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return ''
  const d = new Date(dateString)
  if (Number.isNaN(d.getTime())) return ''
  return formatDateTime(d)
}

const formatMoney = (amount: number): string => {
  if (!amount) return '0 ₽'
  return formatSharedPrice(amount)
}

const fetchMyLeasingCompany = async () => {
  try {
    const me = authStore.user as Record<string, unknown> | null
    const response = await $fetch<{ companies: Array<Record<string, unknown>> }>(
      '/api/v1/leasing/companies',
      { baseURL: config.public.apiBase, credentials: 'include' },
    )
    const myCompanyId = me?.company_id
    const found = (response.companies || []).find(
      (c) => c.company_id === myCompanyId,
    )
    myLeasingCompanyName.value = found ? String(found.name || '') : ''
  } catch {
    myLeasingCompanyName.value = ''
  }
}

onMounted(() => {
  fetchApplications()
  fetchMyLeasingCompany()
  const updateInterval = setInterval(fetchApplications, 30000)
  onUnmounted(() => clearInterval(updateInterval))
})
</script>
