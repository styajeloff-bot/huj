<template>
  <Modal :show="isOpen" @close="$emit('close')" size="xl">
    <template #header>
      <div class="flex items-center justify-between">
        <h3 class="text-lg font-semibold text-gray-900">
          Детали автомобиля
        </h3>
        <div class="flex space-x-2">
          <button
            @click="$emit('edit', vehicle)"
            class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1 rounded text-sm transition-colors"
          >
            Редактировать
          </button>
        </div>
      </div>
    </template>

    <template #body>
      <div v-if="vehicle" class="space-y-6">
        <!-- Изображения -->
        <div v-if="vehicle.images && vehicle.images.length > 0" class="space-y-4">
          <h4 class="font-semibold text-gray-900">Фотографии</h4>
          <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div
              v-for="(image, index) in vehicle.images"
              :key="index"
              class="aspect-w-4 aspect-h-3 bg-gray-200 rounded-lg overflow-hidden cursor-pointer"
              @click="openImageModal(image, index)"
            >
              <img :src="String(image)" :alt="`Фото ${Number(index) + 1}`" class="w-full h-full object-cover">
            </div>
          </div>
        </div>

        <!-- Основная информация -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="space-y-4">
            <h4 class="font-semibold text-gray-900">Основная информация</h4>
            
            <div class="space-y-3">
              <div class="flex justify-between">
                <span class="text-gray-600">VIN:</span>
                <span class="font-mono font-medium">{{ vehicle.vin }}</span>
              </div>
              
              <div class="flex justify-between">
                <span class="text-gray-600">Марка:</span>
                <span class="font-medium">{{ vehicle.mark_name || vehicle.mark_id }}</span>
              </div>
              
              <div class="flex justify-between">
                <span class="text-gray-600">Модель:</span>
                <span class="font-medium">{{ vehicle.model_name || vehicle.model_id }}</span>
              </div>
              
              <div v-if="vehicle.generation_name" class="flex justify-between">
                <span class="text-gray-600">Поколение:</span>
                <span class="font-medium">{{ vehicle.generation_name }}</span>
              </div>
              
              <div class="flex justify-between">
                <span class="text-gray-600">Год выпуска:</span>
                <span class="font-medium">{{ vehicle.year }}</span>
              </div>
              
              <div v-if="vehicle.color" class="flex justify-between">
                <span class="text-gray-600">Цвет:</span>
                <span class="font-medium">{{ vehicle.color }}</span>
              </div>
              
              <div class="flex justify-between">
                <span class="text-gray-600">Статус:</span>
                <span :class="getStatusClass(vehicle.status)" class="px-2 py-1 text-xs font-medium rounded-full">
                  {{ vehicleStockStatusLabel(vehicle) }}
                </span>
                <p v-if="vehicle.reserved_until" class="mt-1 text-xs">Бронь до {{ new Date(vehicle.reserved_until).toLocaleDateString('ru-RU') }}</p>
              </div>
            </div>
          </div>

          <div class="space-y-4">
            <h4 class="font-semibold text-gray-900">Ценовая информация</h4>
            
            <div class="space-y-3">
              <div class="flex justify-between">
                <span class="text-gray-600">Базовая цена:</span>
                <span class="font-medium">{{ formatPrice(vehicle.base_price) }}</span>
              </div>
              
              <div v-if="hasDiscountPrice" class="flex justify-between">
                <span class="text-gray-600">Цена с выгодой:</span>
                <span class="font-medium text-green-600">{{ formatPrice(vehicle.discount_price) }}</span>
              </div>

              <div v-if="showSpecialPrice" class="flex justify-between">
                <span class="text-gray-600">Специальная цена:</span>
                <span class="font-medium">{{ formatPrice(vehicle.special_price) }}</span>
              </div>
              
              <div v-if="hasDiscountPrice" class="flex justify-between">
                <span class="text-gray-600">Размер выгоды:</span>
                <span class="font-medium text-red-600">
                  {{ formatPrice(discountAmount) }}
                  ({{ discountPercent }}%)
                </span>
              </div>
              
              <div class="flex justify-between border-t pt-3">
                <span class="text-gray-600 font-semibold">Итоговая цена:</span>
                <span class="font-bold text-lg text-blue-600">
                  {{ formatPrice(vehicle.base_price) }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Технические характеристики -->
        <div v-if="hasSpecs" class="space-y-4">
          <h4 class="font-semibold text-gray-900">Технические характеристики</h4>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div v-if="vehicle.body_type" class="flex justify-between">
              <span class="text-gray-600">Тип кузова:</span>
              <span class="font-medium">{{ vehicle.body_type }}</span>
            </div>
            
            <div v-if="vehicle.doors_count" class="flex justify-between">
              <span class="text-gray-600">Количество дверей:</span>
              <span class="font-medium">{{ vehicle.doors_count }}</span>
            </div>
            
            <div v-if="vehicle.engine_volume" class="flex justify-between">
              <span class="text-gray-600">Объем двигателя:</span>
              <span class="font-medium">{{ vehicle.engine_volume }} л</span>
            </div>
            
            <div v-if="vehicle.engine_power" class="flex justify-between">
              <span class="text-gray-600">Мощность:</span>
              <span class="font-medium">{{ vehicle.engine_power }} л.с.</span>
            </div>
            
            <div v-if="vehicle.fuel_type" class="flex justify-between">
              <span class="text-gray-600">Тип топлива:</span>
              <span class="font-medium">{{ vehicle.fuel_type }}</span>
            </div>
            
            <div v-if="vehicle.transmission" class="flex justify-between">
              <span class="text-gray-600">Коробка передач:</span>
              <span class="font-medium">{{ vehicle.transmission }}</span>
            </div>
            
            <div v-if="vehicle.drive_type" class="flex justify-between">
              <span class="text-gray-600">Привод:</span>
              <span class="font-medium">{{ vehicle.drive_type }}</span>
            </div>
          </div>
        </div>

        <!-- Дистрибьютор -->
        <div class="space-y-4">
          <h4 class="font-semibold text-gray-900">Информация о дистрибьюторе</h4>
          
          <div class="space-y-3">
            <div v-if="vehicle.distributor_name" class="flex justify-between">
              <span class="text-gray-600">Дистрибьютор:</span>
              <span class="font-medium">{{ vehicle.distributor_name }}</span>
            </div>
            
            <div v-if="vehicle.distributor_company_name" class="flex justify-between">
              <span class="text-gray-600">Компания:</span>
              <span class="font-medium">{{ vehicle.distributor_company_name }}</span>
            </div>
          </div>
        </div>

        <!-- Системная информация -->
        <div class="space-y-4">
          <h4 class="font-semibold text-gray-900">Системная информация</h4>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div class="flex justify-between">
              <span class="text-gray-600">Добавлен:</span>
              <span class="font-medium">{{ formatDate(vehicle.created_at) }}</span>
            </div>
            
            <div v-if="vehicle.updated_at && vehicle.updated_at !== vehicle.created_at" class="flex justify-between">
              <span class="text-gray-600">Обновлен:</span>
              <span class="font-medium">{{ formatDate(vehicle.updated_at) }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-gray-600">ID в системе:</span>
              <span class="font-mono font-medium">{{ vehicle.id }}</span>
            </div>
            
            <div class="flex justify-between">
              <span class="text-gray-600">Доступен для заказа:</span>
              <span :class="vehicle.is_available ? 'text-green-600' : 'text-red-600'" class="font-medium">
                {{ vehicle.is_available ? 'Да' : 'Нет' }}
              </span>
            </div>
          </div>
        </div>

        <!-- История изменений -->
        <div v-if="vehicleHistory.length > 0" class="space-y-4">
          <h4 class="font-semibold text-gray-900">История изменений</h4>
          
          <div class="space-y-3 max-h-64 overflow-y-auto">
            <div
              v-for="record in vehicleHistory"
              :key="record.id"
              class="flex justify-between items-start p-3 bg-gray-50 rounded-lg"
            >
              <div>
                <div class="font-medium text-sm">{{ record.action }}</div>
                <div class="text-xs text-gray-600">{{ formatDate(record.created_at) }}</div>
              </div>
              <div class="text-xs text-gray-500">
                {{ record.user_name }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end space-x-3">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-gray-700 bg-gray-200 hover:bg-gray-300 rounded-lg transition-colors"
        >
          Закрыть
        </button>
        <button
          @click="$emit('edit', vehicle)"
          class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
        >
          Редактировать
        </button>
      </div>
    </template>
  </Modal>

  <!-- Модальное окно просмотра изображения -->
  <Modal :show="showImageModal" @close="showImageModal = false" size="lg">
    <template #body>
      <div class="text-center">
        <img
          v-if="selectedImage"
          :src="selectedImage"
          :alt="`Фото ${selectedImageIndex + 1}`"
          class="max-w-full max-h-96 mx-auto"
        >
        <div v-if="vehicle && vehicle.images && vehicle.images.length > 1" class="flex justify-center space-x-2 mt-4">
          <button
            v-for="(image, index) in vehicle.images"
            :key="index"
            @click="selectImage(image, index)"
            :class="{
              'ring-2 ring-blue-500': index === selectedImageIndex,
              'opacity-60': index !== selectedImageIndex
            }"
            class="w-16 h-12 bg-gray-200 rounded overflow-hidden"
          >
            <img :src="String(image)" :alt="`Миниатюра ${Number(index) + 1}`" class="w-full h-full object-cover">
          </button>
        </div>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { vehicleStockStatusLabel } from '~/utils/vehicleStockStatus'
import { ref, computed, onMounted } from 'vue'
import { useFormatPrice } from '@/composables/useFormatPrice'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  },
  vehicle: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'edit'])

