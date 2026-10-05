<template>
  <div class="space-y-4">
    <!-- Filters Bar -->
    <div class="bg-white rounded-lg border border-gray-200 p-4">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- Filter by Warehouse -->
        <div>
          <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">
            Склад
          </label>
          <select
            v-model="filters.warehouse_id"
            class="select-field"
            @change="handleFilterChange"
          >
            <option value="">Все склады</option>
            <option v-for="wh in warehouses" :key="wh.id" :value="wh.id">
              {{ wh.name }} ({{ wh.address }})
            </option>
          </select>
        </div>

        <!-- Filter by Status -->
        <div>
          <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">
            Статус активности
          </label>
          <select
            v-model="filters.is_active"
            class="select-field"
            @change="handleFilterChange"
          >
            <option value="">Все статусы</option>
            <option value="true">Только активные</option>
            <option value="false">Только неактивные</option>
          </select>
        </div>

        <!-- Reset Button -->
        <div class="flex items-end">
          <button
            type="button"
            class="btn-secondary text-sm h-10 w-full"
            @click="resetFilters"
          >
            Сбросить фильтры
          </button>
        </div>
      </div>
    </div>

    <!-- Error Banner -->
    <div
      v-if="errorMessage"
      class="flex items-start justify-between gap-4 rounded-lg border border-red-200 bg-red-50 p-4"
      role="alert"
    >
      <p class="text-sm text-red-800">{{ errorMessage }}</p>
      <button
        type="button"
        class="text-xs font-medium text-red-600 hover:text-red-800 underline"
        @click="fetchRules"
      >
        Повторить
      </button>
    </div>

    <!-- Table -->
    <div class="bg-white shadow overflow-hidden rounded-lg border border-gray-200">
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Владелец склада
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Склад
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Кому выдан доступ
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Тип доступа
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Марка
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Сайт
              </th>
              <th scope="col" class="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                Активность
              </th>
              <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Дата создания
              </th>
              <th scope="col" class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Действия
              </th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <!-- Loading skeleton -->
            <tr v-if="loading && rules.length === 0">
              <td colspan="9" class="px-6 py-12 text-center text-sm text-gray-500">
                <div class="inline-flex items-center gap-2">
                  <svg class="animate-spin h-5 w-5 text-blue-600" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                  </svg>
                  <span>Загрузка правил доступа...</span>
                </div>
              </td>
            </tr>

            <!-- Empty state -->
            <tr v-else-if="rules.length === 0">
              <td colspan="9" class="px-6 py-12 text-center text-sm text-gray-500">
                Правила доступа не найдены
              </td>
            </tr>

            <!-- Rules list -->
            <tr v-for="rule in rules" :key="rule.id" class="hover:bg-gray-50 transition-colors">
              <!-- Владелец склада -->
              <td class="px-6 py-4">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="text-sm font-medium text-gray-900">
                    {{ rule.owner_company_name || '—' }}
                  </span>
                  <span
                    v-if="rule.owner_company_type"
                    :class="rule.owner_company_type === 'distributor' ? 'bg-indigo-100 text-indigo-800' : 'bg-purple-100 text-purple-800'"
                    class="inline-flex px-1.5 py-0.5 text-xs font-medium rounded"
                  >
                    {{ rule.owner_company_type === 'distributor' ? 'Дистрибьютор' : 'Дилер' }}
                  </span>
                </div>
              </td>

              <!-- Склад -->
              <td class="px-6 py-4">
                <div class="text-sm font-medium text-gray-900">{{ rule.warehouse_name }}</div>
              </td>

              <!-- Кому выдан доступ -->
              <td class="px-6 py-4">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-medium text-gray-900">{{ rule.target_name }}</span>
                  <span
                    v-if="rule.source_group_id"
                    class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800"
                    title="Правило выдано через группу дилеров"
                  >
                    Группа: {{ rule.source_group_name || 'Группа' }}
                  </span>
                </div>
              </td>

              <!-- Тип доступа -->
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  v-if="rule.warehouse_access_type === 'B'"
                  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800"
                >
                  В – разрешена работа с заявками
                </span>
                <span
                  v-else-if="rule.warehouse_access_type === 'C'"
                  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800"
                >
                  С – работа с заявками недоступна
                </span>
                <span
                  v-else-if="rule.warehouse_access_type === 'A'"
                  class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-800"
                >
                  A — Собственный
                </span>
                <span v-else class="text-xs text-gray-400">—</span>
              </td>

              <!-- Марка -->
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  v-if="rule.brand_name"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200"
                  title="Ограничение доступа по марке"
                >
                  Ограничение: {{ rule.brand_name }}
                </span>
                <span
                  v-else-if="rule.warehouse_brand_names && rule.warehouse_brand_names.length > 0"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700"
                >
                  {{ rule.warehouse_brand_names.join(', ') }}
                </span>
                <span v-else class="text-sm text-gray-400">—</span>
              </td>

              <!-- Сайт -->
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  v-if="rule.site_name"
                  class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-50 text-purple-700"
                >
                  {{ rule.site_name }}
                </span>
                <span v-else class="text-sm text-gray-400">Все сайты</span>
              </td>

              <!-- Активность (Toggle switch) -->
              <td class="px-6 py-4 whitespace-nowrap text-center">
                <button
                  type="button"
                  role="switch"
                  :aria-checked="rule.is_active"
                  :disabled="updatingRuleId === rule.id || !canManage || (rule.warehouse_access_type === 'A' && !authStore.isCarCraftEmployee)"
                  :class="[
                    rule.is_active ? 'bg-blue-600' : 'bg-gray-200',
                    'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed'
                  ]"
                  :title="rule.warehouse_access_type === 'A' && !authStore.isCarCraftEmployee ? 'Правило владельца активно всегда' : 'Переключить активность'"
                  @click="toggleActive(rule)"
                >
                  <span class="sr-only">Активность правила</span>
                  <span
                    :class="[
                      rule.is_active ? 'translate-x-5' : 'translate-x-0',
                      'pointer-events-none relative inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out'
                    ]"
                  >
                    <span
                      v-if="updatingRuleId === rule.id"
                      class="absolute inset-0 flex items-center justify-center"
                    >
                      <svg class="h-3 w-3 animate-spin text-blue-600" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
                      </svg>
                    </span>
                  </span>
                </button>
              </td>

              <!-- Дата создания -->
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {{ formatDate(rule.created_at) }}
              </td>

              <!-- Действия -->
              <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                <div class="inline-flex items-center justify-end gap-1">
                  <button
                    v-if="canManage && (rule.warehouse_access_type !== 'A' || authStore.isCarCraftEmployee)"
                    type="button"
                    class="text-blue-600 hover:text-blue-900 inline-flex items-center p-1 rounded hover:bg-blue-50 transition-colors"
                    title="Редактировать правило"
                    @click="openEditModal(rule)"
                  >
                    <PencilIcon class="w-5 h-5" />
                  </button>
                  <button
                    v-if="canManage && (rule.warehouse_access_type !== 'A' || authStore.isCarCraftEmployee)"
                    type="button"
                    class="text-red-600 hover:text-red-900 inline-flex items-center p-1 rounded hover:bg-red-50 transition-colors"
                    title="Удалить правило"
                    @click="confirmDelete(rule)"
                  >
                    <TrashIcon class="w-5 h-5" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination Footer -->
      <div
        v-if="pagination.pages > 1"
        class="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6"
      >
        <div class="text-sm text-gray-700">
          Показаны <span class="font-medium">{{ (pagination.page - 1) * pagination.limit + 1 }}</span>
          — <span class="font-medium">{{ Math.min(pagination.page * pagination.limit, pagination.total) }}</span>
          из <span class="font-medium">{{ pagination.total }}</span> правил
        </div>
        <div class="flex space-x-2">
          <button
            type="button"
            class="btn-secondary text-sm"
            :disabled="pagination.page <= 1 || loading"
            @click="changePage(pagination.page - 1)"
          >
            Назад
          </button>
          <button
            type="button"
            class="btn-secondary text-sm"
            :disabled="pagination.page >= pagination.pages || loading"
            @click="changePage(pagination.page + 1)"
          >
            Вперёд
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div
      v-if="showDeleteConfirm && ruleToDelete"
      class="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50 p-4"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full shadow-xl">
        <h3 class="text-lg font-medium text-gray-900 mb-3">
          Удалить правило доступа?
        </h3>
        <p class="text-sm text-gray-600 mb-6 leading-relaxed">
          Вы уверены, что хотите удалить правило доступа к складу
          <span class="font-semibold text-gray-900">«{{ ruleToDelete.warehouse_name }}»</span>
          для
          <span class="font-semibold text-gray-900">«{{ ruleToDelete.target_name }}»</span>?
          Это действие нельзя отменить.
        </p>
        <div class="flex justify-end space-x-3">
          <button
            type="button"
            class="btn-secondary"
            :disabled="deleting"
            @click="cancelDelete"
          >
            Отмена
          </button>
          <button
            type="button"
            class="btn-danger"
            :disabled="deleting"
            @click="handleDeleteRule"
          >
            <span v-if="deleting">Удаление...</span>
            <span v-else>Удалить</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Edit Rule Modal -->
    <div
      v-if="showEditModal && ruleToEdit"
      class="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50 p-4"
    >
      <div class="bg-white rounded-lg p-6 max-w-md w-full shadow-xl">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-medium text-gray-900">
            Редактировать правило доступа
          </h3>
          <button
            type="button"
            class="text-gray-400 hover:text-gray-600 p-1 rounded-md"
            @click="cancelEdit"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form class="space-y-4" @submit.prevent="handleSaveRule">
          <div class="rounded-md bg-gray-50 p-3 text-sm space-y-1.5 border border-gray-200">
            <div class="flex justify-between">
              <span class="text-gray-500">Склад:</span>
              <span class="font-medium text-gray-900 text-right">{{ ruleToEdit.warehouse_name }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-gray-500">Кому выдан доступ:</span>
              <span class="font-medium text-gray-900 text-right">{{ ruleToEdit.target_name }}</span>
            </div>
            <div v-if="ruleToEdit.owner_company_name" class="flex justify-between">
              <span class="text-gray-500">Владелец склада:</span>
              <span class="font-medium text-gray-900 text-right">{{ ruleToEdit.owner_company_name }}</span>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Тип доступа <span class="text-red-500">*</span>
            </label>
            <select
              v-model="editForm.warehouse_access_type"
              class="select-field"
              required
            >
              <option v-if="authStore.isCarCraftEmployee" value="A">
                A — Собственный
              </option>
              <option value="B">
                В – разрешена работа с заявками
              </option>
              <option value="C">
                С – работа с заявками недоступна
              </option>
            </select>
          </div>

          <div class="flex items-center pt-1">
            <input
              id="edit-rule-active"
              v-model="editForm.is_active"
              type="checkbox"
              class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label for="edit-rule-active" class="ml-2 block text-sm font-medium text-gray-900 cursor-pointer">
              Правило активно
            </label>
          </div>

          <div v-if="editError" class="p-3 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-sm text-red-600">{{ editError }}</p>
          </div>

          <div class="flex justify-end space-x-3 pt-3 border-t border-gray-200">
            <button
              type="button"
              class="btn-secondary"
              :disabled="savingEdit"
              @click="cancelEdit"
            >
              Отмена
            </button>
            <button
              type="submit"
              class="btn-primary"
              :disabled="savingEdit"
            >
              <span v-if="savingEdit">Сохранение...</span>
              <span v-else>Сохранить</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PencilIcon, TrashIcon } from '@heroicons/vue/24/outline'
