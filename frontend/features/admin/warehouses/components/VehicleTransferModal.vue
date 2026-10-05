<template>
  <Modal
    :show="true"
    size="6xl"
    title="Перемещение ТС"
    :subtitle="stage === 'confirm' ? 'Подтвердите параметры перемещения' : 'Выберите исходный склад, целевой склад и ТС'"
    :closable="!submitting"
    show-footer
    body-class="max-h-[calc(100dvh-11rem)] overflow-y-auto"
    @close="emit('close')"
  >
    <section v-if="stage === 'select'" class="space-y-5">
      <div v-if="loadError" class="rounded-md bg-red-50 p-3 text-sm text-red-700">
        {{ loadError }}
      </div>

      <div class="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)]">
        <div class="space-y-5">
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label class="block text-sm font-medium text-gray-700">
              Переместить со склада
              <select v-model="sourceWarehouseId" class="select-field mt-1" :disabled="loadingWarehouses" @change="changeSource">
                <option value="">Выберите склад</option>
                <option v-for="warehouse in warehouses" :key="warehouse.id" :value="warehouse.id">
                  {{ warehouseLabel(warehouse) }} ({{ warehouse.vehicles_count }} ТС)
                </option>
              </select>
            </label>

            <label class="block text-sm font-medium text-gray-700">
              Переместить на склад
              <select v-model="destinationWarehouseId" class="select-field mt-1" :disabled="!sourceWarehouseId || loadingWarehouses">
                <option value="">Выберите склад</option>
                <option v-for="warehouse in destinationWarehouses" :key="warehouse.id" :value="warehouse.id">
                  {{ warehouseLabel(warehouse) }}
                </option>
              </select>
            </label>
          </div>

          <template v-if="sourceWarehouseId">
            <div v-if="loadingVehicles" class="py-10 text-center text-gray-500">Загружаем ТС…</div>
        <div v-else-if="vehicles.length === 0" class="py-10 text-center text-gray-500">На выбранном складе нет ТС по заданным фильтрам</div>
        <div v-else class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-4 py-3 text-left">
                  <input type="checkbox" :checked="isPageSelected" :indeterminate="isPagePartiallySelected" aria-label="Выбрать все на странице" @change="togglePageSelection">
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">VIN</th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Марка</th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Модель</th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Год</th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Цвет</th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Текущий склад</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200 bg-white">
              <tr v-for="vehicle in vehicles" :key="vehicle.id" :class="selectedVehicleIds.includes(vehicle.id) ? 'bg-blue-50' : ''">
                <td class="px-4 py-3"><input type="checkbox" :checked="selectedVehicleIds.includes(vehicle.id)" :aria-label="`Выбрать ${vehicle.vin}`" @change="toggleVehicle(vehicle.id)"></td>
                <td class="px-4 py-3 font-mono text-sm text-gray-900">{{ vehicle.vin }}</td>
                <td class="px-4 py-3 text-sm text-gray-900">{{ vehicle.mark_name }}</td>
                <td class="px-4 py-3 text-sm text-gray-900">{{ vehicle.model_name }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ vehicle.year }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ vehicle.color || '—' }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ sourceWarehouseLabel }}</td>
              </tr>
            </tbody>
          </table>
        </div>

            <div v-if="pagination.pages > 1" class="flex items-center justify-between text-sm text-gray-600">
              <span>Показано {{ pageStart }}–{{ pageEnd }} из {{ pagination.total }}</span>
              <div class="flex gap-2">
                <button type="button" class="btn-secondary btn-sm" :disabled="pagination.page <= 1" @click="changePage(pagination.page - 1)">Назад</button>
                <button type="button" class="btn-secondary btn-sm" :disabled="pagination.page >= pagination.pages" @click="changePage(pagination.page + 1)">Далее</button>
              </div>
            </div>
          </template>
        </div>

        <aside v-if="sourceWarehouseId" class="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div class="mb-3 flex items-center justify-between gap-3">
            <h4 class="font-medium text-gray-900">Фильтры ТС</h4>
            <button type="button" class="text-sm text-blue-600 hover:text-blue-800" @click="resetFilters">
              Сбросить фильтры
            </button>
          </div>
          <div class="space-y-3">
            <label class="block text-sm text-gray-700">
              VIN
              <input v-model.trim="filters.vin" class="input-field mt-1" placeholder="Введите VIN" @input="scheduleVehicleFetch">
            </label>

            <details class="vehicle-filter-dropdown group">
              <summary class="cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 marker:hidden">
                <span class="block truncate">{{ selectionSummary('Выберите марку', filters.mark_ids, facets.marks) }}</span>
              </summary>
              <div class="mt-1 max-h-48 overflow-y-auto rounded-md border border-gray-200 bg-white p-2 shadow-sm">
                <label v-for="mark in facets.marks" :key="mark.id" class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50">
                  <input type="checkbox" :checked="filters.mark_ids.includes(mark.id)" @change="toggleStringFilter('mark_ids', mark.id)">
                  {{ mark.name }}
                </label>
              </div>
            </details>

            <details class="vehicle-filter-dropdown group">
              <summary class="cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 marker:hidden">
                <span class="block truncate">{{ selectionSummary('Выберите модель', filters.model_ids, facets.models) }}</span>
              </summary>
              <div class="mt-1 max-h-48 overflow-y-auto rounded-md border border-gray-200 bg-white p-2 shadow-sm">
                <label v-for="model in facets.models" :key="model.id" class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50">
                  <input type="checkbox" :checked="filters.model_ids.includes(model.id)" @change="toggleStringFilter('model_ids', model.id)">
                  {{ model.name }}
                </label>
              </div>
            </details>

            <details class="vehicle-filter-dropdown group">
              <summary class="cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 marker:hidden">
                <span class="block truncate">{{ selectionSummary('Выберите год', filters.years.map(String), yearOptions) }}</span>
              </summary>
              <div class="mt-1 max-h-48 overflow-y-auto rounded-md border border-gray-200 bg-white p-2 shadow-sm">
                <label v-for="year in facets.years" :key="year" class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50">
                  <input type="checkbox" :checked="filters.years.includes(year)" @change="toggleYearFilter(year)">
                  {{ year }}
                </label>
              </div>
            </details>

            <details class="vehicle-filter-dropdown group">
              <summary class="cursor-pointer rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 marker:hidden">
                <span class="block truncate">{{ selectionSummary('Выберите цвет', filters.colors, colorOptions) }}</span>
              </summary>
              <div class="mt-1 max-h-48 overflow-y-auto rounded-md border border-gray-200 bg-white p-2 shadow-sm">
                <label v-for="color in facets.colors" :key="color" class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50">
                  <input type="checkbox" :checked="filters.colors.includes(color)" @change="toggleStringFilter('colors', color)">
                  {{ color }}
                </label>
              </div>
            </details>
          </div>
        </aside>
      </div>
    </section>

    <section v-else class="space-y-4 text-sm text-gray-700">
      <p>Вы собираетесь переместить <strong>{{ confirmationCount }}</strong> {{ transferModeLabel }}.</p>
      <dl class="grid grid-cols-1 gap-3 rounded-lg bg-gray-50 p-4 md:grid-cols-2">
        <div><dt class="text-gray-500">Исходный склад</dt><dd class="font-medium text-gray-900">{{ sourceWarehouseLabel }}</dd></div>
        <div><dt class="text-gray-500">Целевой склад</dt><dd class="font-medium text-gray-900">{{ destinationWarehouseLabel }}</dd></div>
      </dl>
      <p class="text-gray-500">Операция изменит текущий склад ТС. Конфликтные ТС останутся на прежнем складе.</p>
    </section>

    <template #footer>
      <template v-if="stage === 'select'">
        <button type="button" class="btn-secondary" :disabled="submitting" @click="emit('close')">Отмена</button>
        <button type="button" class="btn-secondary" :disabled="!canTransferAll || submitting" @click="openConfirmation('all')">Переместить все{{ pagination.total ? ` (${pagination.total})` : '' }}</button>
        <button type="button" class="btn-primary" :disabled="!canTransferSelected || submitting" @click="openConfirmation('selected')">Переместить</button>
      </template>
      <template v-else>
        <button type="button" class="btn-secondary" :disabled="submitting" @click="stage = 'select'">Назад</button>
        <button type="button" class="btn-primary" :disabled="submitting" @click="submitTransfer">{{ submitting ? 'Перемещаем…' : 'Подтвердить перемещение' }}</button>
      </template>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import Modal from '~/components/ui/Modal.vue'