const { formatPrice } = useFormatPrice()

// Реактивные данные
import type { VehicleHistoryRecord } from '~/types/admin'

const vehicleHistory = ref<VehicleHistoryRecord[]>([])
const showImageModal = ref(false)
const selectedImage = ref('')
const selectedImageIndex = ref(0)

// Вычисляемые свойства
const hasSpecs = computed(() => {
  if (!props.vehicle) return false
  return props.vehicle.body_type || 
         props.vehicle.doors_count || 
         props.vehicle.engine_volume || 
         props.vehicle.engine_power || 
         props.vehicle.fuel_type || 
         props.vehicle.transmission || 
         props.vehicle.drive_type
})

const toFiniteNumber = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const basePriceNumber = computed(() => toFiniteNumber(props.vehicle?.base_price))
const discountPriceNumber = computed(() => toFiniteNumber(props.vehicle?.discount_price))
const specialPriceNumber = computed(() => toFiniteNumber(props.vehicle?.special_price))

const hasDiscountPrice = computed(() => {
  const base = basePriceNumber.value
  const discount = discountPriceNumber.value
  return base !== null && discount !== null && discount > 0 && discount < base
})

const showSpecialPrice = computed(() => {
  const special = specialPriceNumber.value
  if (special === null) return false
  const discount = discountPriceNumber.value
  return discount === null || special !== discount
})

