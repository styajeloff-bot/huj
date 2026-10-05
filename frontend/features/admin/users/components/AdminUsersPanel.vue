<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Управление пользователями
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
        <button @click="showCreateUserModal = true" class="btn-primary text-sm">
          Создать пользователя
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

    <DataTable
      :data="users"
      :columns="columns"
      :loading="loading"
      :actions="actions"
      :filters="filters"
      :server-side="true"
      :total-items="pagination.total"
      :current-server-page="pagination.page"
      :total-server-pages="pagination.pages"
      :page-size="pagination.limit"
      :searchable="true"
      empty-message="Пользователи не найдены"
      @action="handleAction"
      @refresh="fetchUsers"
      @page-change="changePage"
      @filter="handleFilter"
      @search="handleSearch"
      @sort="handleSort"
    >
      <!-- Кастомная колонка: Телефон -->
      <template #column-phone="{ item }">
        <span class="text-sm text-gray-900">{{ item.phone || '—' }}</span>
      </template>

      <!-- Кастомная колонка: Роль -->
      <template #column-role="{ item }">
        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full" 
              :class="getRoleColor(String(item.role))">
          {{ getRoleLabel(String(item.role)) }}
        </span>
      </template>

      <!-- Кастомная колонка: Компания -->
      <template #column-company="{ item }">
        <div v-if="item.company_name" class="text-sm text-gray-900">
          {{ item.company_name }}
          <div v-if="item.company_inn" class="text-xs text-gray-500">
            ИНН: {{ item.company_inn }}
          </div>
        </div>
        <div v-else class="text-sm text-gray-400">
          Не указана
        </div>
      </template>

      <!-- Кастомная колонка: ФИО -->
      <template #column-name="{ item }">
        <span class="text-sm font-medium text-gray-900">{{ item.name }}</span>
      </template>

      <!-- Кастомная колонка: Статус -->
      <template #column-is_active="{ item }">
        <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
              :class="item.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'">
          {{ item.is_active ? 'Активен' : 'Неактивен' }}
        </span>
      </template>
    </DataTable>

    <!-- Модальные окна -->
    <UserFormModal
      v-if="showCreateUserModal"
      @close="showCreateUserModal = false"
      @success="handleUserSuccess"
    />

    <UserFormModal
      v-if="showEditUserModal"
      :user="selectedUser"
      @close="showEditUserModal = false"
      @success="handleUserSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import UserFormModal from '~/features/auth/components/UserFormModal.vue'
import { PencilIcon, TrashIcon, UserIcon } from '@heroicons/vue/24/outline'
import { useToast } from '@/composables/useToast'
import ImportProgress from '~/features/admin/shared/components/ImportProgress.vue'
import { useCsvImport } from '~/features/admin/shared/composables/useCsvImport'
import type { DataTableFilter } from '~/types/index'
import type { AdminUser, UserRole, Pagination } from '~/types/features'

const config = useRuntimeConfig()
const toast = useToast()
const csvImport = useCsvImport()

const users = ref<AdminUser[]>([])
const loading = ref(true)
const showCreateUserModal = ref(false)
const showEditUserModal = ref(false)
const selectedUser = ref<AdminUser | null>(null)

const currentFilters = ref({
  search: '',
  role: '',
  is_active: ''
})

const sortBy = ref('')
const sortOrder = ref<'asc' | 'desc'>('asc')

