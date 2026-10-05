<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Управление компаниями
      </h2>
      <div class="flex gap-2">
        <button @click="exportCsv" class="btn-secondary text-sm">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
          </svg>
          Выгрузить CSV
        </button>
        <label class="btn-secondary text-sm cursor-pointer">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4 4m4-4v12"></path>
          </svg>
          Загрузить CSV
          <input type="file" accept=".csv" class="hidden" @change="importCsv">
        </label>
        <button @click="showCreateCompanyModal = true" class="btn-primary">
          Создать компанию
        </button>
      </div>
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

    <div class="grid grid-cols-1 gap-3 mb-4 md:grid-cols-5">
      <label class="text-sm text-gray-700">Тип
        <select v-model="currentFilters.company_type" class="select-field mt-1" @change="applyFilters">
          <option value="">Все типы</option>
          <option value="dealer">Дилер</option>
          <option value="leasing_company">Лизинговая компания</option>
          <option value="distributor">Дистрибьютор</option>
          <option value="other">Другое</option>
        </select>
      </label>
      <label class="text-sm text-gray-700">Наименование
        <input v-model="currentFilters.name" class="block w-full mt-1 border rounded-md px-3 py-2" placeholder="Введите наименование" @change="applyFilters">
      </label>
      <label class="text-sm text-gray-700">Статус
        <select v-model="currentFilters.is_active" class="select-field mt-1" @change="applyFilters">
          <option value="">Все статусы</option><option value="true">Активна</option><option value="false">Неактивна</option>
        </select>
      </label>
      <label class="text-sm text-gray-700">Номер телефона
        <input v-model="currentFilters.phone" class="block w-full mt-1 border rounded-md px-3 py-2" placeholder="Введите номер телефона" @change="applyFilters">
      </label>
      <button class="self-end btn-secondary" @click="resetFilters">Сбросить</button>
    </div>

    <DataTable
      :data="companies"
      :columns="columns"
      :loading="loading"
      :filters="filters"
      :server-side="true"
      :total-items="pagination.total"
      :current-server-page="pagination.page"
      :total-server-pages="pagination.pages"
      :page-size="pagination.limit"
      :searchable="true"
      :show-header="false"
      row-clickable
      empty-message="Компании не найдены"
      @row-click="openCompanyDetail"
      @refresh="fetchCompanies"
      @page-change="changePage"
      @filter="handleFilter"
      @search="handleSearch"
    >
      <!-- Кастомная колонка: Компания -->
      <template #column-name="{ item }">
        <div>
          <div class="text-sm font-medium text-gray-900">{{ item.name }}</div>
          <div v-if="item.inn" class="text-sm text-gray-500">ИНН: {{ item.inn }}</div>
        </div>
      </template>

      <!-- Кастомная колонка: Тип -->
      <template #column-company_type="{ item }">
        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full" 
              :class="getTypeColor(String(item.company_type))">
          {{ getTypeLabel(String(item.company_type)) }}
        </span>
      </template>

      <!-- Кастомная колонка: Контакты -->
      <template #column-contacts="{ item }">
        <div class="text-sm text-gray-900">
          <div v-if="item.phone">{{ formatCompanyPhone(String(item.phone)) }}</div>
          <div v-if="item.email" class="text-gray-500">{{ item.email }}</div>
        </div>
      </template>

      <!-- Кастомная колонка: Статус -->
      <template #column-is_active="{ item }">
        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
              :class="item.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'">
          {{ item.is_active ? 'Активна' : 'Неактивна' }}
        </span>
      </template>
    </DataTable>

    <!-- Модальные окна -->
    <CompanyFormModal
      v-if="showCreateCompanyModal"
      @close="showCreateCompanyModal = false"
      @success="handleCompanySuccess"
    />

    <CompanyDetailModal
      v-if="showCompanyDetailModal && selectedCompany"
      :company="selectedCompany"
      :contractor-dropdown-items="contractorDropdownItems"
      v-model:contractor-ids="selectedContractorIds"
      :contractor-loading="contractorLinksLoading"
      :contractor-saving="contractorLinksSaving"
      :contractor-error="contractorLinksError"
      :contractor-controls-disabled="contractorLinksLoading || !leasingCompanyRef"
      :distributor-brand-items="distributorBrandItems"
      v-model:distributor-brand-ids="selectedDistributorBrandIds"
      :distributor-brands-loading="distributorBrandsLoading"
      :distributor-brands-saving="distributorBrandsSaving"
      :distributor-brands-error="distributorBrandsError"
      @close="closeCompanyDetail"
      @updated="replaceCompanyFromEditor"
      @save-contractors="saveLeasingCompanyContractors"
      @save-distributor-brands="saveDistributorBrands"
    />
  </div>
