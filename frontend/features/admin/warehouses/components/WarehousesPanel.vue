<template>
  <div>
    <!-- Top Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
      <div>
        <h2 class="text-xl font-semibold text-gray-900">
          Склады и управление доступом
        </h2>
        <p class="text-sm text-gray-500 mt-1">
          Справочник складов ТС и правила доступа дилеров
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <template v-if="activeTab === 'list'">
          <button
            type="button"
            class="btn-secondary text-sm"
            @click="showVehicleTransferModal = true"
          >
            Перемещение ТС
          </button>
          <button
            v-if="canManageWarehouses"
            type="button"
            class="btn-primary text-sm"
            @click="showCreateModal = true"
          >
            Создать склад
          </button>
        </template>
        <template v-else-if="activeTab === 'management'">
          <button
            v-if="canManageWarehouses"
            type="button"
            class="btn-primary text-sm"
            @click="showCreateRuleModal = true"
          >
            Создать правило
          </button>
        </template>
      </div>
    </div>

    <!-- Tab navigation -->
    <div class="border-b border-gray-200 mb-6">
      <nav class="-mb-px flex space-x-8" aria-label="Вкладки">
        <button
          type="button"
          :class="[
            activeTab === 'list'
              ? 'border-blue-500 text-blue-600 font-semibold'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 font-medium',
            'whitespace-nowrap py-3 px-1 border-b-2 text-sm transition-colors cursor-pointer'
          ]"
          @click="activeTab = 'list'"
        >
          Список складов
        </button>
        <button
          type="button"
          :class="[
            activeTab === 'management'
              ? 'border-blue-500 text-blue-600 font-semibold'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 font-medium',
            'whitespace-nowrap py-3 px-1 border-b-2 text-sm transition-colors cursor-pointer'
          ]"
          @click="activeTab = 'management'"
        >
          Управление складами
        </button>
      </nav>
    </div>

    <!-- TAB 1: Список складов -->
    <div v-show="activeTab === 'list'" class="space-y-4">
      <!-- Filters bar -->
      <div class="bg-white rounded-lg border border-gray-200 p-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <!-- Search -->
          <div>
            <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">Поиск</label>
            <input
              v-model="currentFilters.search"
              type="text"
              class="input-field"
              placeholder="По названию или адресу"
              @keyup.enter="applyFilters"
            />
          </div>

          <!-- City -->
          <div>
            <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">Город</label>
            <select v-model="currentFilters.city_id" class="select-field" @change="applyFilters">
              <option value="">Все города</option>
              <option v-for="c in availableCities" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>

          <!-- Mark -->
          <div>
            <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">Марка</label>
            <select v-model="currentFilters.brand_id" class="select-field" @change="applyFilters">
              <option value="">Все марки</option>
              <option v-for="m in availableMarks" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
          </div>

          <!-- Access type -->
          <div>
            <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">Тип склада</label>
            <select v-model="currentFilters.access_type" class="select-field" @change="applyFilters">
              <option value="">Все типы</option>
              <option value="A">A — Собственный</option>
              <option value="B">В – разрешена работа с заявками</option>
              <option value="C">С – работа с заявками недоступна</option>
            </select>
          </div>

          <!-- Owner (for admin) -->
          <div v-if="authStore.isCarCraftEmployee">
            <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">Владелец</label>
            <select v-model="currentFilters.owner_company_id" class="select-field" @change="applyFilters">
              <option value="">Все владельцы</option>
              <option v-for="comp in availableCompanies" :key="comp.id" :value="comp.id">
                {{ comp.name }} ({{ comp.company_type === 'distributor' ? 'Дистрибьютор' : 'Дилер' }})
              </option>
            </select>
          </div>
        </div>

        <div class="mt-3 flex justify-end gap-2">
          <button type="button" class="btn-secondary text-sm" @click="resetFilters">
            Сбросить
          </button>
          <button type="button" class="btn-primary text-sm" @click="applyFilters">
            Применить
          </button>
        </div>
      </div>

      <!-- Error State -->
      <div
        v-if="warehouseLoadError"
        class="flex items-start justify-between gap-6 rounded-lg border border-red-200 bg-red-50 p-5"
        role="alert"
      >
        <div>
          <p class="text-sm font-semibold text-red-800">Не удалось загрузить склады</p>
          <p class="mt-1 text-sm leading-relaxed text-red-700">{{ warehouseLoadError }}</p>
        </div>
        <button
          type="button"
          class="btn-secondary shrink-0"
          @click="fetchWarehouses"
        >
          Повторить загрузку
        </button>
      </div>

      <!-- Table -->
      <DataTable
        v-else
        :data="warehouses"
        :columns="columns"
        :loading="loading"
        :actions="actions"
        :server-side="true"
        :total-items="pagination.total"
        :current-server-page="pagination.page"
        :total-server-pages="pagination.pages"
        :page-size="pagination.limit"
        :searchable="false"
        :show-header="false"
        empty-message="Склады не найдены"
        @action="handleAction"
        @refresh="fetchWarehouses"
        @page-change="changePage"
      >
        <!-- Кастомная колонка: Марка -->
        <template #column-brand="{ item }">
          <span
            v-if="warehouseBrandDisplay(asWarehouse(item))"
            class="inline-flex px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-100 text-blue-800"
          >
            {{ warehouseBrandDisplay(asWarehouse(item)) }}
          </span>
          <span v-else class="text-sm text-gray-400">—</span>
        </template>

        <!-- Кастомная колонка: Город -->
        <template #column-city_name="{ item }">
          <span v-if="asWarehouse(item).city_name" class="text-sm text-gray-900">{{ asWarehouse(item).city_name }}</span>
          <span v-else class="text-sm text-gray-400">—</span>
        </template>

        <!-- Кастомная колонка: Адрес -->
        <template #column-address="{ item }">
          <div class="flex flex-col">
            <span class="font-medium text-gray-900">{{ asWarehouse(item).name || asWarehouse(item).address }}</span>
            <WarehouseAddressTooltip :warehouse-id="asWarehouse(item).id" :address="asWarehouse(item).address" />
          </div>
        </template>

        <!-- Кастомная колонка: Владелец -->
        <template #column-owner="{ item }">
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="text-sm text-gray-900">
              {{ asWarehouse(item).owner_company_name || asWarehouse(item).company_name || '—' }}
            </span>
            <span
              v-if="asWarehouse(item).owner_company_type"
              :class="asWarehouse(item).owner_company_type === 'distributor' ? 'bg-indigo-100 text-indigo-800' : 'bg-purple-100 text-purple-800'"
              class="inline-flex px-1.5 py-0.5 text-xs font-medium rounded"
            >
              {{ asWarehouse(item).owner_company_type === 'distributor' ? 'Дистрибьютор' : 'Дилер' }}
            </span>
          </div>
        </template>

        <!-- Кастомная колонка: Группы дилеров -->
        <template #column-groups="{ item }">
          <div v-if="asWarehouse(item).groups && asWarehouse(item).groups.length > 0" class="flex flex-wrap gap-1">
            <span
              v-for="group in asWarehouse(item).groups"
              :key="group"
              class="inline-flex px-2 py-0.5 text-xs font-medium rounded bg-gray-100 text-gray-700"
            >
              {{ group }}
            </span>
          </div>
          <span v-else class="text-sm text-gray-400">—</span>
        </template>

        <!-- Кастомная колонка: Количество ТС -->
        <template #column-vehicles_count="{ item }">
          <button
            type="button"
            class="inline-flex items-center px-2.5 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800 hover:bg-green-200 transition-colors cursor-pointer"
            title="Посмотреть ТС на складе"
            @click.stop="openWarehouseVehicles(asWarehouse(item))"
          >
            {{ asWarehouse(item).vehicles_count ?? 0 }} ТС
          </button>
        </template>

        <!-- Кастомная колонка: Тип склада -->
        <template #column-warehouse_access_type="{ item }">
          <span
            v-if="asWarehouse(item).warehouse_access_type === 'A'"
            class="inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800"
          >
            {{ authStore.isCarCraftEmployee ? 'A (Админ)' : 'A — Собственный' }}
          </span>
          <span
            v-else-if="asWarehouse(item).warehouse_access_type === 'B'"
            class="inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full bg-blue-100 text-blue-800"
          >
            В – разрешена работа с заявками
          </span>
          <span
            v-else-if="asWarehouse(item).warehouse_access_type === 'C'"
            class="inline-flex items-center px-2 py-1 text-xs font-semibold rounded-full bg-amber-100 text-amber-800"
          >
            С – работа с заявками недоступна
          </span>
          <span v-else class="text-xs text-gray-400">—</span>
        </template>

        <!-- Кастомная колонка: Тип ТС -->
        <template #column-vehicle_types="{ item }">
          <span v-if="formatVehicleTypes(asWarehouse(item).vehicle_types)" class="text-sm text-gray-900">
            {{ formatVehicleTypes(asWarehouse(item).vehicle_types) }}
          </span>
          <span v-else class="text-sm text-gray-400">—</span>
        </template>

        <!-- Кастомная колонка: Сайт -->
        <template #column-sites="{ item }">
          <div v-if="asWarehouse(item).sites && asWarehouse(item).sites.length > 0" class="flex flex-wrap gap-1">
            <span
              v-for="site in asWarehouse(item).sites"
              :key="site"
              class="inline-flex px-1.5 py-0.5 text-xs font-medium rounded bg-purple-50 text-purple-700"
            >
              {{ site }}
            </span>
          </div>
          <span v-else class="text-sm text-gray-400">—</span>
        </template>
      </DataTable>
    </div>

    <!-- TAB 2: Управление складами (правила доступа) -->
    <div v-show="activeTab === 'management'">
      <WarehouseAccessRulesTable
        ref="rulesTableRef"
        :can-manage="canManageWarehouses"
      />
    </div>

    <!-- Модальные окна -->
    <WarehouseFormModal
      v-if="canManageWarehouses && showCreateModal"
      @close="showCreateModal = false"
      @success="handleSuccess"
    />

    <WarehouseFormModal
      v-if="canManageWarehouses && showEditModal && selectedWarehouse"
      :warehouse="selectedWarehouseNonNull"
      @close="showEditModal = false"
      @success="handleSuccess"
    />

    <WarehouseVehiclesModal
      v-if="showWarehouseVehiclesModal && selectedWarehouse"
      :warehouse="selectedWarehouseNonNull"
      :read-only="!canManageWarehouses"
      @close="showWarehouseVehiclesModal = false"
      @success="handleSuccess"
      @changed="fetchWarehouses"
    />

    <VehicleTransferModal
      v-if="showVehicleTransferModal"
      @close="showVehicleTransferModal = false"
      @success="handleSuccess"
    />

    <WarehouseAccessRuleCreateModal
      v-if="canManageWarehouses && showCreateRuleModal"
      @close="showCreateRuleModal = false"
      @success="handleRuleCreated"
    />

    <!-- Модальное окно каскадного удаления склада -->
    <WarehouseCascadeDeleteModal
      v-if="showCascadeDeleteModal && warehouseToDelete"
      :warehouse="warehouseToDelete"
      @close="closeCascadeDeleteModal"
      @success="handleCascadeDeleteSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { PencilIcon, TrashIcon, ArrowsRightLeftIcon } from '@heroicons/vue/24/outline'