const pagination = ref({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

const columns = [
  { key: 'phone', label: 'Телефон', sortable: true },
  { key: 'role', label: 'Роль', sortable: true },
  { key: 'company', label: 'Компания', sortable: true },
  { key: 'name', label: 'ФИО', sortable: true },
  { key: 'is_active', label: 'Статус', sortable: true }
]

const filters: DataTableFilter[] = [
  {
    key: 'role',
    label: 'Роль',
    type: 'select',
    options: [
      { value: 'client', label: 'Клиент' },
      { value: 'dealer', label: 'Дилер' },
      { value: 'leasing_company', label: 'Лизинговая компания' },
      { value: 'distributor', label: 'Дистрибьютор' },
      { value: 'carcraft_employee', label: 'Сотрудник CarCraft' }
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

const actions = [
  { key: 'edit', label: 'Изменить', icon: PencilIcon, className: 'text-blue-600 hover:text-blue-900' },
  { key: 'toggle', label: 'Изменить статус', icon: UserIcon, className: 'text-gray-600 hover:text-gray-900' },
  { key: 'delete', label: 'Удалить', icon: TrashIcon, className: 'text-red-600 hover:text-red-900' }
]

const fetchUsers = async () => {
  loading.value = true

  try {
    const params = new URLSearchParams({
      page: pagination.value.page.toString(),
      limit: pagination.value.limit.toString()
    })

    if (currentFilters.value.search) params.append('search', currentFilters.value.search)
    if (currentFilters.value.role) params.append('role', currentFilters.value.role)
    if (currentFilters.value.is_active) params.append('is_active', currentFilters.value.is_active)
    if (sortBy.value) {
      params.append('sort_by', sortBy.value)
      params.append('sort_order', sortOrder.value)
    }

    const response = await $fetch<{ users: AdminUser[]; pagination: Pagination }>(`/api/v1/users?${params.toString()}`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    users.value = response.users
    pagination.value = response.pagination
  } catch (err) {
    console.error('Error fetching users:', err)
  } finally {
    loading.value = false
  }
}

const changePage = (page: number) => {
  pagination.value.page = page
  fetchUsers()
}

const handleFilter = (filterValues: Record<string, string>) => {
  currentFilters.value = { ...currentFilters.value, ...filterValues }
  pagination.value.page = 1
  fetchUsers()
}

const handleSearch = (query: string) => {
  currentFilters.value.search = query
  pagination.value.page = 1
  fetchUsers()
}

const handleSort = ({ field, direction }: { field: string; direction: 'asc' | 'desc' }) => {
  sortBy.value = field
  sortOrder.value = direction
  pagination.value.page = 1
  fetchUsers()
}

const exportCsv = async () => {
  const params = new URLSearchParams({ format: 'csv' })
  if (currentFilters.value.search) params.append('search', currentFilters.value.search)
  if (currentFilters.value.role) params.append('role', currentFilters.value.role)
  if (currentFilters.value.is_active) params.append('is_active', currentFilters.value.is_active)
  if (sortBy.value) {
    params.append('sort_by', sortBy.value)
    params.append('sort_order', sortOrder.value)
  }

  try {
    const response = await $fetch(`/api/v1/users?${params}`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    const blob = new Blob([response as BlobPart], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `users_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    console.error('Export error:', err)
    toast.error('Ошибка при выгрузке')
  }
}

const importCsv = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  await csvImport.upload('/api/v1/users/import', file)
  input.value = ''
  fetchUsers()
}

const handleAction = ({ action, item }: { action: string; item: AdminUser }) => {
  if (action === 'edit') {
    selectedUser.value = { ...item }
    showEditUserModal.value = true
  } else if (action === 'toggle') {
    toggleUserStatus(item)
  } else if (action === 'delete') {
    deleteUser(item)
  }
}

const toggleUserStatus = async (user: AdminUser) => {
  try {
    await $fetch(`/api/v1/users/${user.id}`, {
      method: 'PATCH',
      body: { status: user.is_active ? 'disabled' : 'active' },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    user.is_active = !user.is_active
  } catch (err) {
    console.error('Error toggling user status:', err)
  }
}

const deleteUser = async (user: AdminUser) => {
  if (!confirm(`Вы уверены, что хотите удалить пользователя ${user.name}?`)) {
    return
  }

  try {
    await $fetch(`/api/v1/users/${user.id}`, {
      method: 'DELETE',
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    fetchUsers()
  } catch (err) {
    console.error('Error deleting user:', err)
  }
}

const handleUserSuccess = () => {
  showCreateUserModal.value = false
  showEditUserModal.value = false
  selectedUser.value = null
  fetchUsers()
}

const roleLabels: Record<UserRole, string> = {
  client: 'Клиент',
  dealer: 'Дилер',
  leasing_company: 'Лизинговая компания',
  distributor: 'Дистрибьютор',
  carcraft_employee: 'Сотрудник CarCraft'
}

const getRoleLabel = (role: string): string => {
  return roleLabels[role as UserRole] || role
}

const roleColors: Record<UserRole, string> = {
  client: 'bg-blue-100 text-blue-800',
  dealer: 'bg-green-100 text-green-800',
  leasing_company: 'bg-purple-100 text-purple-800',
  distributor: 'bg-orange-100 text-orange-800',
  carcraft_employee: 'bg-red-100 text-red-800'
}

const getRoleColor = (role: string): string => {
  return roleColors[role as UserRole] || 'bg-gray-100 text-gray-800'
}

onMounted(() => {
  fetchUsers()
})
</script>
