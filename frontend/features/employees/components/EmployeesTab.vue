<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">
          {{ tableTitle }}
        </h2>
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">
          Список сотрудников с привязкой к организациям, ролями и правами доступа
        </p>
      </div>
      <button
        v-if="authStore.canCreateEmployees"
        type="button"
        class="btn-primary inline-flex items-center gap-2 text-sm shadow-sm"
        @click="openCreateModal"
      >
        <PlusIcon class="w-4 h-4" />
        Создать сотрудника
      </button>
    </div>

    <!-- Filters -->
    <EmployeeFilters
      :companies="filterOptions.companies"
      :positions="positions"
      :options="filterOptions"
      :initial-filters="filterParams"
      :loading="loading"
      @apply="onApplyFilters"
      @reset="onResetFilters"
    />

    <!-- Error message -->
    <div
      v-if="error"
      class="p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg text-sm text-[color:var(--storefront-error-text,#b91c1c)]"
    >
      {{ error }}
    </div>

    <!-- Loading spinner -->
    <div v-if="loading" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загрузка списка сотрудников...</p>
    </div>

    <!-- Table -->
    <div
      v-else
      class="bg-white rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] shadow-sm overflow-hidden"
    >
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
          <thead class="bg-gray-50">
            <tr>
              <th v-for="column in columns" :key="column.key" scope="col"
                class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                {{ column.label }}
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="employee in employees" :key="employeeKey(employee)" class="hover:bg-gray-50 transition-colors">
              <template v-for="column in columns.slice(0, -2)" :key="column.key">
                <td class="px-4 py-3 text-sm text-gray-800">
                  <span v-if="column.key === 'role'" class="inline-flex px-2 py-0.5 text-xs font-medium rounded-full"
                    :class="getRoleBadgeClass(employee.role)">{{ getRoleLabel(employee.role) }}</span>
                  <template v-else-if="column.key === 'company'">{{ employee.company_name || '—' }}</template>
                  <template v-else-if="column.key === 'brands'">{{ objectNames(employee.brands) }}</template>
                  <template v-else-if="column.key === 'distributors'">{{ objectNames(employee.distributors) }}</template>
                  <template v-else-if="column.key === 'warehouses'">{{ objectNames(employee.warehouses) }}</template>
                  <template v-else-if="column.key === 'position'">{{ employee.position_name || getPositionName(employee.position_id) }}</template>
                  <template v-else-if="column.key === 'name'">{{ employee.name || '—' }}</template>
                  <template v-else-if="column.key === 'phone'">
                    <div class="whitespace-nowrap">{{ employee.phone || '—' }}</div>
                    <div v-if="employee.additional_phone" class="text-xs text-gray-400">Доп: {{ employee.additional_phone }}</div>
                  </template>
                </td>
              </template>

              <!-- Статус -->
              <td class="px-4 py-3 whitespace-nowrap text-sm">
                <span
                  class="inline-flex px-2 py-0.5 text-xs font-semibold rounded-full"
                  :class="employee.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'"
                >
                  {{ employee.is_active ? 'Активен' : 'Неактивен' }}
                </span>
              </td>

              <!-- Действия -->
              <td class="px-4 py-3 whitespace-nowrap text-right text-sm font-medium">
                <div class="flex items-center justify-end gap-3">
                  <button
                    v-if="canEdit(employee)"
                    type="button"
                    class="text-blue-600 hover:text-blue-900 transition-colors inline-flex items-center gap-1"
                    @click="openEditModal(employee)"
                  >
                    <PencilSquareIcon class="w-4 h-4" />
                    Редактировать
                  </button>
                  <button
                    v-if="canEdit(employee)"
                    type="button"
                    class="text-red-600 hover:text-red-900 disabled:opacity-40 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-1"
                    :disabled="!employee.is_active || deactivatingId === employeeKey(employee)"
                    :title="!employee.is_active ? 'Сотрудник уже отключен' : 'Отключить сотрудника'"
                    @click="handleDeactivate(employee)"
                  >
                    <NoSymbolIcon class="w-4 h-4" />
                    Отключить
                  </button>
                  <span
                    v-else
                    class="text-xs text-gray-400 italic"
                  >
                    Только просмотр
                  </span>
                </div>
              </td>
            </tr>

            <tr v-if="employees.length === 0">
              <td
                :colspan="columns.length"
                class="px-6 py-12 text-center text-sm text-gray-500"
              >
                Сотрудники не найдены
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div
        v-if="total > 0"
        class="bg-white px-4 py-3 flex items-center justify-between border-t border-[color:var(--storefront-border,#e5e7eb)] sm:px-6"
      >
        <div class="text-sm text-gray-700">
          Показано
          <span class="font-medium">{{ (currentPage - 1) * perPage + 1 }}</span>
          –
          <span class="font-medium">{{ Math.min(currentPage * perPage, total) }}</span>
          из
          <span class="font-medium">{{ total }}</span>
          сотрудников
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="btn-secondary text-sm px-3 py-1 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="currentPage <= 1 || loading"
            @click="goToPage(currentPage - 1)"
          >
            Назад
          </button>
          <span class="text-sm text-gray-600 px-2">
            {{ currentPage }} / {{ totalPages }}
          </span>
          <button
            type="button"
            class="btn-secondary text-sm px-3 py-1 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="currentPage >= totalPages || loading"
            @click="goToPage(currentPage + 1)"
          >
            Вперед
          </button>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <EmployeeFormModal
      v-if="showModal"
      :show="showModal"
      :employee="editingEmployee"
      :companies="companies"
      :positions="positions"
      @close="showModal = false"
      @saved="onEmployeeSaved"
    />
  </div>
