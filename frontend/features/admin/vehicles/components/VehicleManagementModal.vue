<template>
  <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
    <div class="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] overflow-hidden">
      <div class="p-6 border-b border-gray-200">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-semibold text-gray-900">
            Управление транспортными средствами
          </h3>
          <button @click="$emit('close')" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>
        <p class="text-sm text-gray-500 mt-1">
          Заявка {{ formatApplicationNumber(application) }} | {{ application.name }} | {{ formatPrice(application.total_vehicles_price || 0) }}
        </p>
      </div>

      <div class="p-6 overflow-y-auto max-h-[70vh]">
        <!-- Loading -->
        <div v-if="loading" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p class="mt-2 text-gray-600">Загружаем автомобили...</p>
        </div>

        <!-- Vehicles list -->
        <div v-else class="space-y-4">
          <div 
            v-for="vehicle in vehicles" 
            :key="vehicle.id"
            class="border rounded-lg p-4"
            :class="editingVehicleId === vehicle.id ? 'border-blue-500 bg-blue-50' : 'border-gray-200'"
          >
            <div class="flex items-start justify-between mb-3">
              <div>
                <h4 class="font-medium text-gray-900">
                  {{ getVehicleTitle(vehicle) }}
                </h4>
                <p class="text-sm text-gray-600">
                  {{ getVehicleSubtitle(vehicle) }}
                </p>
              </div>
              <div class="text-right">
                <div class="font-medium">{{ formatPrice(vehicle.total_price || vehicle.unit_price || 0) }}</div>
                <div class="text-sm text-gray-500">Кол-во: {{ vehicle.quantity || 1 }}</div>
              </div>
            </div>

            <!-- Current assignment info -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4 text-sm">
              <div>
                <span class="text-gray-500">VIN:</span>
                <span class="ml-1 font-medium" :class="vehicle.assigned_vin || vehicle.vehicle_vin ? 'text-green-600' : 'text-yellow-600'">
                  {{ vehicle.assigned_vin || vehicle.vehicle_vin || 'Не назначен' }}
                </span>
              </div>
              <div>
                <span class="text-gray-500">Дилер:</span>
                <span class="ml-1 font-medium">{{ vehicle.dealer_name || 'Не назначен' }}</span>
              </div>
              <div>
                <span class="text-gray-500">Дистрибьютор:</span>
                <span class="ml-1 font-medium">{{ vehicle.distributor_name || 'Не назначен' }}</span>
              </div>
            </div>

            <div
              v-if="hasSupportInfo(vehicle)"
              class="mb-4 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm"
            >
              <div class="font-medium text-green-800">
                {{ getSupportTitle(vehicle) }}
              </div>
              <div class="mt-0.5 text-xs text-green-700">
                {{ getSupportTypeLabel(vehicle.support_type) }}
                <span v-if="vehicle.support_amount">
                  · {{ formatPrice(vehicle.support_amount) }}
                </span>
              </div>
            </div>

            <!-- Edit mode -->
            <div v-if="editingVehicleId === vehicle.id" class="border-t pt-4 mt-4 space-y-4">
              <!-- VIN section -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">VIN</label>
                <div class="flex space-x-2">
                  <input 
                    v-model="editForm.vin" 
                    type="text" 
                    placeholder="Введите VIN вручную"
                    class="input-field flex-1"
                  >
                  <button @click="showVinSelector = true" class="btn-secondary text-sm">
                    Выбрать из БД
                  </button>
                </div>
              </div>

              <!-- Dealer/Distributor -->
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">Дилер</label>
                  <select v-model="editForm.dealer_id" class="input-field">
                    <option :value="null">Не назначен</option>
                    <option v-for="dealer in dealers" :key="dealer.id" :value="dealer.id">
                      {{ dealer.name }} ({{ dealer.company_name || dealer.phone }})
                    </option>
                  </select>
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 mb-1">Дистрибьютор</label>
                  <select v-model="editForm.distributor_id" class="input-field">
                    <option :value="null">Не назначен</option>
                    <option v-for="dist in distributors" :key="dist.id" :value="dist.id">
                      {{ dist.name }}
                    </option>
                  </select>
                </div>
              </div>

              <!-- Edit actions -->
              <div class="flex space-x-2">
                <button 
                  @click="saveVehicleChanges(vehicle.id)" 
                  :disabled="saving"
                  class="btn-primary text-sm"
                >
                  {{ saving ? 'Сохранение...' : 'Сохранить' }}
                </button>
                <button @click="cancelEdit" class="btn-secondary text-sm">
                  Отмена
                </button>
              </div>
            </div>

            <!-- Edit button -->
            <div v-else class="flex justify-end">
              <button @click="startEdit(vehicle)" class="btn-secondary text-sm">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                </svg>
                Редактировать
              </button>
            </div>
          </div>

          <div v-if="vehicles.length === 0" class="text-center py-8 text-gray-500">
            Нет автомобилей в заявке
          </div>
        </div>
      </div>

      <div class="p-6 border-t border-gray-200 bg-gray-50">
        <button @click="$emit('close')" class="btn-secondary">
          Закрыть
        </button>
      </div>
    </div>

    <!-- VIN Selector Modal -->
    <div v-if="showVinSelector" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60 p-4">
      <div class="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[80vh] overflow-hidden">
        <div class="p-4 border-b border-gray-200 flex items-center justify-between">
          <h4 class="font-semibold text-gray-900">Выбор автомобиля из базы данных</h4>
          <button @click="showVinSelector = false" class="text-gray-400 hover:text-gray-600">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>
        
        <div class="p-4 overflow-y-auto max-h-[60vh]">
          <div v-if="loadingAvailable" class="text-center py-4">
            <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          </div>
          
          <div v-else-if="availableVehicles.length === 0" class="text-center py-8 text-gray-500">
            Нет доступных автомобилей с подходящей комплектацией
          </div>
          
          <div v-else class="space-y-2">
            <button 
              v-for="av in availableVehicles" 
              :key="av.id"
              @click="selectVehicleFromDb(av)"
              class="w-full text-left p-3 border rounded-lg hover:bg-blue-50 hover:border-blue-500 transition-colors"
            >
              <div class="flex justify-between items-center">
                <div>
                  <div class="font-medium">{{ av.vin }}</div>
                  <div class="text-sm text-gray-600">
                    {{ av.mark_name }} {{ av.model_name }} | {{ av.color }} | {{ av.year }}
                  </div>
                </div>
                <div class="text-right">
                  <div class="font-medium text-green-600">{{ formatPrice(av.discount_price || av.base_price) }}</div>
                  <div class="text-xs text-gray-500">{{ av.status }}</div>
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AdminVehicle } from '~/types/admin'
import { formatSourcedApplicationNumber as formatApplicationNumber } from '~/features/applications/sourceType'