</template>

<script setup lang="ts">
import {
  createCompaniesAdminApi,
  type AdminCompanyDetail,
  type ContractorItem,
  type DistributorBrandItem,
  type LeasingCompanyOption,
} from '../api/companiesAdminApi'
import CompanyFormModal from '~/features/company/components/CompanyFormModal.vue'
import CompanyDetailModal from '~/features/company/components/CompanyDetailModal.vue'
import { formatCompanyPhone } from '~/features/company/utils/companyPhone'
import ImportProgress from '~/features/admin/shared/components/ImportProgress.vue'
import { useCsvImport } from '~/features/admin/shared/composables/useCsvImport'
import type { DataTableFilter, DropdownItem } from '~/types/index'
import type { Company, CompanyType } from '~/types/features'
import type { CatalogId, UUID } from '~/types/ids'

interface ContractorDropdownItem extends DropdownItem {
  id: UUID
  display_name: string
}

const config = useRuntimeConfig()
const api = createCompaniesAdminApi(config)
const csvImport = useCsvImport()
const toast = useToast()

const companies = ref<Company[]>([])
const loading = ref(true)
const showCreateCompanyModal = ref(false)
const showCompanyDetailModal = ref(false)
const selectedCompany = ref<AdminCompanyDetail | null>(null)
const contractorOptions = ref<ContractorItem[]>([])
const selectedContractorIds = ref<UUID[]>([])
const leasingCompanies = ref<LeasingCompanyOption[]>([])
const leasingCompanyRef = ref<LeasingCompanyOption | null>(null)
const contractorLinksLoading = ref(false)
const contractorLinksSaving = ref(false)
const contractorLinksError = ref('')
const contractorLinksRequestId = ref(0)
const distributorBrandItems = ref<DistributorBrandItem[]>([])
const selectedDistributorBrandIds = ref<CatalogId[]>([])
const distributorBrandsLoading = ref(false)
const distributorBrandsSaving = ref(false)
const distributorBrandsError = ref('')
const distributorBrandsRequestId = ref(0)

const currentFilters = ref({
  search: '',
  name: '',
  phone: '',
  company_type: '',
  is_active: ''
})