import WarehouseVehiclesModal from '~/features/admin/vehicles/components/WarehouseVehiclesModal.vue'
import WarehouseFormModal from '~/features/admin/warehouses/components/WarehouseFormModal.vue'
import WarehouseCascadeDeleteModal from '~/features/admin/warehouses/components/WarehouseCascadeDeleteModal.vue'
import VehicleTransferModal from '~/features/admin/warehouses/components/VehicleTransferModal.vue'
import WarehouseAddressTooltip from '~/features/admin/warehouses/components/WarehouseAddressTooltip.vue'
import WarehouseAccessRulesTable from '~/features/admin/warehouses/components/WarehouseAccessRulesTable.vue'
import WarehouseAccessRuleCreateModal from '~/features/admin/warehouses/components/WarehouseAccessRuleCreateModal.vue'
import DataTable from '~/components/ui/DataTable.vue'
import type { Warehouse, WarehouseMark } from '../types'
import type { City, Company } from '~/types/features'
import { createWarehousesApi } from '../api/warehousesApi'
import { useAuthStore } from '~/features/auth/store/auth'

const config = useRuntimeConfig()
const authStore = useAuthStore()
const api = createWarehousesApi(config)

const canManageWarehouses = computed(() =>
  authStore.hasScope('warehouses:admin') ||
  authStore.isCarCraftEmployee ||
  authStore.isDistributor ||
  authStore.isDealer
)

