<template>
  <div>
    <div class="mb-6 space-y-3">
      <h2 class="text-xl font-semibold text-gray-900">
        Подрядчики
      </h2>

      <form class="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between" @submit.prevent="applyFilters">
        <div class="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <input
            v-model.trim="currentFilters.contractor_name"
            type="text"
            class="input-field min-w-[220px] flex-1 text-sm xl:max-w-[320px]"
            placeholder="Название подрядчика"
            aria-label="Фильтр по названию подрядчика"
          >
          <input
            v-model="currentFilters.inn"
            type="text"
            inputmode="numeric"
            maxlength="12"
            class="input-field min-w-[180px] flex-1 text-sm xl:max-w-[220px]"
            placeholder="ИНН подрядчика"
            aria-label="Фильтр по ИНН подрядчика"
            @input="normalizeFilterInn"
          >
          <button type="submit" class="btn-secondary text-sm">
            Применить
          </button>
          <button
            v-if="hasActiveFilters"
            type="button"
            class="btn-outline text-sm"
            @click="resetFilters"
          >
            Сбросить
          </button>
        </div>

        <div class="flex shrink-0 flex-wrap items-center gap-2">
          <label
            class="btn-secondary inline-flex cursor-pointer items-center gap-2 text-sm"
            :class="{ 'pointer-events-none opacity-60': importing }"
          >
            <ArrowUpTrayIcon class="w-4 h-4" />
            {{ importing ? 'Загрузка...' : 'Загрузить Excel' }}
            <input
              type="file"
              accept=".xlsx,.xls"
              class="hidden"
              :disabled="importing"
              @change="importExcel"
            >
          </label>
          <button type="button" class="btn-primary inline-flex items-center gap-2" @click="openCreateModal">
            <PlusIcon class="w-4 h-4" />
            Добавить
          </button>
        </div>
      </form>
    </div>

    <div
      v-if="importResult"
      class="mb-4 rounded-lg border p-4 text-sm"
      :class="importResult.errors.length ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-green-200 bg-green-50 text-green-900'"
    >
      <div class="font-medium">
        Импорт Excel: обработано строк {{ importResult.rows_total }}
      </div>
      <div class="mt-1">
        Создано подрядчиков: {{ importResult.contractors_created }} ·
        создано связей: {{ importResult.links_created }} ·
        пропущено дублей: {{ importResult.links_skipped }} ·
        ошибок: {{ importResult.errors.length }}
      </div>
      <ul v-if="importResult.errors.length" class="mt-2 space-y-1">
        <li v-for="error in importResult.errors.slice(0, 10)" :key="`${error.row}-${error.message}`">
          Строка {{ error.row }}: {{ error.message }}
        </li>
      </ul>
      <div v-if="importResult.errors.length > 10" class="mt-2">
        Показаны первые 10 ошибок из {{ importResult.errors.length }}.
      </div>
    </div>

    <DataTable
      :data="items"
      :columns="columns"
      :loading="loading"
      :actions="actions"
      :server-side="true"
      :total-items="pagination.total"
      :current-server-page="pagination.page"
      :total-server-pages="pagination.pages"
      :page-size="pagination.limit"
      :searchable="false"
      :filterable="false"
      :refreshable="false"
      :show-header="false"
      title=""
      empty-message="Подрядчики не найдены"
      @action="handleAction"
      @page-change="changePage"
    >
      <template #column-name="{ item }">
        <div>
          <div class="text-sm font-medium text-gray-900">
            {{ item.name }}
          </div>
          <div class="text-xs text-gray-500">
            ИНН: {{ item.inn }}
          </div>
        </div>
      </template>
    </DataTable>

    <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <form class="w-full max-w-xl rounded-lg bg-white shadow-xl" @submit.prevent="createContractor">
        <div class="border-b border-gray-200 px-5 py-4">
          <h3 class="text-base font-semibold text-gray-900">Добавить подрядчика</h3>
        </div>
        <div class="space-y-4 px-5 py-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Наименование подрядчика</label>
            <input
              v-model.trim="createForm.contractor_name"
              type="text"
              maxlength="255"
              class="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              required
            >
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">ИНН подрядчика</label>
            <input
              v-model.trim="createForm.contractor_inn"
              type="text"
              inputmode="numeric"
              maxlength="12"
              class="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              required
              @input="normalizeCreateInn"
            >
          </div>
          <SearchableDropdown
            v-model="createLeasingCompanyIds"
            label="Лизинговые компании"
            placeholder="Выберите ЛК"
            :items="leasingCompanyDropdownItems"
            label-key="display_name"
            value-key="id"
            multiple
            show-select-all
            search-placeholder="Найти ЛК..."
            :disabled="linksLoading"
          />
          <p v-if="linksError" class="text-sm text-red-600">{{ linksError }}</p>
          <p v-if="formError" class="text-sm text-red-600">{{ formError }}</p>
        </div>
        <div class="flex justify-end gap-2 border-t border-gray-200 px-5 py-4">
          <button type="button" class="btn-secondary" @click="closeCreateModal">Отмена</button>
          <button type="submit" class="btn-primary" :disabled="saving || linksLoading">
            {{ saving ? 'Сохранение...' : 'Сохранить' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="editingItem" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <form class="w-full max-w-xl rounded-lg bg-white shadow-xl" @submit.prevent="updateContractor">
        <div class="border-b border-gray-200 px-5 py-4">
          <h3 class="text-base font-semibold text-gray-900">Редактировать подрядчика</h3>
        </div>
        <div class="space-y-4 px-5 py-4">
          <div class="grid grid-cols-1 gap-3 rounded-md bg-gray-50 p-3 sm:grid-cols-3">
            <div>
              <div class="text-xs font-medium uppercase text-gray-500">ИНН</div>
              <div class="text-sm text-gray-900">{{ editingItem.inn }}</div>
            </div>
            <div>
              <div class="text-xs font-medium uppercase text-gray-500">Создан</div>
              <div class="text-sm text-gray-900">{{ formatDateTime(editingItem.created_at) }}</div>
            </div>
            <div>
              <div class="text-xs font-medium uppercase text-gray-500">Изменён</div>
              <div class="text-sm text-gray-900">{{ formatDateTime(editingItem.updated_at) }}</div>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Наименование</label>
            <input
              v-model.trim="editName"
              type="text"
              maxlength="255"
              class="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              required
            >
          </div>
          <SearchableDropdown
            v-model="selectedLeasingCompanyIds"
            label="Лизинговые компании"
            placeholder="Выберите ЛК"
            :items="leasingCompanyDropdownItems"
            label-key="display_name"
            value-key="id"
            multiple
            show-select-all
            search-placeholder="Найти ЛК..."
            :disabled="linksLoading"
          />
          <p v-if="linksError" class="text-sm text-red-600">{{ linksError }}</p>
          <p v-if="formError" class="text-sm text-red-600">{{ formError }}</p>
        </div>
        <div class="flex justify-end gap-2 border-t border-gray-200 px-5 py-4">
          <button type="button" class="btn-secondary" @click="closeEditModal">Отмена</button>
          <button type="submit" class="btn-primary" :disabled="saving || linksLoading">
            {{ saving ? 'Сохранение...' : 'Сохранить' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowUpTrayIcon,
  PencilIcon,
  PlusIcon,
} from '@heroicons/vue/24/outline'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import {
  createCompaniesAdminApi,
  type ContractorImportResponse,
  type ContractorItem,
  type LeasingCompanyOption,
} from '../api/companiesAdminApi'
import type { Pagination } from '~/types/features'
import type { DropdownItem } from '~/types'
import type { UUID } from '~/types/ids'

interface LeasingCompanyDropdownItem extends DropdownItem {
  id: UUID
  display_name: string
}

const config = useRuntimeConfig()
const toast = useToast()
const api = createCompaniesAdminApi(config)

const items = ref<ContractorItem[]>([])
const leasingCompanies = ref<LeasingCompanyOption[]>([])
const loading = ref(true)
const linksLoading = ref(false)
const saving = ref(false)
const importing = ref(false)
const formError = ref('')
const linksError = ref('')
const importResult = ref<ContractorImportResponse | null>(null)
const showCreateModal = ref(false)
const editingItem = ref<ContractorItem | null>(null)
const createLeasingCompanyIds = ref<UUID[]>([])
const selectedLeasingCompanyIds = ref<UUID[]>([])

const createForm = ref({
  contractor_name: '',
  contractor_inn: '',
})
const editName = ref('')

const currentFilters = ref({
  contractor_name: '',
  inn: '',
})

const pagination = ref<Pagination>({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0,
})

const columns = [
  { key: 'name', label: 'Подрядчик' },
  { key: 'created_at', label: 'Добавлен', type: 'date' },
  { key: 'updated_at', label: 'Обновлён', type: 'date' },
]

const actions = [
  { key: 'edit', label: 'Редактировать', icon: PencilIcon, className: 'text-blue-600 hover:text-blue-900' },
]

const fieldLabels: Record<string, string> = {
  contractor_name: 'Наименование подрядчика',
  contractor_inn: 'ИНН подрядчика',
  name: 'Наименование',
  leasing_company_ids: 'Лизинговые компании',
}

const leasingCompanyDropdownItems = computed<LeasingCompanyDropdownItem[]>(() =>
  leasingCompanies.value.map((company) => ({
    id: company.id,
    display_name: `${company.name || company.id}${company.inn ? ` · ИНН ${company.inn}` : ''}`,
  }))
)

const normalizeDigits = (value: string, maxLength = 12) => value.replace(/\D/g, '').slice(0, maxLength)

const isValidInn = (value: string) => value.length === 10 || value.length === 12

const formatDateTime = (value: string | undefined) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatValidationError = (item: unknown): string => {
  const error = item as { loc?: unknown[]; msg?: string; type?: string }
  const field = typeof error.loc?.[error.loc.length - 1] === 'string'
    ? String(error.loc[error.loc.length - 1])
    : ''
  const label = fieldLabels[field] || field
  if (field.endsWith('inn') || error.type === 'value_error') {
    const msg = error.msg || ''
    if (msg.includes('ИНН') || msg.includes('pattern') || msg.includes('10') || msg.includes('12')) {
      return `${label}: должен содержать 10 или 12 цифр`
    }
  }
  return label ? `${label}: ${error.msg || 'некорректное значение'}` : error.msg || ''
}

const readError = (err: unknown): string => {
  const data = (err as { data?: { detail?: unknown; message?: string } })?.data
  if (Array.isArray(data?.detail)) {
    return data.detail
      .map((item) => formatValidationError(item))
      .filter(Boolean)
      .join('; ') || 'Проверьте данные запроса'
  }
  return typeof data?.detail === 'string'
    ? data.detail
    : data?.message || 'Операция не выполнена'
}

const hasActiveFilters = computed(() =>
  Boolean(currentFilters.value.contractor_name || currentFilters.value.inn)
)

const fetchContractors = async () => {
  loading.value = true
  try {
    const params: Record<string, string> = {
      page: pagination.value.page.toString(),
      limit: pagination.value.limit.toString(),
    }
    if (currentFilters.value.contractor_name) {
      params.contractor_name = currentFilters.value.contractor_name
    }
    const inn = normalizeDigits(currentFilters.value.inn)
    if (inn) params.inn = inn

    const response = await api.getContractors(params)
    items.value = response.items
    pagination.value = response.pagination
  } catch (err) {
    console.error('Error fetching contractors:', err)
    toast.error(readError(err))
  } finally {
    loading.value = false
  }
}

const fetchLeasingCompanies = async () => {
  if (leasingCompanies.value.length > 0) return
  const response = await api.getLeasingCompanies()
  leasingCompanies.value = response.companies || []
}

const changePage = (page: number) => {
  pagination.value.page = page
  fetchContractors()
}

const applyFilters = () => {
  currentFilters.value.inn = normalizeDigits(currentFilters.value.inn)
  pagination.value.page = 1
  fetchContractors()
}

const resetFilters = () => {
  currentFilters.value = {
    contractor_name: '',
    inn: '',
  }
  pagination.value.page = 1
  fetchContractors()
}

const normalizeFilterInn = () => {
  currentFilters.value.inn = normalizeDigits(currentFilters.value.inn)
}

const handleAction = ({ action, item }: { action: string; item: ContractorItem }) => {
  formError.value = ''
  linksError.value = ''
  if (action === 'edit') {
    openEditModal(item)
  }
}

const openCreateModal = async () => {
  formError.value = ''
  linksError.value = ''
  createLeasingCompanyIds.value = []
  createForm.value = {
    contractor_name: '',
    contractor_inn: '',
  }
  showCreateModal.value = true
  linksLoading.value = true
  try {
    await fetchLeasingCompanies()
  } catch (err) {
    linksError.value = readError(err)
  } finally {
    linksLoading.value = false
  }
}

const closeCreateModal = () => {
  showCreateModal.value = false
  formError.value = ''
  linksError.value = ''
  createLeasingCompanyIds.value = []
}

const normalizeCreateInn = () => {
  createForm.value.contractor_inn = normalizeDigits(createForm.value.contractor_inn)
}

const createContractor = async () => {
  const contractorInn = normalizeDigits(createForm.value.contractor_inn)
  createForm.value.contractor_inn = contractorInn
  if (!isValidInn(contractorInn)) {
    formError.value = 'ИНН подрядчика должен содержать 10 или 12 цифр'
    return
  }

  saving.value = true
  formError.value = ''
  try {
    const result = await api.createContractor({
      contractor_name: createForm.value.contractor_name.trim(),
      contractor_inn: contractorInn,
    })
    await Promise.all(createLeasingCompanyIds.value.map((leasingCompanyId) =>
      api.createContractorLink({
        leasing_company_id: leasingCompanyId,
        contractor_name: createForm.value.contractor_name.trim(),
        contractor_inn: contractorInn,
      })
    ))
    toast.success(result.created ? 'Подрядчик добавлен' : 'Подрядчик уже есть в справочнике')
    closeCreateModal()
    await fetchContractors()
  } catch (err) {
    formError.value = readError(err)
  } finally {
    saving.value = false
  }
}

const importExcel = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  importing.value = true
  importResult.value = null
  try {
    const result = await api.importContractorLinks(file)
    importResult.value = result
    if (result.errors.length > 0) {
      toast.warning('Импорт обработан с ошибками по строкам')
    } else {
      toast.success('Импорт Excel обработан')
    }
    await fetchContractors()
  } catch (err) {
    toast.error(readError(err))
  } finally {
    importing.value = false
    input.value = ''
  }
}

const openEditModal = async (item: ContractorItem) => {
  editingItem.value = item
  editName.value = item.name
  selectedLeasingCompanyIds.value = []
  formError.value = ''
  linksError.value = ''
  linksLoading.value = true
  try {
    await fetchLeasingCompanies()
    const response = await api.getContractorLeasingCompanies(item.id)
    selectedLeasingCompanyIds.value = response.items.map((link) => link.leasing_company_id)
  } catch (err) {
    linksError.value = readError(err)
  } finally {
    linksLoading.value = false
  }
}

const closeEditModal = () => {
  editingItem.value = null
  selectedLeasingCompanyIds.value = []
  formError.value = ''
  linksError.value = ''
}

const updateContractor = async () => {
  if (!editingItem.value) return
  saving.value = true
  formError.value = ''
  linksError.value = ''
  try {
    await api.updateContractor(editingItem.value.id, { name: editName.value })
    await api.setContractorLeasingCompanies(editingItem.value.id, selectedLeasingCompanyIds.value)
    toast.success('Подрядчик обновлён')
    closeEditModal()
    await fetchContractors()
  } catch (err) {
    formError.value = readError(err)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchContractors()
})
</script>