import { useToast } from '~/composables/useToast'

interface TransferWarehouse {
  id: string
  address: string
  brand: string
  city_name: string | null
  vehicles_count: number
}

interface TransferVehicle {
  id: string
  vin: string | null
  mark_name: string | null
  model_name: string | null
  year: number | null
  color: string | null
  source_warehouse_id: string
}

interface FacetOption { id: string; name: string }
interface TransferFacets { marks: FacetOption[]; models: FacetOption[]; years: number[]; colors: string[] }
interface TransferPagination { page: number; limit: number; total: number; pages: number }
interface VehiclesResponse { vehicles: TransferVehicle[]; pagination: TransferPagination; facets: TransferFacets }
interface TransferResponse { transferred_count: number; failed_count: number }
interface TransferBasePayload { source_warehouse_id: string; destination_warehouse_id: string }
type TransferSelection =
  | { vehicle_ids: string[] }
  | { all_filtered: true; vin?: string; mark_ids?: string[]; model_ids?: string[]; years?: number[]; colors?: string[] }

type TransferMode = 'selected' | 'all'

const emit = defineEmits<{ (event: 'close'): void; (event: 'success'): void }>()
const config = useRuntimeConfig()
const toast = useToast()
const apiBase = '/api/v1/distributor/warehouse-transfers'