interface Dealer {
  id: string
  name: string
  company_name?: string
  phone?: string
}

interface Distributor {
  id: string
  name: string
}

const props = defineProps({
  application: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'saved'])

const config = useRuntimeConfig()
const { formatPrice } = useFormatPrice()

const vehicles = ref<AdminVehicle[]>([])
const dealers = ref<Dealer[]>([])
const distributors = ref<Distributor[]>([])
const loading = ref(true)
const saving = ref(false)

const editingVehicleId = ref<string | null>(null)
const editForm = reactive({
  vin: '',
  vehicle_id: null as string | null,
  dealer_id: null as string | null,
  distributor_id: null as string | null
})

const showVinSelector = ref(false)
const availableVehicles = ref<AdminVehicle[]>([])
const loadingAvailable = ref(false)

const getVehicleTitle = (vehicle: AdminVehicle) => {
  const mark = vehicle.mark_name || vehicle.mark_cyrillic || vehicle.mark_cyrillic_name
  const model = vehicle.model_name || vehicle.model_cyrillic || vehicle.model_cyrillic_name
  return [mark, model].filter(Boolean).join(' ') || 'Автомобиль'
}

const getVehicleSubtitle = (vehicle: AdminVehicle) => {
  const complectation = vehicle.complectation_name || vehicle.group_name || 'Комплектация не указана'
  const color = vehicle.color || 'Цвет не указан'
  const year = vehicle.year || vehicle.vehicle_year || 'Год не указан'
  return `${complectation} | ${color} | ${year}`
}

