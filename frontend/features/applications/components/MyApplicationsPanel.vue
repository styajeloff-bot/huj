<template>
  <section data-storefront-block="client.application">
    <div class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 class="text-2xl font-semibold text-[color:var(--storefront-title,#111827)]">Мои заявки</h1>
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Заявки, созданные вами или связанные с вашей дилерской компанией.
        </p>
      </div>
      <NuxtLink
        v-if="authStore.canCreateApplications"
        :to="publicRoute('/special-equipment')"
        class="btn-primary text-sm"
      >
        Создать заявку
      </NuxtLink>
    </div>

    <div
      v-if="!authStore.canViewApplications"
      class="mb-6 rounded-lg border border-[color:var(--storefront-warning-border,#fef08a)] bg-[color:rgb(var(--storefront-warning-rgb,254_252_232)/var(--tw-bg-opacity,1))] p-4 text-sm text-[color:var(--storefront-warning-text,#854d0e)]"
    >
      Доступ к заявкам ограничен. Обратитесь к администратору компании.
    </div>

    <div
      v-if="authStore.canViewApplications"
      class="mb-6 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4"
    >
      <label class="mb-1 block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Статус</label>
      <select
        v-model="filters.status"
        class="storefront-control select-field max-w-xs"
        :disabled="filters.kind === 'fast_deal'"
        @change="applyStatusFilter"
      >
        <option value="">Все статусы</option>
        <option value="active">Активная</option>
        <option value="rejected">Отклонена</option>
        <option value="issued">Выдана</option>
      </select>
      <p v-if="statusFilterHint" class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]" data-testid="application-status-hint">
        {{ statusFilterHint }}
      </p>
      <ApplicationKindFilter v-model="filters.kind" class="mt-4 max-w-xs" @update:model-value="applyStatusFilter" />
      <div class="mt-4">
        <label for="application-search" class="mb-1 block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Поиск</label>
        <input id="application-search" v-model="filters.search" type="search" class="storefront-control input-field max-w-lg" placeholder="Номер заявки с префиксом или без" @input="debouncedSearch" @keydown.enter.prevent="applyStatusFilter">
      </div>
      <ApplicationSourceFilter v-if="canViewApplicationSource(authStore.userRole)" v-model="filters.sources" class="mt-4" @update:model-value="applyStatusFilter" />
    </div>

    <div v-if="loading" class="py-12 text-center">
      <div class="inline-block h-8 w-8 animate-spin rounded-full border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
      <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем заявки...</p>
    </div>

    <div v-else-if="error" class="rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-6 text-center">
      <p class="mb-4 text-[color:var(--storefront-error-text,#b91c1c)]">{{ error }}</p>
      <button class="btn-primary" @click="fetchApplications">Попробовать снова</button>
    </div>

    <div
      v-else-if="authStore.canViewApplications && applications.length === 0"
      class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] py-12 text-center"
    >
      <svg class="mx-auto mb-4 h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      <h2 class="mb-2 text-lg font-medium text-[color:var(--storefront-title,#111827)]">{{ emptyTitle }}</h2>
      <p class="text-[color:var(--storefront-text-muted,#4b5563)]">{{ emptyHint }}</p>
    </div>

    <div v-else class="space-y-6">
      <template v-for="row in applications" :key="row.id">
        <FastDealApplicationRow v-if="isFastDealRow(row)" :deal="row" />
        <ApplicationCard
          v-else
          :application="row"
          action-mode="details"
          @open-details="openApplicationDetails"
          @updated="fetchApplications"
        />
      </template>
    </div>

    <div
      v-if="!loading && !error && pagination && pagination.pages > 1"
      class="mt-6 flex items-center justify-center gap-2"
      data-testid="applications-pagination"
    >
      <button type="button" class="btn-secondary text-sm disabled:opacity-50" :disabled="page <= 1" @click="changePage(page - 1)">
        Назад
      </button>
      <span class="px-3 text-sm text-[color:var(--storefront-text,#374151)]">Страница {{ page }} из {{ pagination.pages }}</span>
      <button type="button" class="btn-secondary text-sm disabled:opacity-50" :disabled="page >= pagination.pages" @click="changePage(page + 1)">
        Вперёд
      </button>
    </div>

    <ApplicationDetailModal
      v-if="selectedApplicationId && (authStore.canViewApplications || notificationCompanyId)"
      :key="`${selectedApplicationId}:${notificationCompanyId || ''}`"
      :application-id="selectedApplicationId"
      :notification-company-id="notificationCompanyId"
      @close="closeApplicationDetails"
      @updated="fetchApplications"
    />
  </section>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import ApplicationCard from '~/features/applications/components/ApplicationCard.vue'
import ApplicationSourceFilter from '~/features/applications/components/ApplicationSourceFilter.vue'
import { canViewApplicationSource, type SiteApplicationSourceType } from '~/features/applications/sourceType'
import ApplicationDetailModal from '~/features/applications/components/ApplicationDetailModal.vue'
import ApplicationKindFilter from '~/features/fast-deals/components/ApplicationKindFilter.vue'
import FastDealApplicationRow from '~/features/fast-deals/components/FastDealApplicationRow.vue'
import { isFastDealRow, kindQueryValue, type ApplicationListKind } from '~/features/fast-deals/mergedList'
import {
  createApplicationsApi,
  parseApplicationsApiError,
  type Application,
  type EntityId,
  type MergedApplicationRow,
  type Pagination,
} from '~/features/applications/api/applicationsApi'
import { useAuthStore } from '~/features/auth/store/auth'
import { isUuid } from '~/types/ids'
import type { ApiError } from '@/types'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const notificationCompanyId = computed(() => isUuid(route.query.notification_company_id) ? route.query.notification_company_id : undefined)
const { publicRoute } = useStorefront()
const config = useRuntimeConfig()
const applicationsApi = createApplicationsApi(config)

const applications = ref<MergedApplicationRow[]>([])
const loading = ref(true)
const error = ref('')
const page = ref(1)
const limit = ref(50)
const pagination = ref<Pagination | null>(null)
const selectedApplicationId = ref<EntityId | null>(null)
const filters = reactive({
  status: '',
  search: '',
  sources: [] as SiteApplicationSourceType[],
  kind: '' as ApplicationListKind | '',
})

// Statuses of ordinary applications do not exist for fast deals: the server leaves them out when
// such a status is chosen, and the status filter is not sent at all when only fast deals are shown.
const statusFilterHint = computed(() => {
  if (filters.kind === 'fast_deal') return 'Статус быстрой регистрации выбирается в разделе «Регистрация сделки».'
  if (filters.status && filters.kind === '') return 'При выборе статуса показываются только обычные заявки, быстрые регистрации скрыты.'
  return ''
})
const emptyTitle = computed(() => filters.kind === 'fast_deal' ? 'Быстрых регистраций нет' : 'Заявок пока нет')
const emptyHint = computed(() => filters.kind === 'fast_deal'
  ? 'Сделки быстрой регистрации появятся здесь, когда вы или ваша компания их создадите.'
  : 'Создайте первую заявку на автомобиль.')

const fetchApplications = async () => {
  if (!authStore.canViewApplications) {
    applications.value = []
    pagination.value = null
    loading.value = false
    return
  }

  loading.value = true
  error.value = ''
  try {
    const response = await applicationsApi.listApplicationsMerged(
      page.value,
      limit.value,
      filters.kind === 'fast_deal' ? '' : filters.status,
      {
        search: filters.search,
        source_type: canViewApplicationSource(authStore.userRole) ? filters.sources : undefined,
        kind: kindQueryValue(filters.kind),
      },
    )
    applications.value = response.applications || []
    pagination.value = response.pagination || null
  } catch (err) {
    const apiErr = err as ApiError
    if (apiErr.status === 401) {
      await authStore.checkAuth()
    } else {
      error.value = parseApplicationsApiError(
        err,
        'Ошибка при загрузке заявок',
      ).message
    }
  } finally {
    loading.value = false
  }
}

const applyStatusFilter = () => {
  page.value = 1
  fetchApplications()
}

const changePage = (next: number) => {
  page.value = next
  fetchApplications()
}

const { debounce } = useLodash()
const debouncedSearch = debounce(applyStatusFilter, 300)
onBeforeUnmount(() => debouncedSearch.cancel())

const openApplicationDetails = (application: Application) => {
  selectedApplicationId.value = application.id
}

const closeApplicationDetails = async () => {
  selectedApplicationId.value = null
  const query = { ...route.query }
  delete query.application
  delete query.notification_company_id
  await router.replace({ query })
}

watch(() => route.query.application, value => {
  selectedApplicationId.value = isUuid(value) ? value : null
}, { immediate: true })

onMounted(() => {
  fetchApplications()
})
</script>
