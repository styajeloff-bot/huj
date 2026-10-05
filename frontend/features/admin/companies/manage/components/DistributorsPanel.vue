<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Управление дистрибьюторами
      </h2>
      <label class="btn-secondary text-sm cursor-pointer">
        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4 4m4-4v12"></path>
        </svg>
        Загрузить связи (CSV)
        <input type="file" accept=".csv" class="hidden" @change="importLinksCsv">
      </label>
    </div>

    <ImportProgress
      :uploading="csvImport.uploading.value"
      :finished="csvImport.finished.value"
      :status="csvImport.status.value"
      :filename="csvImport.filename.value"
      :progress="csvImport.progress.value"
      :rows-total="csvImport.rowsTotal.value"
      :rows-done="csvImport.rowsDone.value"
      :errors-count="csvImport.errorsCount.value"
      :error-sample="csvImport.errorSample.value"
      :error-message="csvImport.errorMessage.value"
    />

    <DataTable
      :data="distributors"
      :columns="columns"
      :loading="loading"
      :actions="actions"
      :server-side="true"
      :total-items="pagination.total"
      :current-server-page="pagination.page"
      :total-server-pages="pagination.pages"
      :page-size="pagination.limit"
      :searchable="true"
      :show-header="false"
      empty-message="Дистрибьюторы не найдены"
      @action="handleAction"
      @refresh="fetchDistributors"
      @page-change="changePage"
      @search="handleSearch"
    >
      <template #column-name="{ item }">
        <div>
          <div class="text-sm font-medium text-gray-900">{{ item.name }}</div>
          <div v-if="item.inn" class="text-sm text-gray-500">ИНН: {{ item.inn }}</div>
        </div>
      </template>

      <template #column-company_type="{ item }">
        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-orange-100 text-orange-800">
          Дистрибьютор
        </span>
      </template>

      <template #column-contacts="{ item }">
        <div class="text-sm text-gray-900">
          <div v-if="item.phone">{{ item.phone }}</div>
          <div v-if="item.email" class="text-gray-500">{{ item.email }}</div>
        </div>
      </template>

      <template #column-is_active="{ item }">
        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
              :class="item.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'">
          {{ item.is_active ? 'Активна' : 'Неактивна' }}
        </span>
      </template>

      <template #column-can_manage_dealer_groups="{ item }">
        <label class="inline-flex items-center gap-2 text-sm text-gray-700" @click.stop>
          <input
            type="checkbox"
            class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            :checked="Boolean(item.can_manage_dealer_groups)"
            :disabled="isPermissionSaving(item.id)"
            @change="toggleDealerGroupPermission(tableCompany(item), ($event.target as HTMLInputElement).checked)"
          />
          <span>{{ item.can_manage_dealer_groups ? 'Разрешено' : 'Запрещено' }}</span>
        </label>
      </template>
    </DataTable>

    <DistributorDealersManager
      v-if="showManager && selectedDistributor"
      :distributor="selectedDistributor"
      @close="showManager = false"
      @updated="fetchDistributors"
    />
  </div>
</template>

<script setup lang="ts">
import { EyeIcon } from '@heroicons/vue/24/outline'
import { createCompaniesAdminApi } from '../api/companiesAdminApi'
import DistributorDealersManager from './DistributorDealersManager.vue'
import ImportProgress from '~/features/admin/shared/components/ImportProgress.vue'
import { useCsvImport } from '~/features/admin/shared/composables/useCsvImport'
import type { Company, Pagination } from '~/types/features'
import type { UUID } from '~/types/ids'

const config = useRuntimeConfig()
const api = createCompaniesAdminApi(config)
const csvImport = useCsvImport()
const toast = useToast()

const importLinksCsv = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await csvImport.upload('/api/v1/admin/companies/distributor-dealer-links/import', file)
  input.value = ''
  fetchDistributors()
}

const distributors = ref<Company[]>([])
const loading = ref(true)
const showManager = ref(false)
const selectedDistributor = ref<Company | null>(null)
const permissionSavingIds = ref<Set<UUID>>(new Set())

const currentSearch = ref('')

const pagination = ref<Pagination>({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

const columns = [
  { key: 'name', label: 'Компания' },
  { key: 'company_type', label: 'Тип' },
  { key: 'contacts', label: 'Контакты' },
  { key: 'can_manage_dealer_groups', label: 'Группы дилеров' },
  { key: 'is_active', label: 'Статус' }
]

const actions = [
  { key: 'view', label: 'Связанные дилеры', icon: EyeIcon, className: 'text-blue-600 hover:text-blue-900' }
]

const fetchDistributors = async () => {
  loading.value = true
  try {
    const params: Record<string, string> = {
      page: pagination.value.page.toString(),
      limit: pagination.value.limit.toString(),
      company_type: 'distributor'
    }
    if (currentSearch.value) params.search = currentSearch.value

    const [response, permissionsResponse] = await Promise.all([
      api.getCompanies(params),
      api.getAdminDistributors()
    ])
    const permissions = new Map(
      (permissionsResponse.distributors || []).map((distributor) => [
        distributor.id,
        Boolean(distributor.can_manage_dealer_groups)
      ])
    )
    distributors.value = response.companies.map((distributor) => ({
      ...distributor,
      can_manage_dealer_groups: permissions.get(distributor.id) || false
    }))
    pagination.value = response.pagination
  } catch (err) {
    console.error('Error fetching distributors:', err)
  } finally {
    loading.value = false
  }
}

const changePage = (page: number) => {
  pagination.value.page = page
  fetchDistributors()
}

const handleSearch = (query: string) => {
  currentSearch.value = query
  pagination.value.page = 1
  fetchDistributors()
}

const handleAction = ({ action, item }: { action: string; item: Company }) => {
  if (action === 'view') {
    selectedDistributor.value = item
    showManager.value = true
  }
}

const isPermissionSaving = (id: unknown) => typeof id === 'string' && permissionSavingIds.value.has(id)

const tableCompany = (item: Record<string, unknown>): Company => item as unknown as Company

const setPermissionSaving = (id: UUID, saving: boolean) => {
  const next = new Set(permissionSavingIds.value)
  if (saving) {
    next.add(id)
  } else {
    next.delete(id)
  }
  permissionSavingIds.value = next
}

const updateDistributorPermission = (id: UUID, canManage: boolean) => {
  distributors.value = distributors.value.map((distributor) =>
    distributor.id === id
      ? { ...distributor, can_manage_dealer_groups: canManage }
      : distributor
  )
  if (selectedDistributor.value?.id === id) {
    selectedDistributor.value = {
      ...selectedDistributor.value,
      can_manage_dealer_groups: canManage
    }
  }
}

const toggleDealerGroupPermission = async (distributor: Company, canManage: boolean) => {
  const id = distributor.id
  const previous = Boolean(distributor.can_manage_dealer_groups)
  setPermissionSaving(id, true)
  try {
    await api.updateCompany(id, { can_manage_dealer_groups: canManage })
    updateDistributorPermission(id, canManage)
    toast.success('Право управления группами дилеров обновлено')
  } catch (err) {
    updateDistributorPermission(id, previous)
    toast.error('Не удалось обновить право управления группами дилеров')
    console.error('Error updating distributor dealer group permission:', err)
  } finally {
    setPermissionSaving(id, false)
  }
}

onMounted(() => {
  fetchDistributors()
})
</script>