</template>

<script setup lang="ts">
import {
  PlusIcon,
  PencilSquareIcon,
  NoSymbolIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import { useAuthStore } from '~/features/auth/store/auth'
import { createCompanyApi } from '~/features/company/api/companyApi'
import {
  listEmployees,
  listPositions,
  deactivateEmployee,
  employeeFilterOptions,
  type EmployeeItem,
  type EmployeeListItem,
  type EmployeeObject,
  type EmployeeFilterOptions,
  type PositionItem,
} from '../api/employeesApi'
import EmployeeFilters, { type FilterState } from './EmployeeFilters.vue'
import EmployeeFormModal from './EmployeeFormModal.vue'

const authStore = useAuthStore()
const config = useRuntimeConfig()
const companyApi = createCompanyApi(config)

const employees = ref<EmployeeListItem[]>([])
const companies = ref<Array<{ id: UUID; name: string }>>([])
const positions = ref<PositionItem[]>([])

const loading = ref(true)
const error = ref('')
const deactivatingId = ref<string | null>(null)

const currentPage = ref(1)
const perPage = ref(20)
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / perPage.value)))

const emptyFilters = (): FilterState => ({
  role: '', company_id: '', position_id: '', dealer_id: '', distributor_id: '',
  brand_id: '', warehouse_id: '', name: '', phone: '',
})
const filterParams = ref<FilterState>(emptyFilters())
const filterOptions = ref<EmployeeFilterOptions>({ companies: [], dealers: [], distributors: [], brands: [], warehouses: [] })
const tableTitle = computed(() => filterParams.value.role === 'dealer'
  ? 'Пользователи Дилеры' : filterParams.value.role === 'distributor' ? 'Пользователи Дистрибьюторы' : 'Пользователи')