const activeTab = ref<'list' | 'management'>('list')

const warehouses = ref<Warehouse[]>([])
const loading = ref(true)
const warehouseLoadError = ref('')

const showCreateModal = ref(false)
const showEditModal = ref(false)
const showWarehouseVehiclesModal = ref(false)
const showVehicleTransferModal = ref(false)
const showCreateRuleModal = ref(false)
const showCascadeDeleteModal = ref(false)

const selectedWarehouse = ref<Warehouse | null>(null)
const selectedWarehouseNonNull = computed(() => selectedWarehouse.value as Warehouse)
const warehouseToDelete = ref<Warehouse | null>(null)

const rulesTableRef = ref<InstanceType<typeof WarehouseAccessRulesTable> | null>(null)

const availableMarks = ref<WarehouseMark[]>([])
const availableCities = ref<City[]>([])
const availableCompanies = ref<Company[]>([])

const currentFilters = ref({
  search: '',
  city_id: '',
  brand_id: '',
  access_type: '',
  owner_company_id: ''
})

const pagination = ref({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

const columns = [
  { key: 'brand', label: 'Марка' },
  { key: 'city_name', label: 'Город' },
  { key: 'address', label: 'Адрес' },
  { key: 'owner', label: 'Владелец' },
  { key: 'groups', label: 'Группы дилеров' },
  { key: 'vehicles_count', label: 'Количество ТС' },
  { key: 'warehouse_access_type', label: 'Тип склада' },
  { key: 'vehicle_types', label: 'Тип ТС' },
  { key: 'sites', label: 'Сайт' }
]

const actions = computed(() => [
  {
    key: 'transfer',
    label: 'Перемещение ТС',
    icon: ArrowsRightLeftIcon,
    className: 'text-indigo-600 hover:text-indigo-900',
    visible: () => canManageWarehouses.value
  },
  {
    key: 'edit',
    label: 'Редактировать',
    icon: PencilIcon,
    className: 'text-blue-600 hover:text-blue-900',
    visible: () => canManageWarehouses.value
  },
  {
    key: 'delete',
    label: 'Удалить склад',
    icon: TrashIcon,
    className: 'text-red-600 hover:text-red-900',
    visible: () => authStore.isCarCraftEmployee
  }
])

const asWarehouse = (item: unknown): Warehouse => item as Warehouse

const warehouseBrandDisplay = (w: Warehouse): string => {
  if (w.vehicle_marks && w.vehicle_marks.length > 0) return w.vehicle_marks.join(', ')
  return ''
}

const formatVehicleTypes = (types?: string[]) => {
  if (!types || types.length === 0) return ''
  const map: Record<string, string> = {
    new: 'Новые',
    used: 'Б/У',
    'Новые': 'Новые',
    'Б/У': 'Б/У'
  }
  return types.map(t => map[t] || t).join(', ')
}

const fetchWarehouses = async () => {
  loading.value = true
  warehouseLoadError.value = ''

  try {
    const res = await api.getWarehouses({
      page: pagination.value.page,
      limit: pagination.value.limit,
      search: currentFilters.value.search || undefined,
      city_id: currentFilters.value.city_id || undefined,
      brand_id: currentFilters.value.brand_id || undefined,
      access_type: currentFilters.value.access_type || undefined,
      owner_company_id: currentFilters.value.owner_company_id || undefined
    })

    warehouses.value = res.warehouses || []
    if (res.pagination) {
      pagination.value = res.pagination
    }
  } catch (err: unknown) {
    console.error('Error fetching warehouses:', err)
    warehouseLoadError.value = 'Проверьте подключение и повторите попытку.'
  } finally {
    loading.value = false
  }
}

const fetchFiltersData = async () => {
  try {
    const promises: Promise<unknown>[] = [
      api.getWarehouseMarks(),
      api.getCities()
    ]

    if (authStore.isCarCraftEmployee) {
      promises.push(api.getCompanies({ limit: 1000 }))
    }

    const [marksRes, citiesRes, companiesRes] = await Promise.all(promises)

    const typedMarks = marksRes as { marks?: WarehouseMark[]; items?: WarehouseMark[] }
    availableMarks.value = typedMarks.marks || typedMarks.items || []

    const typedCities = citiesRes as { cities?: City[] }
    availableCities.value = typedCities.cities || []

    if (companiesRes) {
      const typedCompanies = companiesRes as { companies?: Company[] }
      availableCompanies.value = (typedCompanies.companies || []).filter(
        c => c.company_type === 'dealer' || c.company_type === 'distributor'
      )
    }
  } catch (err) {
    console.error('Error fetching filters data:', err)
  }
}

const changePage = (page: number) => {
  pagination.value.page = page
  fetchWarehouses()
}

const applyFilters = () => {
  pagination.value.page = 1
  fetchWarehouses()
}

const resetFilters = () => {
  currentFilters.value = {
    search: '',
    city_id: '',
    brand_id: '',
    access_type: '',
    owner_company_id: ''
  }
  pagination.value.page = 1
  fetchWarehouses()
}

const openWarehouseVehicles = (warehouse: Warehouse) => {
  selectedWarehouse.value = { ...warehouse }
  showWarehouseVehiclesModal.value = true
}

const handleAction = ({ action, item }: { action: string; item: Warehouse }) => {
  selectedWarehouse.value = { ...item }

  if (action === 'transfer') {
    showVehicleTransferModal.value = true
  } else if (action === 'delete') {
    if (!authStore.isCarCraftEmployee) return
    warehouseToDelete.value = item
    showCascadeDeleteModal.value = true
  } else if (!canManageWarehouses.value) {
    return
  } else if (action === 'edit') {
    showEditModal.value = true
  }
}

const closeCascadeDeleteModal = () => {
  showCascadeDeleteModal.value = false
  warehouseToDelete.value = null
}

const handleCascadeDeleteSuccess = () => {
  closeCascadeDeleteModal()
  fetchWarehouses()
  fetchFiltersData()
  rulesTableRef.value?.fetchRules()
}

const handleSuccess = () => {
  showCreateModal.value = false
  showEditModal.value = false
  showWarehouseVehiclesModal.value = false
  showVehicleTransferModal.value = false
  selectedWarehouse.value = null
  fetchWarehouses()
  fetchFiltersData()
  rulesTableRef.value?.fetchRules()
}

const handleRuleCreated = () => {
  showCreateRuleModal.value = false
  rulesTableRef.value?.fetchRules()
}

onMounted(() => {
  fetchWarehouses()
  fetchFiltersData()
})
</script>