import type { Warehouse, WarehouseAccessRule, WarehouseAccessType } from '../types'
import { createWarehousesAdminApi } from '../api/warehousesAdminApi'
import { useAuthStore } from '~/features/auth/store/auth'

const props = withDefaults(
  defineProps<{
    warehouseId?: string
    canManage?: boolean
  }>(),
  {
    warehouseId: '',
    canManage: true
  }
)

const config = useRuntimeConfig()
const authStore = useAuthStore()
const api = createWarehousesAdminApi(config)

const rules = ref<WarehouseAccessRule[]>([])
const warehouses = ref<Warehouse[]>([])
const loading = ref(false)
const errorMessage = ref('')
const updatingRuleId = ref<string | null>(null)

const showDeleteConfirm = ref(false)
const ruleToDelete = ref<WarehouseAccessRule | null>(null)
const deleting = ref(false)

const showEditModal = ref(false)
const ruleToEdit = ref<WarehouseAccessRule | null>(null)
const editForm = ref<{ warehouse_access_type: WarehouseAccessType; is_active: boolean }>({
  warehouse_access_type: 'B',
  is_active: true
})
const savingEdit = ref(false)
const editError = ref('')

const filters = ref({
  warehouse_id: props.warehouseId || '',
  is_active: ''
})

const pagination = ref({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

const fetchWarehouses = async () => {
  try {
    const res = await api.getMyWarehouses()
    warehouses.value = res.warehouses || []
  } catch (err) {
    console.error('Error fetching warehouses for filter:', err)
  }
}

const fetchRules = async () => {
  loading.value = true
  errorMessage.value = ''

  try {
    const params = {
      page: pagination.value.page,
      limit: pagination.value.limit,
      warehouse_id: filters.value.warehouse_id || undefined,
      is_active: filters.value.is_active !== '' ? filters.value.is_active === 'true' : undefined
    }

    const res = await api.getAccessRules(params)
    rules.value = res.rules || []
    if (res.pagination) {
      pagination.value = res.pagination
    }
  } catch (err: unknown) {
    console.error('Error fetching access rules:', err)
    errorMessage.value = 'Не удалось загрузить правила доступа. Пожалуйста, повторите попытку.'
  } finally {
    loading.value = false
  }
}

const handleFilterChange = () => {
  pagination.value.page = 1
  fetchRules()
}

const resetFilters = () => {
  filters.value.warehouse_id = props.warehouseId || ''
  filters.value.is_active = ''
  pagination.value.page = 1
  fetchRules()
}

const changePage = (newPage: number) => {
  pagination.value.page = newPage
  fetchRules()
}

const toggleActive = async (rule: WarehouseAccessRule) => {
  if (updatingRuleId.value || !props.canManage) return
  if (rule.warehouse_access_type === 'A' && !authStore.isCarCraftEmployee) return
  updatingRuleId.value = rule.id

  const nextStatus = !rule.is_active
  try {
    await api.updateAccessRule(rule.id, { is_active: nextStatus })
    rule.is_active = nextStatus
  } catch (err: unknown) {
    console.error('Error updating access rule:', err)
    errorMessage.value = 'Ошибка при изменении статуса активности правила.'
  } finally {
    updatingRuleId.value = null
  }
}

const openEditModal = (rule: WarehouseAccessRule) => {
  ruleToEdit.value = rule
  editForm.value = {
    warehouse_access_type: rule.warehouse_access_type,
    is_active: rule.is_active
  }
  editError.value = ''
  showEditModal.value = true
}

const cancelEdit = () => {
  showEditModal.value = false
  ruleToEdit.value = null
  editError.value = ''
}

const handleSaveRule = async () => {
  if (!ruleToEdit.value) return
  savingEdit.value = true
  editError.value = ''

  try {
    await api.updateAccessRule(ruleToEdit.value.id, {
      warehouse_access_type: editForm.value.warehouse_access_type,
      is_active: editForm.value.is_active
    })
    showEditModal.value = false
    ruleToEdit.value = null
    fetchRules()
  } catch (err: unknown) {
    console.error('Error saving access rule:', err)
    const e = err as { data?: { detail?: string; error?: string; message?: string } }
    editError.value = e.data?.detail || e.data?.error || e.data?.message || 'Ошибка при сохранении правила доступа.'
  } finally {
    savingEdit.value = false
  }
}

const confirmDelete = (rule: WarehouseAccessRule) => {
  ruleToDelete.value = rule
  showDeleteConfirm.value = true
}

const cancelDelete = () => {
  showDeleteConfirm.value = false
  ruleToDelete.value = null
}

const handleDeleteRule = async () => {
  if (!ruleToDelete.value) return
  deleting.value = true

  try {
    await api.deleteAccessRule(ruleToDelete.value.id)
    showDeleteConfirm.value = false
    ruleToDelete.value = null
    fetchRules()
  } catch (err: unknown) {
    console.error('Error deleting access rule:', err)
    errorMessage.value = 'Ошибка при удалении правила доступа.'
  } finally {
    deleting.value = false
  }
}

const formatDate = (dateString?: string | null) => {
  if (!dateString) return '—'
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return dateString
  return date.toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  })
}

watch(
  () => props.warehouseId,
  newId => {
    if (newId !== undefined) {
      filters.value.warehouse_id = newId
      fetchRules()
    }
  }
)

onMounted(() => {
  fetchWarehouses()
  fetchRules()
})

defineExpose({
  fetchRules,
  refresh: fetchRules
})
</script>