const discountAmount = computed(() => {
  const base = basePriceNumber.value ?? 0
  const discount = discountPriceNumber.value ?? base
  return Math.max(0, base - discount)
})

const discountPercent = computed(() => {
  const base = basePriceNumber.value
  const discount = discountPriceNumber.value
  if (!base || discount === null) return 0
  return Math.round((1 - discount / base) * 100)
})

// Методы
const getStatusClass = (status: string) => {
  const classes: Record<string, string> = {
    available: 'bg-green-100 text-green-800',
    reserved: 'bg-yellow-100 text-yellow-800',
    sold: 'bg-gray-100 text-gray-800'
  }
  return classes[status] || 'bg-gray-100 text-gray-800'
}



const formatDate = (dateString: string | undefined) => {
  if (!dateString) return ''
  return new Date(dateString).toLocaleString('ru-RU')
}

const openImageModal = (image: string | number, index: string | number) => {
  selectedImage.value = String(image)
  selectedImageIndex.value = Number(index)
  showImageModal.value = true
}

const selectImage = (image: string | number, index: string | number) => {
  selectedImage.value = String(image)
  selectedImageIndex.value = Number(index)
}

const fetchVehicleHistory = async () => {
  if (!props.vehicle?.id) return
  
  try {
    const response = await $fetch(`/api/v1/distributor/vehicles/${props.vehicle.id}/history`)
    vehicleHistory.value = (response as { history: VehicleHistoryRecord[] }).history || []
  } catch (err: unknown) {
    console.error('Error fetching vehicle history:', err)
  }
}

// Наблюдатели
watch(() => props.isOpen, (isOpen) => {
  if (isOpen && props.vehicle) {
    fetchVehicleHistory()
  }
})
</script>