const warehouses = ref<TransferWarehouse[]>([])
const sourceWarehouseId = ref('')
const destinationWarehouseId = ref('')
const vehicles = ref<TransferVehicle[]>([])
const selectedVehicleIds = ref<string[]>([])
const loadingWarehouses = ref(true)
const loadingVehicles = ref(false)
const submitting = ref(false)
const loadError = ref('')
const stage = ref<'select' | 'confirm'>('select')
const transferMode = ref<TransferMode>('selected')
const pagination = ref<TransferPagination>({ page: 1, limit: 50, total: 0, pages: 0 })
const facets = ref<TransferFacets>({ marks: [], models: [], years: [], colors: [] })
const filters = ref({ vin: '', mark_ids: [] as string[], model_ids: [] as string[], years: [] as number[], colors: [] as string[] })
const yearOptions = computed<FacetOption[]>(() => facets.value.years.map(year => ({ id: String(year), name: String(year) })))
const colorOptions = computed<FacetOption[]>(() => facets.value.colors.map(color => ({ id: color, name: color })))
let searchTimer: ReturnType<typeof setTimeout> | undefined

const destinationWarehouses = computed(() => warehouses.value.filter(warehouse => warehouse.id !== sourceWarehouseId.value))
const selectedSourceWarehouse = computed(() => warehouses.value.find(warehouse => warehouse.id === sourceWarehouseId.value))
const selectedDestinationWarehouse = computed(() => warehouses.value.find(warehouse => warehouse.id === destinationWarehouseId.value))
const sourceWarehouseLabel = computed(() => selectedSourceWarehouse.value ? warehouseLabel(selectedSourceWarehouse.value) : '—')
const destinationWarehouseLabel = computed(() => selectedDestinationWarehouse.value ? warehouseLabel(selectedDestinationWarehouse.value) : '—')
const isPageSelected = computed(() => vehicles.value.length > 0 && vehicles.value.every(vehicle => selectedVehicleIds.value.includes(vehicle.id)))
const isPagePartiallySelected = computed(() => !isPageSelected.value && vehicles.value.some(vehicle => selectedVehicleIds.value.includes(vehicle.id)))
const canTransferBase = computed(() => Boolean(sourceWarehouseId.value && destinationWarehouseId.value && sourceWarehouseId.value !== destinationWarehouseId.value))
const canTransferSelected = computed(() => canTransferBase.value && selectedVehicleIds.value.length > 0)
const canTransferAll = computed(() => canTransferBase.value && pagination.value.total > 0)
const confirmationCount = computed(() => transferMode.value === 'selected' ? selectedVehicleIds.value.length : pagination.value.total)
const transferModeLabel = computed(() => transferMode.value === 'selected' ? 'выбранных ТС' : 'ТС по текущим фильтрам')
const pageStart = computed(() => pagination.value.total === 0 ? 0 : (pagination.value.page - 1) * pagination.value.limit + 1)
const pageEnd = computed(() => Math.min(pagination.value.page * pagination.value.limit, pagination.value.total))

const warehouseLabel = (warehouse: TransferWarehouse) => `${warehouse.address}${warehouse.city_name ? `, ${warehouse.city_name}` : ''}`
const selectionSummary = (placeholder: string, selectedIds: string[], options: FacetOption[]) => {
  const names = options.filter(option => selectedIds.includes(option.id)).map(option => option.name)
  return names.length ? names.join(', ') : placeholder
}
const toggleStringFilter = (key: 'mark_ids' | 'model_ids' | 'colors', value: string) => {
  const values = filters.value[key]
  filters.value[key] = values.includes(value) ? values.filter(item => item !== value) : [...values, value]
  applyFilters()
}
const toggleYearFilter = (year: number) => {
  filters.value.years = filters.value.years.includes(year)
    ? filters.value.years.filter(item => item !== year)
    : [...filters.value.years, year]
  applyFilters()
}