const pagination = ref({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

const columns = [
  { key: 'name', label: 'Компания' },
  { key: 'company_type', label: 'Тип' },
  { key: 'contacts', label: 'Контакты' },
  { key: 'user_count', label: 'Пользователи' },
  { key: 'is_active', label: 'Статус' }
]

const filters: DataTableFilter[] = [
  {
    key: 'company_type',
    label: 'Тип',
    type: 'select',
    options: [
      { value: 'dealer', label: 'Дилер' },
      { value: 'leasing_company', label: 'Лизинговая компания' },
      { value: 'distributor', label: 'Дистрибьютор' },
      { value: 'other', label: 'Другое' }
    ]
  },
  {
    key: 'is_active',
    label: 'Статус',
    type: 'select',
    options: [
      { value: 'true', label: 'Активные' },
      { value: 'false', label: 'Неактивные' }
    ]
  }
]

const contractorDropdownItems = computed<ContractorDropdownItem[]>(() =>
  contractorOptions.value.map((contractor) => ({
    id: contractor.id,
    display_name: `${contractor.name} · ИНН ${contractor.inn}`
  }))
)

const fetchCompanies = async () => {
  loading.value = true

  try {
    const params: Record<string, string> = {
      page: pagination.value.page.toString(),
      limit: pagination.value.limit.toString()
    }

    if (currentFilters.value.search) params.search = currentFilters.value.search
    if (currentFilters.value.name) params.name = currentFilters.value.name
    if (currentFilters.value.phone) params.phone = currentFilters.value.phone
    if (currentFilters.value.company_type) params.company_type = currentFilters.value.company_type
    if (currentFilters.value.is_active) params.is_active = currentFilters.value.is_active

    const response = await api.getCompanies(params)

    companies.value = response.companies
    pagination.value = response.pagination
  } catch (err) {
    console.error('Error fetching companies:', err)
  } finally {
    loading.value = false
  }
}

const changePage = (page: number) => {
  pagination.value.page = page
  fetchCompanies()
}

const handleFilter = (filterValues: Record<string, string>) => {
  currentFilters.value = { ...currentFilters.value, ...filterValues }
  pagination.value.page = 1
  fetchCompanies()
}

const handleSearch = (query: string) => {
  currentFilters.value.search = query
  pagination.value.page = 1
  fetchCompanies()
}

const applyFilters = () => {
  pagination.value.page = 1
  fetchCompanies()
}

const resetFilters = () => {
  currentFilters.value = { search: '', name: '', phone: '', company_type: '', is_active: '' }
  applyFilters()
}

const openCompanyDetail = (item: Record<string, unknown>) => {
  const company = item as Company
  selectedCompany.value = toAdminCompanyDetail(company)
  showCompanyDetailModal.value = true
  resetContractorLinksState()
  resetDistributorBrandsState()
  if (company.company_type === 'leasing_company') {
    loadContractorLinks(company)
  }
  if (company.company_type === 'distributor') {
    loadDistributorBrands(company)
  }
}

const toAdminCompanyDetail = (company: Company): AdminCompanyDetail => ({
  id: company.id,
  name: company.name,
  inn: company.inn,
  kpp: company.kpp,
  ogrn: company.ogrn,
  company_type: company.company_type,
  phone: company.phone,
  email: company.email,
  website: company.website,
  legal_address: company.legal_address,
  actual_address: company.actual_address,
  is_active: company.is_active,
  user_count: company.user_count,
  application_count: company.application_count,
  created_at: company.created_at
})

const replaceCompanyFromEditor = (company: AdminCompanyDetail) => {
  companies.value = companies.value.map((item) =>
    item.id === company.id ? { ...item, ...company } : item
  )
  if (selectedCompany.value?.id === company.id) {
    selectedCompany.value = company
  }
}


const closeCompanyDetail = () => {
  showCompanyDetailModal.value = false
  selectedCompany.value = null
  resetContractorLinksState()
  resetDistributorBrandsState()
}

const handleCompanySuccess = () => {
  showCreateCompanyModal.value = false
  closeCompanyDetail()
  fetchCompanies()
}

const readAdminError = (err: unknown): string => {
  const data = (err as { data?: { detail?: unknown; message?: string } })?.data
  if (Array.isArray(data?.detail)) {
    return data.detail
      .map((item) => {
        const error = item as { loc?: unknown[]; msg?: string }
        const field = typeof error.loc?.[error.loc.length - 1] === 'string'
          ? String(error.loc[error.loc.length - 1])
          : ''
        return field ? `${field}: ${error.msg || 'некорректное значение'}` : error.msg || ''
      })
      .filter(Boolean)
      .join('; ') || 'Проверьте данные запроса'
  }
  return typeof data?.detail === 'string'
    ? data.detail
    : data?.message || 'Операция не выполнена'
}

const fetchLeasingCompanies = async () => {
  if (leasingCompanies.value.length > 0) return
  const response = await api.getLeasingCompanies()
  leasingCompanies.value = response.companies || []
}

const findLeasingCompanyRef = (company: Company): LeasingCompanyOption | null => {
  const companyId = company.id
  const companyInn = company.inn || ''
  return leasingCompanies.value.find((leasingCompany) =>
    leasingCompany.company_id === companyId
    || Boolean(companyInn && leasingCompany.inn === companyInn)
  ) || null
}

const loadContractorLinks = async (company: Company) => {
  const targetCompanyId = company.id
  const requestId = ++contractorLinksRequestId.value
  const isCurrentRequest = () =>
    contractorLinksRequestId.value === requestId
    && selectedCompany.value?.id === targetCompanyId

  selectedContractorIds.value = []
  leasingCompanyRef.value = null
  contractorLinksError.value = ''
  contractorLinksLoading.value = true
  try {
    const [, contractorsResponse] = await Promise.all([
      fetchLeasingCompanies(),
      api.getContractors({ page: '1', limit: '200' })
    ])
    if (!isCurrentRequest()) return
    contractorOptions.value = contractorsResponse.items
    leasingCompanyRef.value = findLeasingCompanyRef(company)
    if (!leasingCompanyRef.value) {
      contractorLinksError.value = 'Связанная запись лизинговой компании не найдена'
      return
    }

    const links = await api.getLeasingCompanyContractors(leasingCompanyRef.value.id)
    if (!isCurrentRequest()) return
    selectedContractorIds.value = links.items.map((link) => link.contractor_id)
  } catch (err) {
    if (!isCurrentRequest()) return
    contractorLinksError.value = readAdminError(err)
  } finally {
    if (isCurrentRequest()) {
      contractorLinksLoading.value = false
    }
  }
}

const resetContractorLinksState = () => {
  contractorLinksRequestId.value += 1
  selectedContractorIds.value = []
  leasingCompanyRef.value = null
  contractorLinksError.value = ''
  contractorLinksLoading.value = false
  contractorLinksSaving.value = false
}

const saveLeasingCompanyContractors = async () => {
  if (!leasingCompanyRef.value) return
  contractorLinksSaving.value = true
  contractorLinksError.value = ''
  try {
    const response = await api.setLeasingCompanyContractors(
      leasingCompanyRef.value.id,
      selectedContractorIds.value
    )
    selectedContractorIds.value = response.items.map((link) => link.contractor_id)
    toast.success('Связи лизинговой компании обновлены')
  } catch (err) {
    contractorLinksError.value = readAdminError(err)
  } finally {
    contractorLinksSaving.value = false
  }
}

const loadDistributorBrands = async (company: Company) => {
  const targetCompanyId = company.id
  const requestId = ++distributorBrandsRequestId.value
  const isCurrentRequest = () =>
    distributorBrandsRequestId.value === requestId
    && selectedCompany.value?.id === targetCompanyId

  distributorBrandItems.value = []
  selectedDistributorBrandIds.value = []
  distributorBrandsError.value = ''
  distributorBrandsLoading.value = true
  try {
    const response = await api.getDistributorBrands(targetCompanyId)
    if (!isCurrentRequest()) return
    distributorBrandItems.value = response.available_brands
    selectedDistributorBrandIds.value = response.selected_brand_ids
  } catch (err) {
    if (!isCurrentRequest()) return
    distributorBrandsError.value = readAdminError(err)
  } finally {
    if (isCurrentRequest()) {
      distributorBrandsLoading.value = false
    }
  }
}

const resetDistributorBrandsState = () => {
  distributorBrandsRequestId.value += 1
  distributorBrandItems.value = []
  selectedDistributorBrandIds.value = []
  distributorBrandsError.value = ''
  distributorBrandsLoading.value = false
  distributorBrandsSaving.value = false
}

const saveDistributorBrands = async () => {
  const company = selectedCompany.value
  if (!company || company.company_type !== 'distributor') return

  const targetCompanyId = company.id
  const requestId = distributorBrandsRequestId.value
  const isCurrentRequest = () =>
    distributorBrandsRequestId.value === requestId
    && selectedCompany.value?.id === targetCompanyId

  distributorBrandsSaving.value = true
  distributorBrandsError.value = ''
  try {
    const response = await api.setDistributorBrands(targetCompanyId, {
      brand_ids: selectedDistributorBrandIds.value
    })
    if (!isCurrentRequest()) return
    distributorBrandItems.value = response.available_brands
    selectedDistributorBrandIds.value = response.selected_brand_ids
    toast.success('Марки дистрибьютора обновлены')
  } catch (err) {
    if (!isCurrentRequest()) return
    distributorBrandsError.value = readAdminError(err)
  } finally {
    if (isCurrentRequest()) {
      distributorBrandsSaving.value = false
    }
  }
}

const companyTypeLabels: Record<CompanyType, string> = {
  dealer: 'Дилер',
  leasing_company: 'Лизинговая компания',
  distributor: 'Дистрибьютор',
  other: 'Другое'
}

const getTypeLabel = (type: string): string => {
  return companyTypeLabels[type as CompanyType] || type
}

const companyTypeColors: Record<CompanyType, string> = {
  dealer: 'bg-green-100 text-green-800',
  leasing_company: 'bg-purple-100 text-purple-800',
  distributor: 'bg-orange-100 text-orange-800',
  other: 'bg-gray-100 text-gray-800'
}

const getTypeColor = (type: string): string => {
  return companyTypeColors[type as CompanyType] || 'bg-gray-100 text-gray-800'
}

const exportCsv = async () => {
  const params = new URLSearchParams({ format: 'csv' })
  if (currentFilters.value.search) params.append('search', currentFilters.value.search)
  if (currentFilters.value.company_type) params.append('company_type', currentFilters.value.company_type)
  if (currentFilters.value.is_active) params.append('is_active', currentFilters.value.is_active)

  try {
    const response = await fetch(`${config.public.apiBase}/api/v1/companies?${params}`, {
      credentials: 'include'
    })
    if (!response.ok) throw new Error('Export failed')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `companies_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    console.error('Export error:', err)
  }
}

const importCsv = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  await csvImport.upload('/api/v1/companies/import', file)
  input.value = ''
  fetchCompanies()
}

onMounted(() => {
  fetchCompanies()
})
</script>
