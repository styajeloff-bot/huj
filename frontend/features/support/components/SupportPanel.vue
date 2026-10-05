<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">{{ title }}</h2>
      <button v-if="!readonly" @click="openCreateProgram" class="btn-primary">
        {{ createButtonLabel }}
      </button>
    </div>

    <div
      v-if="actionMessage"
      class="mb-4 rounded-lg border px-4 py-3 text-sm"
      :class="actionMessage.kind === 'warning'
        ? 'border-yellow-200 bg-yellow-50 text-yellow-800'
        : 'border-green-200 bg-green-50 text-green-800'"
    >
      {{ actionMessage.text }}
    </div>

    <div
      v-if="deepLinkUnavailable"
      class="mb-4 rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
      role="status"
    >
      Поддержка больше недоступна или не связана с вашей организацией.
    </div>

    <!-- Filters -->
    <div class="bg-white p-4 rounded-lg border border-gray-200 mb-6">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Универсальный поиск</label>
          <input
            v-model="filters.search"
            type="text"
            placeholder="Название, VIN, марка"
            class="input-field"
            @input="debouncedSearch"
          >
        </div>
        <div>
          <SearchableDropdown
            v-model="filters.mark_id"
            label="Марка"
            placeholder="Все марки"
            :items="markOptions"
            label-key="display_name"
            value-key="id"
            search-placeholder="Найти марку..."
            @update:modelValue="handleMarkFilterChange"
          />
        </div>
        <div>
          <SearchableDropdown
            v-model="filters.model_id"
            label="Модель"
            placeholder="Все модели"
            :items="modelOptions"
            label-key="display_name"
            value-key="id"
            search-placeholder="Найти модель..."
            :disabled="!filters.mark_id"
            @update:modelValue="fetchPrograms"
          />
        </div>

        <!-- Admin-only filters -->
        <template v-if="!readonly">
          <div>
            <SearchableDropdown
              v-model="filters.dealer_group_id"
              label="Группа дилеров"
              placeholder="Все группы"
              :items="dealerGroups"
              label-key="name"
              value-key="id"
              search-placeholder="Найти группу..."
              @update:modelValue="fetchPrograms"
            />
          </div>
          <div>
            <SearchableDropdown
              v-model="filters.distributor_id"
              label="Дистрибьютор"
              placeholder="Все дистрибьюторы"
              :items="distributors"
              label-key="name"
              value-key="id"
              search-placeholder="Найти дистрибьютора..."
              @update:modelValue="fetchPrograms"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Показать как</label>
            <select v-model="filters.view_as" class="select-field" @change="fetchPrograms">
              <option value="">Все программы</option>
              <option value="distributor">Для дистрибьютора</option>
              <option value="leasing_company">Для лизинговой</option>
              <option value="client">Для клиента</option>
            </select>
          </div>
        </template>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Статус</label>
          <select v-model="filters.status" class="select-field" @change="fetchPrograms">
            <option value="">Все статусы</option>
            <option value="true">Активные</option>
            <option value="false">Неактивные</option>
            <template v-if="!readonly">
              <option value="active_in_period">Активна в периоде</option>
              <option value="inactive_in_period">Неактивна в периоде</option>
            </template>
          </select>
        </div>

        <template v-if="!readonly && (filters.status === 'active_in_period' || filters.status === 'inactive_in_period')">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Период с</label>
            <input v-model="filters.period_starts_at" type="date" class="input-field" @change="fetchPrograms" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Период по</label>
            <input v-model="filters.period_ends_at" type="date" class="input-field" @change="fetchPrograms" />
          </div>
        </template>

        <div v-if="!readonly">
          <SearchableDropdown
            v-model="visibleColumns"
            label="Колонки таблицы"
            placeholder="Выберите колонки"
            :items="columnOptions"
            label-key="label"
            value-key="id"
            search-placeholder="Найти колонку..."
            multiple
            @update:modelValue="saveVisibleColumns"
          />
        </div>
      </div>
    </div>

    <!-- Programs table -->
    <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div v-if="loading" class="text-center py-8">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p class="mt-2 text-gray-600">{{ loadingText }}</p>
      </div>

      <div v-else-if="error" class="text-center py-8">
        <p class="text-red-600 mb-4">{{ error }}</p>
        <button @click="fetchPrograms" class="btn-primary">Попробовать снова</button>
      </div>

      <div v-else-if="supportPrograms.length === 0" class="text-center py-8">
        <svg class="mx-auto h-12 w-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
        </svg>
        <p class="text-gray-600">{{ emptyText }}</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th v-if="col('program')" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Программа</th>
              <th v-if="col('application')" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Применение</th>
              <th v-if="col('support')" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Поддержка</th>
              <th v-if="col('period')" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Срок</th>
              <th v-if="col('leasing')" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ЛК</th>
              <th v-if="col('visibility') && !readonly" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Видимость</th>
              <th v-if="col('status')" class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Статус</th>
              <th v-if="col('actions') && !readonly" class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Действия</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr
              v-for="program in supportPrograms"
              :key="program.id"
              class="hover:bg-gray-50 transition-colors"
              :class="{
                'cursor-pointer hover:bg-blue-50': readonly,
                'bg-blue-50 ring-1 ring-inset ring-blue-200': selectedDeepLinkProgramId === program.id,
              }"
              @click="readonly ? openView(program) : undefined"
            >
              <td v-if="col('program')" class="px-6 py-4">
                <div class="text-sm font-medium text-gray-900">{{ program.name }}</div>
                <div class="text-xs text-gray-500">{{ getSupportTypeLabel(program.support_type) }}</div>
                <div v-if="program.comment" class="text-xs text-gray-400 mt-1 max-w-xs truncate" :title="program.comment">{{ program.comment }}</div>
              </td>
              <td v-if="col('application')" class="px-6 py-4 text-sm text-gray-700">
                <div>{{ program.mark_name || '—' }}</div>
                <div v-if="program.model_name" class="text-xs text-gray-500">{{ program.model_name }}</div>
                <div v-if="program.vins?.length" class="text-xs text-gray-500">VIN: {{ program.vins.join(', ') }}</div>
                <div v-else-if="program.vin" class="text-xs text-gray-500">VIN: {{ program.vin }}</div>
                <div v-if="program.dealer_groups?.length" class="text-xs text-gray-500">Группы: {{ program.dealer_groups.map((g) => g.name).join(', ') }}</div>
                <div v-else-if="program.dealer_group_name" class="text-xs text-gray-500">Группа: {{ program.dealer_group_name }}</div>
                <div v-if="!readonly && program.distributor_name" class="text-xs text-gray-500">Дистрибьютор: {{ program.distributor_name }}</div>
              </td>
              <td v-if="col('support')" class="px-6 py-4 text-sm text-gray-700">
                {{ formatSupportValue(program) }}
              </td>
              <td v-if="col('period')" class="px-6 py-4 text-sm text-gray-700">
                {{ formatProgramDates(program) }}
              </td>
              <td v-if="col('leasing')" class="px-6 py-4 text-sm text-gray-700">
                <span v-if="program.leasing_companies?.length">
                  {{ program.leasing_companies.map((c) => c.name).join(', ') }}
                </span>
                <span v-else class="text-gray-400">Любые</span>
              </td>
              <td v-if="col('visibility') && !readonly" class="px-6 py-4 text-sm">
                <span v-if="program.show_to_leasing_company !== false" class="inline-flex px-1.5 py-0.5 text-xs rounded bg-blue-100 text-blue-700 mr-1" title="Лизинговой">ЛК</span>
                <span v-if="program.show_to_client !== false" class="inline-flex px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-700" title="Клиенту">Клиент</span>
                <span v-if="program.show_to_leasing_company === false && program.show_to_client === false" class="text-gray-400 text-xs">—</span>
              </td>
              <td v-if="col('status')" class="px-6 py-4">
                <span
                  class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                  :class="supportStatusClass(program)"
                >
                  {{ supportStatusLabel(program) }}
                </span>
              </td>
              <td v-if="col('actions') && !readonly" class="px-6 py-4 text-right text-sm font-medium space-x-2">
                <button @click.stop="openView(program)" class="text-gray-500 hover:text-gray-800">Просмотр</button>
                <button @click.stop="openEdit(program)" class="text-blue-600 hover:text-blue-900">Редактировать</button>
                <button @click.stop="openClone(program)" class="text-gray-600 hover:text-gray-900">Дублировать</button>
                <button
                  @click.stop="openToggleActive(program)"
                  :class="program.is_active ? 'text-red-600 hover:text-red-900' : 'text-green-600 hover:text-green-900'"
                >
                  {{ program.is_active ? 'Деактивировать' : 'Активировать' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="pagination.pages > 1" class="bg-gray-50 px-6 py-3 border-t">
        <div class="flex items-center justify-between">
          <div class="text-sm text-gray-500">
            Показаны {{ (pagination.page - 1) * pagination.limit + 1 }}–{{ Math.min(pagination.page * pagination.limit, pagination.total) }} из {{ pagination.total }}
          </div>
          <div class="flex space-x-2">
            <button @click="changePage(pagination.page - 1)" :disabled="pagination.page <= 1" class="btn-secondary disabled:opacity-50">
              Предыдущая
            </button>
            <button @click="changePage(pagination.page + 1)" :disabled="pagination.page >= pagination.pages" class="btn-secondary disabled:opacity-50">
              Следующая
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- View modal (shared) -->
    <SupportViewModal
      v-if="viewSupportProgram !== null"
      :show="showViewModal"
      :program="viewSupportProgram"
      @close="showViewModal = false"
    />

    <!-- Create/Edit modal (admin only) -->
    <SupportAdminCreateModal
      v-if="!readonly && showEditModal"
      :show="showEditModal"
      :program="editSupportProgram"
      :clone-mode="cloneMode"
      @close="closeEditModal"
      @success="handleEditSuccess"
    />

    <!-- Toggle active status confirmation modal (admin only) -->
    <div
      v-if="!readonly && showToggleModal && toggleSupportProgram"
      class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4"
      @click.self="cancelToggleActive"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">
          {{ toggleSupportProgram.is_active ? 'Деактивировать поддержку' : 'Активировать поддержку' }}
        </h3>
        <p class="text-sm text-gray-700 mb-2">
          Вы уверены, что хотите
          <span class="font-semibold">{{ toggleSupportProgram.is_active ? 'деактивировать' : 'активировать' }}</span>
          поддержку <span class="font-semibold">«{{ toggleSupportProgram.name }}»</span>?
        </p>
        <p class="text-xs text-gray-500 mb-4">
          Изменение статуса нельзя будет отменить.
        </p>
        <div v-if="toggleError" class="mb-4 p-2 rounded border border-red-200 bg-red-50 text-xs text-red-600">
          {{ toggleError }}
        </div>
        <div class="flex justify-end space-x-3">
          <button type="button" class="btn-secondary" :disabled="toggleLoading" @click="cancelToggleActive">
            Отмена
          </button>
          <button
            type="button"
            :class="toggleSupportProgram.is_active ? 'btn-danger' : 'btn-primary'"
            :disabled="toggleLoading"
            @click="confirmToggleActive"
          >
            <span v-if="toggleLoading">Обновление...</span>
            <span v-else>
              {{ toggleSupportProgram.is_active ? 'Деактивировать' : 'Активировать' }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { SupportProgram, Pagination, VehicleMark, VehicleModel, SupportDealerGroup } from '~/types/admin'
import SupportViewModal from './SupportViewModal.vue'
import SupportAdminCreateModal from '~/features/admin/support/create/components/SupportAdminCreateModal.vue'
import { createSupportAdminApi } from '~/features/admin/support/api/supportAdminApi'
import { createCompensationApi } from '~/features/compensations/api/compensationApi'
import { clearLegacy, useScopedStorage } from '~/features/auth/composables/useScopedStorage'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useLodash } from '~/composables/useLodash'
import {
  findSupportProgramAcrossPages,
  resolveSupportProgramDeepLink,
  type SupportDeepLinkTarget,
  type SupportProgramPage,
} from '~/utils/supportDeepLink'
import { formatSupportProgramPricing } from '~/utils/supportProgramPresentation'

interface DistributorItem {
  id: string
  name: string
}

const props = defineProps({
  readonly: {
    type: Boolean,
    default: false
  },
  /** Override fetch function for non-admin contexts (e.g. distributor) */
  fetchFn: {
    type: Function as PropType<(params: Record<string, string>) => Promise<SupportProgramPage>>,
    default: null
  },
  deepLinkTarget: {
    type: Object as PropType<SupportDeepLinkTarget | null>,
    default: null,
  },
  title: {
    type: String,
    default: 'Поддержки'
  },
  createButtonLabel: {
    type: String,
    default: 'Создать поддержку'
  },
  loadingText: {
    type: String,
    default: 'Загружаем поддержку...'
  },
  emptyText: {
    type: String,
    default: 'Программы поддержки не найдены'
  }
})

const config = useRuntimeConfig()
const adminApi = createSupportAdminApi(config)
const compensationApi = createCompensationApi(config)
const { debounce } = useLodash()

const supportPrograms = ref<SupportProgram[]>([])
const loading = ref(true)
const error = ref('')
const actionMessage = ref<{ kind: 'success' | 'warning'; text: string } | null>(null)
const deepLinkUnavailable = ref(false)
const deepLinkHandled = ref(false)
const selectedDeepLinkProgramId = ref<string | null>(null)

const dealerGroups = ref<SupportDealerGroup[]>([])
const distributors = ref<DistributorItem[]>([])
const marks = ref<VehicleMark[]>([])
const models = ref<VehicleModel[]>([])

const filters = ref<{
  search: string
  mark_id: string | null
  model_id: string | null
  dealer_group_id: string | null
  distributor_id: string | null
  view_as: string
  status: string
  period_starts_at: string
  period_ends_at: string
}>({
  search: '',
  mark_id: null,
  model_id: null,
  dealer_group_id: null,
  distributor_id: null,
  view_as: '',
  status: '',
  period_starts_at: '',
  period_ends_at: ''
})

const pagination = ref<Pagination>({ page: 1, limit: 20, total: 0, pages: 0 })

// View modal
const showViewModal = ref(false)
const viewSupportProgram = ref<SupportProgram | null>(null)

// Edit modal (admin)
const showEditModal = ref(false)
const editSupportProgram = ref<SupportProgram | null>(null)
const cloneMode = ref(false)

// Toggle active status modal (admin)
const showToggleModal = ref(false)
const toggleSupportProgram = ref<SupportProgram | null>(null)
const toggleLoading = ref(false)
const toggleError = ref('')

// Column visibility (admin only)
const COLUMNS_KEY = 'support-admin-visible-columns'
const ALL_COLS = ['program', 'application', 'support', 'period', 'leasing', 'visibility', 'status', 'actions']

const columnOptions = [
  { id: 'program', label: 'Программа' },
  { id: 'application', label: 'Применение' },
  { id: 'support', label: 'Поддержка' },
  { id: 'period', label: 'Срок' },
  { id: 'leasing', label: 'ЛК' },
  { id: 'visibility', label: 'Видимость' },
  { id: 'status', label: 'Статус' },
  { id: 'actions', label: 'Действия' }
]

const columnsStorage = useScopedStorage<string[]>(COLUMNS_KEY)
clearLegacy(COLUMNS_KEY)

function loadVisibleColumns() {
  if (process.client) {
    const saved = columnsStorage.get()
    if (Array.isArray(saved) && saved.length > 0) {
      return saved.filter((id) => ALL_COLS.includes(id))
    }
  }
  return [...ALL_COLS]
}

function saveVisibleColumns() {
  if (process.client) {
    const cols = Array.isArray(visibleColumns.value) && visibleColumns.value.length > 0
      ? visibleColumns.value
      : [...ALL_COLS]
    if (cols.length !== visibleColumns.value.length) visibleColumns.value = cols
    columnsStorage.set(cols)
  }
}

const visibleColumns = ref(loadVisibleColumns())

// In readonly mode all columns visible (except admin-only ones handled in template)
const READONLY_COLS = ['program', 'support', 'period', 'leasing', 'status']

const col = (id: string) => props.readonly ? READONLY_COLS.includes(id) : visibleColumns.value.includes(id)

const markOptions = computed(() => marks.value.map((m) => ({ ...m, display_name: m.name || m.cyrillic_name })))
const modelOptions = computed(() => models.value.map((m) => ({ ...m, display_name: m.name || m.cyrillic_name })))

const revealDeepLinkedProgram = (programs: SupportProgram[]) => {
  if (deepLinkHandled.value || !props.deepLinkTarget) return
  deepLinkHandled.value = true
  const program = resolveSupportProgramDeepLink(programs, props.deepLinkTarget)
  if (!program) {
    deepLinkUnavailable.value = true
    return
  }
  selectedDeepLinkProgramId.value = program.id
  viewSupportProgram.value = program
  showViewModal.value = true
}

let fetchProgramsRequestId = 0
const fetchPrograms = async () => {
  const requestId = ++fetchProgramsRequestId
  loading.value = true
  error.value = ''
  try {
    const params: Record<string, string> = {
      page: pagination.value.page.toString(),
      limit: pagination.value.limit.toString()
    }
    if (filters.value.search) params.search = filters.value.search
    if (!params.search && props.deepLinkTarget && !props.deepLinkTarget.id && props.deepLinkTarget.name) {
      params.search = props.deepLinkTarget.name
    }
    if (filters.value.mark_id) params.mark_id = filters.value.mark_id
    if (filters.value.model_id) params.model_id = filters.value.model_id
    if (!props.readonly) {
      if (filters.value.dealer_group_id) params.dealer_group_id = filters.value.dealer_group_id.toString()
      if (filters.value.distributor_id) params.distributor_id = filters.value.distributor_id.toString()
      if (filters.value.view_as) params.view_as = filters.value.view_as
      if (filters.value.period_starts_at) params.period_starts_at = filters.value.period_starts_at
      if (filters.value.period_ends_at) params.period_ends_at = filters.value.period_ends_at
    }
    if (filters.value.status) params.status = filters.value.status

    const requestPrograms = async (
      requestParams: Record<string, string>,
    ): Promise<SupportProgramPage> => {
      if (props.fetchFn) {
        return await props.fetchFn(requestParams) as SupportProgramPage
      }
      return await adminApi.getSupportPrograms(requestParams)
    }
    const response = await requestPrograms(params)
    if (requestId !== fetchProgramsRequestId) return

    const deepLinkedProgram = props.deepLinkTarget && !deepLinkHandled.value
      ? await findSupportProgramAcrossPages(
          response,
          props.deepLinkTarget,
          page => requestPrograms({ ...params, page: String(page) }),
        )
      : null
    if (requestId !== fetchProgramsRequestId) return
    supportPrograms.value = response.items
    pagination.value = response.pagination
    if (props.deepLinkTarget && !deepLinkHandled.value) {
      revealDeepLinkedProgram(deepLinkedProgram ? [deepLinkedProgram] : [])
    }
  } catch (err: unknown) {
    if (requestId !== fetchProgramsRequestId) return
    const e = err as { data?: { error?: string } }
    error.value = e?.data?.error || 'Ошибка при загрузке поддержки'
  } finally {
    if (requestId === fetchProgramsRequestId) loading.value = false
  }
}

const debouncedSearch = debounce(() => {
  pagination.value.page = 1
  fetchPrograms()
}, 500)

const handleMarkFilterChange = async () => {
  filters.value.model_id = null
  if (filters.value.mark_id) {
    try { models.value = await adminApi.getModels(filters.value.mark_id) } catch { models.value = [] }
  } else {
    models.value = []
  }
  fetchPrograms()
}

const changePage = (page: number) => {
  pagination.value.page = page
  fetchPrograms()
}

const openView = (program: SupportProgram) => {
  viewSupportProgram.value = program
  showViewModal.value = true
}

watch(() => props.deepLinkTarget, () => {
  deepLinkHandled.value = false
  deepLinkUnavailable.value = false
  selectedDeepLinkProgramId.value = null
  viewSupportProgram.value = null
  showViewModal.value = false
  fetchPrograms()
}, { deep: true })

const openCreateProgram = () => {
  editSupportProgram.value = null
  cloneMode.value = false
  showEditModal.value = true
}

const openEdit = async (program: SupportProgram) => {
  cloneMode.value = false
  try {
    const response = await adminApi.getSupportProgramById(program.id)
    editSupportProgram.value = response.support_program
  } catch {
    editSupportProgram.value = program
  }
  showEditModal.value = true
}

const openClone = async (program: SupportProgram) => {
  cloneMode.value = true
  try {
    const response = await adminApi.getSupportProgramById(program.id)
    const prog = response.support_program
    editSupportProgram.value = prog ? { ...prog, id: undefined as unknown as string, name: (prog.name || '').trim() + ' (копия)' } : program
  } catch {
    editSupportProgram.value = program ? { ...program, id: undefined as unknown as string, name: (program.name || '').trim() + ' (копия)' } : null
  }
  showEditModal.value = true
}

const openToggleActive = (program: SupportProgram) => {
  toggleSupportProgram.value = program
  toggleError.value = ''
  showToggleModal.value = true
}

const cancelToggleActive = () => {
  if (toggleLoading.value) return
  showToggleModal.value = false
  toggleSupportProgram.value = null
  toggleError.value = ''
}

const confirmToggleActive = async () => {
  if (!toggleSupportProgram.value || toggleLoading.value) return
  toggleLoading.value = true
  toggleError.value = ''
  actionMessage.value = null
  try {
    const program = toggleSupportProgram.value
    if (toggleSupportProgram.value.is_active) {
      await adminApi.deactivateSupportProgram(program.id)
      try {
        const cancellation = await compensationApi.cancelForSupport(program.id)
        if (cancellation.already_paid_count > 0) {
          actionMessage.value = {
            kind: 'warning',
            text: `Поддержка «${program.name}» деактивирована. Неоплаченные компенсации отменены автоматически, а ${cancellation.already_paid_count} оплаченных требуют ручной обработки.`
          }
        } else if (cancellation.cancelled_count > 0) {
          actionMessage.value = {
            kind: 'success',
            text: `Поддержка «${program.name}» деактивирована. Автоматически отменено компенсаций: ${cancellation.cancelled_count}.`
          }
        } else {
          actionMessage.value = {
            kind: 'success',
            text: `Поддержка «${program.name}» деактивирована. Связанных открытых компенсаций не найдено.`
          }
        }
      } catch {
        actionMessage.value = {
          kind: 'warning',
          text: `Поддержка «${program.name}» деактивирована. Автоотмена компенсаций будет завершена фоновым процессом.`
        }
      }
    } else {
      await adminApi.activateSupportProgram(program.id)
      actionMessage.value = {
        kind: 'success',
        text: `Поддержка «${program.name}» активирована.`
      }
    }
    showToggleModal.value = false
    toggleSupportProgram.value = null
    await fetchPrograms()
  } catch (err: unknown) {
    const e = err as { data?: { error?: string }; message?: string }
    toggleError.value = e?.data?.error || e?.message || 'Не удалось изменить статус поддержки'
  } finally {
    toggleLoading.value = false
  }
}

const closeEditModal = () => {
  showEditModal.value = false
  cloneMode.value = false
  editSupportProgram.value = null
}

const handleEditSuccess = () => {
  closeEditModal()
  fetchPrograms()
}

const getSupportTypeLabel = (type: string) => {
  const labels: Record<string, string> = {
    down_payment_compensation: 'Компенсация первого взноса (компенсация лизинговой)',
    vehicle_discount_dealer_compensation: 'Поддержка на ТС (компенсация дилеру)',
    vehicle_discount_dealer_invoice: 'Поддержка на ТС (уменьшение счета дилеру)',
    leasing_interest_compensation: 'Компенсация процентов по лизингу (компенсация лизинговой)'
  }
  return labels[type] || type
}

const formatSupportValue = (program: SupportProgram) => formatSupportProgramPricing(program)

const formatProgramDates = (program: SupportProgram) => {
  const formatRuDate = (val: string | undefined | null) => {
    if (!val) return '—'
    const raw = String(val)
    const iso = raw.slice(0, 10)
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/)
    if (m) return `${m[3]}.${m[2]}.${m[1]}`

    // For non-ISO inputs (e.g. Date -> "Thu Mar 12 ...") keep full string to parse year.
    const d = new Date(raw)
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
    }
    return iso
  }

  const start = program.starts_at
    ? formatRuDate(program.starts_at)
    : (program.created_at ? formatRuDate(program.created_at) : '—')
  const end = program.ends_at ? formatRuDate(program.ends_at) : 'бессрочно'
  return `${start} → ${end}`
}