const queryParams = () => {
  const params = new URLSearchParams({ source_warehouse_id: sourceWarehouseId.value, page: String(pagination.value.page), limit: String(pagination.value.limit) })
  if (filters.value.vin) params.append('vin', filters.value.vin)
  filters.value.mark_ids.forEach(id => params.append('mark_ids', id))
  filters.value.model_ids.forEach(id => params.append('model_ids', id))
  filters.value.years.forEach(year => params.append('years', String(year)))
  filters.value.colors.forEach(color => params.append('colors', color))
  return params
}

const fetchWarehouses = async () => {
  loadingWarehouses.value = true
  loadError.value = ''
  try {
    const response = await $fetch<{ warehouses: TransferWarehouse[] }>(`${apiBase}/warehouses`, { baseURL: config.public.apiBase, credentials: 'include' })
    warehouses.value = response.warehouses
  } catch (error: unknown) {
    loadError.value = 'Не удалось загрузить доступные склады'
    toast.apiError(error as { data?: { error?: string }; message?: string }, loadError.value)
  } finally {
    loadingWarehouses.value = false
  }
}

const fetchVehicles = async () => {
  if (!sourceWarehouseId.value) return
  loadingVehicles.value = true
  loadError.value = ''
  try {
    const response = await $fetch<VehiclesResponse>(`${apiBase}/vehicles?${queryParams().toString()}`, { baseURL: config.public.apiBase, credentials: 'include' })
    vehicles.value = response.vehicles
    pagination.value = response.pagination
    facets.value = response.facets
  } catch (error: unknown) {
    loadError.value = 'Не удалось загрузить ТС исходного склада'
    toast.apiError(error as { data?: { error?: string }; message?: string }, loadError.value)
  } finally {
    loadingVehicles.value = false
  }
}

const changeSource = () => {
  destinationWarehouseId.value = ''
  selectedVehicleIds.value = []
  pagination.value.page = 1
  filters.value = { vin: '', mark_ids: [], model_ids: [], years: [], colors: [] }
  facets.value = { marks: [], models: [], years: [], colors: [] }
  vehicles.value = []
  if (sourceWarehouseId.value) fetchVehicles()
}

const applyFilters = () => { pagination.value.page = 1; fetchVehicles() }
const scheduleVehicleFetch = () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(applyFilters, 350)
}
const resetFilters = () => {
  filters.value = { vin: '', mark_ids: [], model_ids: [], years: [], colors: [] }
  pagination.value.page = 1
  fetchVehicles()
}
const changePage = (page: number) => { pagination.value.page = page; fetchVehicles() }
const toggleVehicle = (vehicleId: string) => {
  selectedVehicleIds.value = selectedVehicleIds.value.includes(vehicleId)
    ? selectedVehicleIds.value.filter(id => id !== vehicleId)
    : [...selectedVehicleIds.value, vehicleId]
}
const togglePageSelection = () => {
  const pageIds = vehicles.value.map(vehicle => vehicle.id)
  selectedVehicleIds.value = isPageSelected.value
    ? selectedVehicleIds.value.filter(id => !pageIds.includes(id))
    : [...new Set([...selectedVehicleIds.value, ...pageIds])]
}
const openConfirmation = (mode: TransferMode) => { transferMode.value = mode; stage.value = 'confirm' }

const submitTransfer = async () => {
  if (!canTransferBase.value || submitting.value) return
  submitting.value = true
  try {
    const selection: TransferSelection = transferMode.value === 'selected'
      ? { vehicle_ids: selectedVehicleIds.value }
      : { all_filtered: true, ...filters.value }
    const payload: TransferBasePayload & TransferSelection = {
      source_warehouse_id: sourceWarehouseId.value,
      destination_warehouse_id: destinationWarehouseId.value,
      ...selection
    }
    const response = await $fetch<TransferResponse>(`${apiBase}`, {
      method: 'POST',
      baseURL: config.public.apiBase,
      credentials: 'include',
      body: payload
    })
    toast.success(`Перемещено: ${response.transferred_count}, не перемещено: ${response.failed_count}`)
    emit('success')
    emit('close')
  } catch (error: unknown) {
    toast.apiError(error as { data?: { error?: string }; message?: string }, 'Не удалось переместить ТС')
    stage.value = 'select'
  } finally {
    submitting.value = false
  }
}

onMounted(fetchWarehouses)
onUnmounted(() => { if (searchTimer) clearTimeout(searchTimer) })
</script>