const columns = computed(() => {
  const roleColumns = filterParams.value.role === 'dealer'
    ? [{ key: 'company', label: 'Дилер' }, { key: 'brands', label: 'Марка' },
        { key: 'distributors', label: 'Дистрибьютор' }, { key: 'warehouses', label: 'Склад дилера' }]
    : filterParams.value.role === 'distributor'
      ? [{ key: 'company', label: 'Дистрибьютор' }, { key: 'brands', label: 'Марка' }, { key: 'warehouses', label: 'Склад дистрибьютора' }]
      : [{ key: 'role', label: 'Роль' }, { key: 'company', label: 'Компания' }]
  return [...roleColumns, { key: 'position', label: 'Должность' }, { key: 'name', label: 'ФИО' },
    { key: 'phone', label: 'Телефон' }, { key: 'status', label: 'Статус' }, { key: 'actions', label: 'Кнопки' }]
})
const objectNames = (objects: EmployeeObject[]): string =>
  [...new Set(objects.map((object) => object.name).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru')).join(', ') || '—'

const showModal = ref(false)
const editingEmployee = ref<EmployeeItem | null>(null)

const employeeKey = (employee: EmployeeListItem): string => employee.row_type === 'company'
  ? `company:${employee.user_company_id}` : `system:${employee.user_id}`

const getPositionName = (positionId?: UUID | null): string => {
  if (!positionId) return '—'
  const match = positions.value.find((p) => p.id === positionId)
  return match?.name || '—'
}

const getRoleLabel = (role?: string): string => {
  switch (role) {
    case 'client':
      return 'Клиент'
    case 'dealer':
      return 'Дилер'
    case 'distributor':
      return 'Дистрибьютор'
    case 'leasing_company':
      return 'Лизинговая компания'
    case 'admin':
    case 'carcraft_employee':
      return 'Сотрудник КК'
    default:
      return role || '—'
  }
}

const getRoleBadgeClass = (role?: string): string => {
  switch (role) {
    case 'client':
      return 'bg-gray-100 text-gray-800'
    case 'dealer':
      return 'bg-blue-100 text-blue-800'
    case 'distributor':
      return 'bg-purple-100 text-purple-800'
    case 'leasing_company':
      return 'bg-emerald-100 text-emerald-800'
    case 'admin':
    case 'carcraft_employee':
      return 'bg-indigo-100 text-indigo-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

const canEdit = (employee: EmployeeListItem): boolean => {
  if (employee.row_type === 'system') return false
  if (authStore.isCarCraftEmployee) return employee.can_edit !== false
  if (employee.user_id === authStore.user?.id || !authStore.canCreateEmployees) return false
  return employee.can_edit === true
}

let optionsRequest = 0
const fetchFilterOptions = async () => {
  const requestId = ++optionsRequest
  const options = await employeeFilterOptions(config, filterParams.value.role || undefined)
  if (requestId === optionsRequest) filterOptions.value = options
}

const fetchMetadata = async () => {
  try {
    const posRes = await listPositions(config)
    positions.value = posRes.items || []
  } catch (e) {
    console.error('Failed to load positions', e)
  }

  try {
    const result = authStore.isCarCraftEmployee
      ? await companyApi.listCompanies() : await companyApi.getMyCompanies()
    companies.value = (result.companies || []).map((company) => ({ id: company.id, name: company.name }))
  } catch (e) {
    console.error('Failed to load companies', e)
  }

  try {
    await fetchFilterOptions()
  } catch (e) {
    console.error('Failed to load employee filter options', e)
    error.value = 'Не удалось загрузить фильтры сотрудников'
  }
}

let employeesRequest = 0
const fetchEmployees = async () => {
  const requestId = ++employeesRequest
  loading.value = true
  error.value = ''
  try {
    const res = await listEmployees(config, {
      role: filterParams.value.role || undefined,
      company_id: filterParams.value.role !== 'dealer' ? filterParams.value.company_id || undefined : undefined,
      dealer_id: filterParams.value.role === 'dealer' ? filterParams.value.dealer_id || undefined : undefined,
      distributor_id: filterParams.value.role === 'dealer' ? filterParams.value.distributor_id || undefined : undefined,
      brand_id: filterParams.value.role === 'distributor' ? filterParams.value.brand_id || undefined : undefined,
      warehouse_id: ['dealer', 'distributor'].includes(filterParams.value.role) ? filterParams.value.warehouse_id || undefined : undefined,
      position_id: filterParams.value.position_id || undefined,
      name: filterParams.value.name.trim() || undefined,
      phone: filterParams.value.phone.trim() || undefined,
      page: currentPage.value,
      per_page: perPage.value,
    })
    if (requestId !== employeesRequest) return
    employees.value = res.items || []
    total.value = res.total ?? employees.value.length
    if (res.page) currentPage.value = res.page
    if (res.per_page) perPage.value = res.per_page
  } catch (err: any) {
    if (requestId === employeesRequest) error.value = err?.data?.detail || err?.message || 'Не удалось загрузить список сотрудников'
  } finally {
    if (requestId === employeesRequest) loading.value = false
  }
}

const onApplyFilters = async (filters: FilterState) => {
  const roleChanged = filters.role !== filterParams.value.role
  filterParams.value = { ...filters }
  currentPage.value = 1
  await Promise.all([
    fetchEmployees(),
    roleChanged ? fetchFilterOptions().catch(() => { error.value = 'Не удалось загрузить фильтры сотрудников' }) : Promise.resolve(),
  ])
}

const onResetFilters = () => onApplyFilters(emptyFilters())

const goToPage = (page: number) => {
  if (page < 1 || page > totalPages.value) return
  currentPage.value = page
  fetchEmployees()
}

const openCreateModal = () => {
  editingEmployee.value = null
  showModal.value = true
}

const openEditModal = (employee: EmployeeListItem) => {
  if (employee.row_type !== 'company' || !canEdit(employee)) return
  if (!employee.company_role) {
    error.value = 'Не удалось определить роль сотрудника в компании'
    return
  }
  editingEmployee.value = { ...employee, role: employee.company_role }
  showModal.value = true
}

const onEmployeeSaved = async () => {
  await fetchEmployees()
}

const handleDeactivate = async (employee: EmployeeListItem) => {
  if (employee.row_type !== 'company' || !canEdit(employee)) return
  const key = employeeKey(employee)
  if (!employee.is_active || deactivatingId.value) return
  if (!window.confirm(`Отключить сотрудника «${employee.name || employee.phone || ''}»?`)) return

  deactivatingId.value = key
  error.value = ''
  try {
    await deactivateEmployee(config, employee.user_id, employee.company_id)
    employee.is_active = false
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Не удалось отключить сотрудника'
  } finally {
    deactivatingId.value = null
  }
}

onMounted(async () => {
  await Promise.all([fetchMetadata(), fetchEmployees()])
})
</script>