const isCompleted = (program: SupportProgram) => {
  if (!program.ends_at) return false
  const end = String(program.ends_at).slice(0, 10)
  return end < new Date().toISOString().slice(0, 10)
}

const supportStatusLabel = (program: SupportProgram) => {
  if (!program.is_active) return 'Неактивна'
  if (program.status === 'completed' || isCompleted(program)) return 'Завершена'
  return 'Активна'
}

const supportStatusClass = (program: SupportProgram) => {
  if (!program.is_active) return 'bg-red-100 text-red-800'
  if (program.status === 'completed' || isCompleted(program)) return 'bg-gray-100 text-gray-800'
  return 'bg-green-100 text-green-800'
}

onMounted(async () => {
  visibleColumns.value = loadVisibleColumns()
  const fetchRefs = [adminApi.getMarks({ specialOffer: 'true' }).then((d) => { marks.value = Array.isArray(d) ? d : [] }).catch(() => {})]
  if (!props.readonly) {
    fetchRefs.push(
      adminApi.getDealerGroups().then((d) => { dealerGroups.value = d.dealer_groups || [] }).catch(() => {}),
      adminApi.getDistributors().then((d) => { distributors.value = d.distributors || [] }).catch(() => {})
    )
  }
  await Promise.all(fetchRefs)
  await fetchPrograms()
})
</script>
