<template>
  <div class="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg max-w-5xl w-full mx-4 max-h-[90vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-6 border-b">
        <div>
          <h3 class="text-lg font-medium text-gray-900">
            {{ readOnly ? 'Машины на складе' : 'Привязка машин к складу' }}
          </h3>
          <p class="text-sm text-gray-500 mt-1">
            {{ warehouse.address }} ({{ warehouse.brand }}{{ warehouse.city_name ? `, ${warehouse.city_name}` : '' }})
          </p>
        </div>
        <button
          class="text-gray-400 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          type="button"
          aria-label="Закрыть"
          :disabled="deletion.pending"
          @click="$emit('close')"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>

      <!-- Tabs -->
      <div v-if="!readOnly" class="border-b">
        <nav class="flex -mb-px px-6">
          <button
            @click="activeTab = 'bind'"
            :disabled="deletion.pending"
            :class="[
              'py-3 px-4 border-b-2 font-medium text-sm',
              activeTab === 'bind'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            Добавить машины
          </button>
          <button
            @click="activeTab = 'current'"
            :class="[
              'py-3 px-4 border-b-2 font-medium text-sm',
              activeTab === 'current'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            ]"
          >
            Машины на складе ({{ currentVehiclesCount }})
          </button>
        </nav>
      </div>

      <!-- Tab: Bind Vehicles -->
      <div v-if="!readOnly && activeTab === 'bind'" class="flex-1 overflow-hidden flex flex-col">
        <!-- Filters -->
        <div class="p-4 border-b bg-gray-50">
          <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Марка</label>
              <select v-model="filters.mark" class="select-field" @change="fetchAvailableVehicles">
                <option value="">Все марки</option>
                <option v-for="mark in availableMarks" :key="mark.id" :value="mark.id">
                  {{ mark.name }}
                </option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Поиск</label>
              <input
                v-model="filters.search"
                type="text"
                placeholder="VIN, марка или модель"
                class="input-field"
                @input="debouncedSearch"
              >
            </div>
            <div class="flex items-end">
              <button
                @click="bindByMark"
                :disabled="!filters.mark || bindingByMark"
                class="btn-secondary w-full"
              >
                <span v-if="bindingByMark">Привязка...</span>
                <span v-else>Привязать все {{ filters.mark ? 'выбранной марки' : '' }}</span>
              </button>
            </div>
            <div class="flex items-end">
              <button
                @click="bindSelected"
                :disabled="selectedVehicles.length === 0 || binding"
                class="btn-primary w-full"
              >
                <span v-if="binding">Привязка...</span>
                <span v-else>Привязать выбранные ({{ selectedVehicles.length }})</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Vehicles Table -->
        <div class="flex-1 overflow-auto p-4">
          <div v-if="loadingVehicles" class="text-center py-8">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <p class="mt-2 text-gray-600">Загружаем машины...</p>
          </div>

          <div v-else-if="availableVehicles.length === 0" class="text-center py-8">
            <p class="text-gray-600">Нет доступных машин для привязки</p>
            <p class="text-sm text-gray-400 mt-1">Только машины с VIN могут быть привязаны к складу</p>
          </div>

          <div v-else>
            <table class="min-w-full divide-y divide-gray-200">
              <thead class="bg-gray-50 sticky top-0">
                <tr>
                  <th class="px-4 py-3 text-left">
                    <input
                      type="checkbox"
                      :checked="isAllSelected"
                      :indeterminate="isPartialSelected"
                      @change="toggleSelectAll"
                      class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    >
                  </th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">VIN</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Марка</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Модель</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Год</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Цвет</th>
                  <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Текущий склад</th>
                </tr>
              </thead>
              <tbody class="bg-white divide-y divide-gray-200">
                <tr
                  v-for="vehicle in availableVehicles"
                  :key="vehicle.id"
                  class="hover:bg-gray-50"
                  :class="{ 'bg-blue-50': selectedVehicles.includes(vehicle.id) }"
                >
                  <td class="px-4 py-3">
                    <input
                      type="checkbox"
                      :checked="selectedVehicles.includes(vehicle.id)"
                      @change="toggleVehicle(vehicle.id)"
                      class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    >
                  </td>
                  <td class="px-4 py-3 text-sm font-mono text-gray-900">{{ vehicle.vin }}</td>
                  <td class="px-4 py-3 text-sm text-gray-900">{{ vehicle.mark_name }}</td>
                  <td class="px-4 py-3 text-sm text-gray-900">{{ vehicle.model_name }}</td>
                  <td class="px-4 py-3 text-sm text-gray-600">{{ vehicle.year }}</td>
                  <td class="px-4 py-3 text-sm text-gray-600">{{ vehicle.color || '-' }}</td>
                  <td class="px-4 py-3 text-sm">
                    <span v-if="vehicle.current_warehouse_address" class="text-orange-600">
                      {{ vehicle.current_warehouse_address }}
                    </span>
                    <span v-else class="text-gray-400">Не привязан</span>
                  </td>
                </tr>
              </tbody>
            </table>

            <!-- Pagination -->
            <div v-if="vehiclesPagination.pages > 1" class="mt-4 flex items-center justify-between">
              <div class="text-sm text-gray-500">
                Показаны {{ (vehiclesPagination.page - 1) * vehiclesPagination.limit + 1 }}-{{ Math.min(vehiclesPagination.page * vehiclesPagination.limit, vehiclesPagination.total) }} из {{ vehiclesPagination.total }}
              </div>
              <div class="flex space-x-2">
                <button
                  @click="changeVehiclesPage(vehiclesPagination.page - 1)"
                  :disabled="vehiclesPagination.page <= 1"
                  class="btn-secondary btn-sm disabled:opacity-50"
                >
                  Назад
                </button>
                <button
                  @click="changeVehiclesPage(vehiclesPagination.page + 1)"
                  :disabled="vehiclesPagination.page >= vehiclesPagination.pages"
                  class="btn-secondary btn-sm disabled:opacity-50"
                >
                  Далее
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: Current Vehicles -->
      <div v-if="activeTab === 'current'" class="flex-1 overflow-auto p-4">
        <div v-if="deletion.isAdmin" class="mb-4 flex items-center justify-between gap-4">
          <p class="text-sm text-gray-600">Всего на складе: {{ currentVehiclesCount }}</p>
          <div class="flex gap-3">
            <button type="button" class="btn-secondary disabled:opacity-50" :disabled="deletion.pending || unbinding || loadingCurrentVehicles || !!currentLoadError" @click="deletion.open('unbind')">Отвязать все</button>
            <button type="button" class="btn-danger disabled:opacity-50" :disabled="deletion.pending || unbinding || loadingCurrentVehicles || !!currentLoadError" @click="deletion.open('bulk')">Удалить все</button>
          </div>
        </div>
        <div v-if="deletion.isAdmin && deletion.result?.skipped.length" class="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-gray-900" role="status">
          <p class="font-medium">Остались на складе: {{ deletion.result.skipped_count }}</p>
          <details class="mt-2">
            <summary class="cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500">Пропущенные автомобили и причины</summary>
            <ul class="mt-3 max-h-64 overflow-auto space-y-3">
              <li v-for="(item, index) in deletion.result.skipped" :key="item.vehicle_id">
                <p class="font-medium">{{ item.vin || `Автомобиль без VIN №${index + 1}` }}</p>
                <ul class="mt-1 list-disc pl-5">
                  <li v-for="blocker in item.blocking_reasons" :key="blocker.type">{{ blocker.description }} — {{ blocker.count }}</li>
                </ul>
              </li>
            </ul>
          </details>
        </div>
        <label class="mb-4 block text-sm font-medium text-gray-700">Статус автомобиля
          <select v-model="currentStatus" class="select-field mt-1" @change="currentVehiclesPagination.page = 1; fetchCurrentVehicles()">
            <option value="">Все статусы</option><option value="available">На складе</option><option value="reserved">Забронирована</option><option value="sold">Продажа / оплата</option>
          </select>
        </label>
        <div v-if="currentLoadError" class="mb-4 rounded-lg bg-red-50 p-4 text-sm text-red-700" role="alert">
          <p>{{ currentLoadError }}</p>
          <button type="button" class="btn-secondary mt-2" :disabled="loadingCurrentVehicles || deletion.pending" @click="fetchCurrentVehicles">Повторить загрузку</button>
        </div>
        <div v-if="loadingCurrentVehicles" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p class="mt-2 text-gray-600">Загружаем машины на складе...</p>
        </div>

        <div v-else-if="!currentLoadError && currentVehicles.length === 0" class="text-center py-8">
          <p class="text-gray-600">На складе нет машин</p>
        </div>

        <div v-else>
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50 sticky top-0">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">VIN</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Марка</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Модель</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Год</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Цвет</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Статус</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Привязан</th>
                <th v-if="!readOnly" class="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Действия</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="vehicle in currentVehicles" :key="vehicle.id" class="hover:bg-gray-50">
                <td class="px-4 py-3 text-sm font-mono text-gray-900">{{ vehicle.vin }}</td>
                <td class="px-4 py-3 text-sm text-gray-900">{{ vehicle.mark_name }}</td>
                <td class="px-4 py-3 text-sm text-gray-900">{{ vehicle.model_name }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ vehicle.year }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ vehicle.color || '-' }}</td>
                <td class="px-4 py-3 text-sm"><span class="rounded-full bg-gray-100 px-2 py-1">{{ vehicleStockStatusLabel(vehicle) }}</span><p v-if="vehicle.reserved_until" class="mt-1 text-xs">Бронь до {{ formatDate(vehicle.reserved_until) }}</p></td>
                <td class="px-4 py-3 text-sm text-gray-500">{{ formatDate(vehicle.bound_at) }}</td>
                <td v-if="!readOnly" class="px-4 py-3 text-right">
                  <button
                    @click="unbindVehicle(vehicle)"
                    :disabled="deletion.pending || unbinding"
                    class="text-red-600 hover:text-red-900 text-sm"
                  >
                    Отвязать
                  </button>
                  <div v-if="deletion.isAdmin" class="mt-2 text-sm">
                    <button type="button" class="text-red-600 hover:text-red-900 disabled:text-gray-400 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-red-500 rounded"
                      :disabled="deletion.pending || unbinding || loadingCurrentVehicles || !!currentLoadError || !deletion.checks[vehicle.id]?.data?.can_delete || deletion.checks[vehicle.id]?.pending || !!deletion.checks[vehicle.id]?.error"
                      @click="deletion.open('single', vehicle.id)">Удалить</button>
                    <p v-if="deletion.checks[vehicle.id]?.pending" class="mt-1 text-gray-500">Проверка связей…</p>
                    <div v-else-if="deletion.checks[vehicle.id]?.error" class="mt-1 text-red-700">
                      <p>{{ deletion.checks[vehicle.id]?.error }}</p>
                      <button type="button" class="underline focus-visible:ring-2 focus-visible:ring-blue-500" :disabled="deletion.pending" @click="deletion.checkVehicle(vehicle.id)">Повторить проверку</button>
                    </div>
                    <details v-else-if="deletion.checks[vehicle.id]?.data?.blocking_reasons.length" class="mt-1 text-left text-gray-600">
                      <summary class="cursor-pointer focus-visible:ring-2 focus-visible:ring-blue-500">Причины запрета</summary>
                      <ul class="mt-2 space-y-1">
                        <li v-for="blocker in deletion.checks[vehicle.id]?.data?.blocking_reasons" :key="blocker.type">{{ blocker.description }} — {{ blocker.count }}</li>
                      </ul>
                    </details>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- Pagination for current vehicles -->
          <div v-if="currentVehiclesPagination.pages > 1" class="mt-4 flex items-center justify-between">
            <div class="text-sm text-gray-500">
              Показаны {{ (currentVehiclesPagination.page - 1) * currentVehiclesPagination.limit + 1 }}-{{ Math.min(currentVehiclesPagination.page * currentVehiclesPagination.limit, currentVehiclesPagination.total) }} из {{ currentVehiclesPagination.total }}
            </div>
            <div class="flex space-x-2">
              <button
                @click="changeCurrentVehiclesPage(currentVehiclesPagination.page - 1)"
                :disabled="currentVehiclesPagination.page <= 1 || deletion.pending || unbinding"
                class="btn-secondary btn-sm disabled:opacity-50"
              >
                Назад
              </button>
              <button
                @click="changeCurrentVehiclesPage(currentVehiclesPagination.page + 1)"
                :disabled="currentVehiclesPagination.page >= currentVehiclesPagination.pages || deletion.pending || unbinding"
                class="btn-secondary btn-sm disabled:opacity-50"
              >
                Далее
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="error" class="p-4 border-t bg-red-50">
        <p class="text-sm text-red-600">{{ error }}</p>
      </div>

      <!-- Success message -->
      <div v-if="successMessage" class="p-4 border-t bg-green-50">
        <p class="text-sm text-green-600" role="status">{{ successMessage }}</p>
      </div>
    </div>
    <Modal :show="deletion.isAdmin && deletion.operation !== null" :title="deletion.operation === 'single' ? 'Удалить автомобиль?' : deletion.operation === 'unbind' ? 'Отвязать все автомобили?' : 'Удалить автомобили склада?'"
      size="lg" :closable="!deletion.pending" :close-on-overlay="!deletion.pending" @close="deletion.close">
      <form class="space-y-4 text-sm text-gray-700" @submit.prevent="deletion.submit">
        <template v-if="deletion.operation === 'single' && deletion.selected">
          <p class="font-medium text-gray-900">{{ deletion.selected.check.name }}</p>
          <p>VIN: {{ deletion.selected.check.vin || 'не указан' }}</p>
          <p>Автомобиль будет физически удалён. Восстановить его через интерфейс невозможно.</p>
        </template>
        <template v-else>
          <p class="font-medium text-gray-900">{{ warehouse.address }}</p>
          <p>Операция действует на весь склад независимо от текущей страницы и фильтра.</p>
          <p v-if="deletion.operation === 'unbind'">Будут сняты все текущие привязки (сейчас: {{ currentVehiclesCount }}). Карточки автомобилей, их связи и история перемещений сохранятся.</p>
          <template v-else>
            <p v-if="deletion.summaryPending" role="status">Проверяем автомобили всего склада…</p>
            <template v-if="deletion.summary">
              <p>Всего: {{ deletion.summary.requested_count }}. Можно удалить: {{ deletion.summary.deletable_count }}. Заблокировано: {{ deletion.summary.blocked_count }}.</p>
              <ul class="max-h-48 overflow-auto space-y-1">
                <li v-for="blocker in deletion.summary.blocking_reasons" :key="blocker.type">{{ blocker.description }} — связей: {{ blocker.count }}, автомобилей: {{ blocker.vehicle_count }}</li>
              </ul>
              <p>Разрешённые автомобили будут физически удалены. Заблокированные останутся на складе. Перед удалением связи проверяются повторно, поэтому итог может отличаться от сводки.</p>
            </template>
            <button type="button" class="btn-secondary" :disabled="deletion.summaryPending || deletion.pending" @click="deletion.loadSummary">Обновить проверку</button>
          </template>
        </template>
        <div v-if="deletion.operation !== 'unbind'">
          <label for="vehicle-delete-confirmation" class="mb-1 block font-medium">{{ deletion.operation === 'single' && deletion.selected?.check.vin ? 'Введите VIN автомобиля или слово УДАЛИТЬ' : 'Введите слово УДАЛИТЬ' }}</label>
          <input id="vehicle-delete-confirmation" v-model="deletion.confirmation" class="input-field" autocomplete="off" :disabled="deletion.pending">
        </div>
        <div v-if="deletion.operation === 'single'">
          <label for="vehicle-delete-reason" class="mb-1 block font-medium">Комментарий администратора (необязательно)</label>
          <input id="vehicle-delete-reason" v-model="deletion.reason" class="input-field" :disabled="deletion.pending">
        </div>
        <div v-if="deletion.dialogError" class="rounded bg-red-50 p-3 text-red-700" role="alert">
          <p>{{ deletion.dialogError }}</p>
          <ul class="mt-2 space-y-1"><li v-for="blocker in deletion.conflictReasons" :key="blocker.type">{{ blocker.description }} — {{ blocker.count }}</li></ul>
        </div>
        <div class="flex justify-end gap-3 border-t pt-4">
          <button type="button" class="btn-secondary" :disabled="deletion.pending" @click="deletion.close">Отмена</button>
          <button type="submit" class="btn-danger disabled:opacity-50 disabled:cursor-not-allowed" :disabled="!deletion.canConfirm">{{ deletion.pending ? 'Выполняем…' : deletion.operation === 'unbind' ? 'Отвязать все' : deletion.operation === 'single' ? 'Удалить автомобиль' : 'Удалить все разрешённые' }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { vehicleStockStatusLabel } from '~/utils/vehicleStockStatus'
import type { AdminVehicle, VehicleMark, Pagination, BindStats, BulkBindVehiclesResponse } from '~/types/admin'
import type { Warehouse } from '~/types/features'
import Modal from '~/components/ui/Modal.vue'
import { useWarehouseVehicleDeletion } from '~/features/admin/vehicles/composables/useWarehouseVehicleDeletion'

const props = withDefaults(defineProps<{
  warehouse: Warehouse
  readOnly?: boolean
}>(), {
  readOnly: false
})

const emit = defineEmits(['close', 'success', 'changed'])

const config = useRuntimeConfig()
const nuxtApp = useNuxtApp()

const activeTab = ref<'bind' | 'current'>(props.readOnly ? 'current' : 'bind')

// Available vehicles for binding
const availableVehicles = ref<AdminVehicle[]>([])
const loadingVehicles = ref(!props.readOnly)
const selectedVehicles = ref<string[]>([])
const availableMarks = ref<VehicleMark[]>([])

const filters = ref({
  mark: '',
  search: ''
})

const vehiclesPagination = ref({
  page: 1,
  limit: 50,
  total: 0,
  pages: 0
})

// Current vehicles on warehouse
const currentStatus = ref('')
const currentVehicles = ref<AdminVehicle[]>([])
const loadingCurrentVehicles = ref(true)
const currentVehiclesCount = ref(0)
const currentLoadError = ref('')
let currentLoadVersion = 0

const currentVehiclesPagination = ref({
  page: 1,
  limit: 50,
  total: 0,
  pages: 0
})

// Status
const binding = ref(false)
const bindingByMark = ref(false)
const error = ref('')
const successMessage = ref('')
const unbinding = ref(false)
const deletion = reactive(useWarehouseVehicleDeletion(
  () => props.warehouse.id,
  () => props.readOnly,
  async () => {
    selectedVehicles.value = []
    vehiclesPagination.value.page = 1
    await Promise.all([fetchCurrentVehicles(), fetchAvailableVehicles(), fetchAvailableMarks()])
    emit('changed')
    const catalogKeys = Object.keys(nuxtApp.payload.data).filter(key => /vehicle|car|catalog|warehouse|model-showcase/i.test(key))
    await refreshNuxtData(catalogKeys).catch(() => {
      error.value = 'Операция выполнена, но не все данные каталога обновились. Обновите страницу.'
    })
  },
  successMessage
))

// Computed
const isAllSelected = computed(() => {
  return availableVehicles.value.length > 0 &&
    availableVehicles.value.every(v => selectedVehicles.value.includes(v.id))
})

const isPartialSelected = computed(() => {
  return selectedVehicles.value.length > 0 && !isAllSelected.value
})

// Methods
const fetchAvailableVehicles = async () => {
  if (props.readOnly) return

  loadingVehicles.value = true
  error.value = ''

  try {
    const params = new URLSearchParams({
      page: vehiclesPagination.value.page.toString(),
      limit: vehiclesPagination.value.limit.toString(),
      only_unbound: 'true'
    })

    if (filters.value.mark) params.append('mark', filters.value.mark)
    if (filters.value.search) params.append('search', filters.value.search)

    const response = await $fetch(`/api/v1/admin/vehicles/for-warehouse?${params.toString()}`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const data = response as { vehicles: AdminVehicle[]; pagination: Pagination }
    availableVehicles.value = data.vehicles || []
    vehiclesPagination.value = data.pagination
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    error.value = e.data?.error || 'Ошибка загрузки машин'
  } finally {
    loadingVehicles.value = false
  }
}

const fetchAvailableMarks = async () => {
  if (props.readOnly) return

  try {
    const response = await $fetch('/api/v1/admin/vehicles/marks-with-vin', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    availableMarks.value = (response as { marks: VehicleMark[] }).marks
  } catch (err: unknown) {
    console.error('Ошибка загрузки марок:', err)
  }
}

const fetchCurrentVehicles = async () => {
  const version = ++currentLoadVersion
  loadingCurrentVehicles.value = true
  currentLoadError.value = ''
  void deletion.checkRows([])

  try {
    const params = new URLSearchParams({
      page: currentVehiclesPagination.value.page.toString(),
      limit: currentVehiclesPagination.value.limit.toString(),
      ...(currentStatus.value ? { status: currentStatus.value } : {})
    })

    const response = await $fetch(`/api/v1/admin/warehouses/${props.warehouse.id}/vehicles?${params.toString()}`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const data = response as { vehicles: AdminVehicle[]; pagination: Pagination }
    if (version !== currentLoadVersion) return
    const lastPage = Math.max(1, data.pagination.pages)
    if (currentVehiclesPagination.value.page > lastPage) {
      currentVehiclesPagination.value.page = lastPage
      await fetchCurrentVehicles()
      return
    }
    currentVehicles.value = data.vehicles || []
    currentVehiclesPagination.value = data.pagination
    currentVehiclesCount.value = data.pagination.total
    void deletion.checkRows(currentVehicles.value.map(vehicle => vehicle.id))
  } catch (err: unknown) {
    if (version === currentLoadVersion) currentLoadError.value = 'Не удалось обновить машины склада. Повторите загрузку.'
  } finally {
    if (version === currentLoadVersion) loadingCurrentVehicles.value = false
  }
}

const debouncedSearch = useLodash().debounce(() => {
  vehiclesPagination.value.page = 1
  fetchAvailableVehicles()
}, 500)

const changeVehiclesPage = (page: number) => {
  vehiclesPagination.value.page = page
  fetchAvailableVehicles()
}

const changeCurrentVehiclesPage = (page: number) => {
  if (deletion.pending || unbinding.value || loadingCurrentVehicles.value) return
  currentVehiclesPagination.value.page = page
  fetchCurrentVehicles()
}

const toggleVehicle = (id: string) => {
  if (props.readOnly) return

  const index = selectedVehicles.value.indexOf(id)
  if (index === -1) {
    selectedVehicles.value.push(id)
  } else {
    selectedVehicles.value.splice(index, 1)
  }
}

const toggleSelectAll = () => {
  if (props.readOnly) return

  if (isAllSelected.value) {
    // Deselect all on current page
    availableVehicles.value.forEach(v => {
      const index = selectedVehicles.value.indexOf(v.id)
      if (index !== -1) {
        selectedVehicles.value.splice(index, 1)
      }
    })
  } else {
    // Select all on current page
    availableVehicles.value.forEach(v => {
      if (!selectedVehicles.value.includes(v.id)) {
        selectedVehicles.value.push(v.id)
      }
    })
  }
}

const bindSelected = async () => {
  if (props.readOnly || selectedVehicles.value.length === 0) return

  binding.value = true
  error.value = ''
  successMessage.value = ''

  try {
    const response = await $fetch(`/api/v1/admin/warehouses/${props.warehouse.id}/vehicles/bulk`, {
      method: 'POST',
      body: { vehicle_ids: selectedVehicles.value },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const data = response as BulkBindVehiclesResponse
    successMessage.value = `Привязано: ${data.bound}, пропущено: ${data.skipped}`
    selectedVehicles.value = []
    fetchAvailableVehicles()
    fetchCurrentVehicles()
    emit('success')
  } catch (err: unknown) {
    const e = err as { data?: { detail?: unknown } }
    const detail = e.data?.detail
    const detailMessage = typeof detail === 'string'
      ? detail.trim()
      : Array.isArray(detail)
        ? detail
          .map(item => (
            typeof item === 'object' && item !== null && 'msg' in item
              ? String(item.msg)
              : ''
          ))
          .filter(Boolean)
          .join('; ')
        : ''
    error.value = detailMessage || 'Ошибка привязки машин'
  } finally {
    binding.value = false
  }
}

const bindByMark = async () => {
  if (props.readOnly || !filters.value.mark) return

  bindingByMark.value = true
  error.value = ''
  successMessage.value = ''

  try {
    const response = await $fetch(`/api/v1/admin/warehouses/${props.warehouse.id}/vehicles/bind-by-mark`, {
      method: 'POST',
      body: { mark_id: filters.value.mark },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const data = response as { stats: BindStats }
    successMessage.value = `Привязано: ${data.stats.bound}, перемещено: ${data.stats.moved}`
    selectedVehicles.value = []
    fetchAvailableVehicles()
    fetchCurrentVehicles()
    emit('success')
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    error.value = e.data?.error || 'Ошибка массовой привязки'
  } finally {
    bindingByMark.value = false
  }
}

const unbindVehicle = async (vehicle: AdminVehicle) => {
  if (props.readOnly || deletion.pending || unbinding.value) return

  unbinding.value = true
  error.value = ''
  successMessage.value = ''

  try {
    await $fetch(`/api/v1/admin/warehouses/${props.warehouse.id}/vehicles/${vehicle.id}`, {
      method: 'DELETE',
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    successMessage.value = `Машина ${vehicle.vin} отвязана от склада`
    fetchAvailableVehicles()
    fetchCurrentVehicles()
    emit('success')
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    error.value = e.data?.error || 'Ошибка отвязки машины'
  } finally {
    unbinding.value = false
  }
}

const formatDate = (dateString: string | undefined) => {
  return new Date(dateString || '').toLocaleDateString('ru-RU')
}

// Watch tab changes
watch(() => deletion.isAdmin, allowed => {
  if (allowed) void deletion.checkRows(currentVehicles.value.map(vehicle => vehicle.id))
})

watch(activeTab, (newTab) => {
  if (newTab === 'current' && currentVehicles.value.length === 0) {
    fetchCurrentVehicles()
  }
})

onMounted(() => {
  if (!props.readOnly) {
    fetchAvailableVehicles()
    fetchAvailableMarks()
  }
  fetchCurrentVehicles()
})
</script>