const SUPPORT_TYPE_LABELS: Record<string, string> = {
  down_payment_compensation: 'Поддержка первого взноса',
  vehicle_discount_dealer_compensation: 'Поддержка на ТС (поддержка дилеру)',
  vehicle_discount_dealer_invoice: 'Поддержка на ТС (уменьшение счета дилеру)',
  leasing_interest_compensation: 'Поддержка процентов по лизингу'
}

const hasSupportInfo = (vehicle: AdminVehicle) =>
  Boolean(vehicle.support_type || vehicle.support_amount || vehicle.support_program_info?.name)

const getSupportTitle = (vehicle: AdminVehicle) =>
  vehicle.support_program_info?.name || 'Применена поддержка'

const getSupportTypeLabel = (type?: string | null) =>
  type ? SUPPORT_TYPE_LABELS[type] || type : 'Поддержка'

const fetchVehicles = async () => {
  loading.value = true
  try {
    const [vehiclesRes, dealersRes, distributorsRes] = await Promise.all([
      $fetch(`/api/v1/admin/applications/${props.application.id}/vehicles`, {
        baseURL: config.public.apiBase,
        credentials: 'include'
      }),
      $fetch('/api/v1/admin/dealers', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      }),
      $fetch('/api/v1/admin/distributors', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    ])
    
    vehicles.value = (vehiclesRes as { vehicles: AdminVehicle[] }).vehicles || []
    dealers.value = (dealersRes as { dealers: Dealer[] }).dealers || []
    distributors.value = (distributorsRes as { distributors: Distributor[] }).distributors || []
  } catch (err: unknown) {
    console.error('Error fetching vehicles:', err)
  } finally {
    loading.value = false
  }
}

const startEdit = async (vehicle: AdminVehicle) => {
  editingVehicleId.value = vehicle.id
  editForm.vin = vehicle.assigned_vin || vehicle.vehicle_vin || ''
  editForm.vehicle_id = vehicle.vehicle_id ?? null
  editForm.dealer_id = vehicle.dealer_id ?? null
  editForm.distributor_id = vehicle.distributor_id ?? null
  
  // Load available vehicles for VIN selection
  loadingAvailable.value = true
  try {
    const response = await $fetch(`/api/v1/application-vehicles/${vehicle.id}/available-vins`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    availableVehicles.value = (response as { vehicles: AdminVehicle[] }).vehicles || []
  } catch (err: unknown) {
    console.error('Error fetching available vehicles:', err)
    availableVehicles.value = []
  } finally {
    loadingAvailable.value = false
  }
}

const cancelEdit = () => {
  editingVehicleId.value = null
  editForm.vin = ''
  editForm.vehicle_id = null
  editForm.dealer_id = null
  editForm.distributor_id = null
}

const selectVehicleFromDb = (vehicle: AdminVehicle) => {
  editForm.vehicle_id = vehicle.id
  editForm.vin = vehicle.vin || ''
  showVinSelector.value = false
}

const saveVehicleChanges = async (vehicleId: string) => {
  saving.value = true
  try {
    // Save VIN changes
    if (editForm.vehicle_id || editForm.vin) {
      await $fetch(`/api/v1/application-vehicles/${vehicleId}`, {
        method: 'PATCH',
        body: {
          vehicle_id: editForm.vehicle_id,
          vin: editForm.vehicle_id ? undefined : editForm.vin
        },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    }
    
    // Save dealer/distributor assignment
    if (editForm.dealer_id !== null || editForm.distributor_id !== null) {
      await $fetch(`/api/v1/admin/application-vehicles/${vehicleId}/assign`, {
        method: 'PUT',
        body: {
          dealer_id: editForm.dealer_id,
          distributor_id: editForm.distributor_id
        },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    }
    
    cancelEdit()
    await fetchVehicles()
    emit('saved')
  } catch (err: unknown) {
    console.error('Error saving vehicle changes:', err)
    const e = err as { data?: { error?: string } }
    alert(e.data?.error || 'Ошибка при сохранении изменений')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchVehicles()
})
</script>

<style scoped>
.z-60 {
  z-index: 60;
}
</style>
