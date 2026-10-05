<template>
  <Modal :show="isOpen" @close="$emit('close')" size="lg">
    <div class="p-6">
      <div class="flex items-center justify-between mb-6">
        <h3 class="text-xl font-semibold text-gray-900">
          {{ isEditing ? 'Редактировать автомобиль' : 'Добавить автомобиль' }}
        </h3>
        <button
          @click="$emit('close')"
          class="text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>

      <form @submit.prevent="handleSubmit" class="space-y-6">
        <!-- Основная информация -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Марка <span class="text-red-500">*</span>
            </label>
            <select
              v-model="form.mark_id"
              @change="onMarkChange"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">Выберите марку</option>
              <option v-for="mark in marks" :key="mark.id" :value="mark.id">
                {{ mark.name }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Модель <span class="text-red-500">*</span>
            </label>
            <select
              v-model="form.model_id"
              required
              :disabled="!form.mark_id"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100"
            >
              <option value="">Выберите модель</option>
              <option v-for="model in models" :key="model.id" :value="model.id">
                {{ model.name }}
              </option>
            </select>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Год выпуска <span class="text-red-500">*</span>
            </label>
            <input
              v-model.number="form.year"
              type="number"
              :min="1900"
              :max="new Date().getFullYear() + 1"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Цена <span class="text-red-500">*</span>
            </label>
            <input
              v-model.number="form.base_price"
              type="number"
              min="0"
              step="any"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>
        </div>

        <!-- Дополнительная информация -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              VIN номер
            </label>
            <input
              v-model="form.vin"
              type="text"
              maxlength="17"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Цена с выгодой
            </label>
            <input
              v-model.number="form.discount_price"
              type="number"
              min="0"
              step="any"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Специальная цена
            </label>
            <input
              v-model.number="form.special_price"
              type="number"
              min="0"
              step="any"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>
        </div>

        <!-- Дополнительные поля -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              ID поколения
            </label>
            <input
              v-model="form.generation_id"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              ID конфигурации
            </label>
            <input
              v-model="form.configuration_id"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              ID комплектации
            </label>
            <input
              v-model="form.complectation_id"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>
        </div>

        <!-- Дополнительные поля -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Цвет
            </label>
            <input
              v-model="form.color"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Статус
            </label>
            <select
              v-model="form.status"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="available">В наличии</option>
              <option value="reserved">Зарезервировано</option>
              <option value="sold">Продано</option>
              <option value="maintenance">На обслуживании</option>
            </select>
          </div>
        </div>

        <!-- Кнопки -->
        <div class="flex justify-end space-x-3 pt-6 border-t border-gray-200">
          <button
            type="button"
            @click="$emit('close')"
            class="px-4 py-2 text-gray-700 bg-gray-200 hover:bg-gray-300 rounded-lg transition-colors"
          >
            Отмена
          </button>
          <button
            type="submit"
            :disabled="loading"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span v-if="loading" class="flex items-center">
              <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              {{ isEditing ? 'Обновление...' : 'Добавление...' }}
            </span>
            <span v-else>
              {{ isEditing ? 'Обновить' : 'Добавить' }}
            </span>
          </button>
        </div>
      </form>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import { useLogger } from '@/composables/useLogger'

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  vehicle: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close', 'success'])

const { showToast } = useToast()
const logger = useLogger()

import type { VehicleMark, VehicleModel } from '~/types/admin'

const loading = ref(false)
const marks = ref<VehicleMark[]>([])
const models = ref<VehicleModel[]>([])

const isEditing = computed(() => !!props.vehicle)

const form = ref({
  mark_id: '',
  model_id: '',
  year: new Date().getFullYear(),
  vin: '',
  base_price: 0,
  special_price: null as number | null,
  discount_price: null as number | null,
  color: '',
  status: 'available',
  generation_id: '',
  configuration_id: '',
  complectation_id: ''
})

// Загружаем марки
const fetchMarks = async () => {
  try {
    const response = await $fetch<{ marks?: VehicleMark[] }>('/api/v1/cars/facets', {
      params: { fields: 'marks' },
    })
    marks.value = response.marks || []
  } catch (error: unknown) {
    logger.error('Error fetching marks:', error)
    showToast.error('Ошибка при загрузке марок')
  }
}

// Загружаем модели для выбранной марки
const fetchModels = async (markId: string) => {
  if (!markId) {
    models.value = []
    return
  }

  try {
    const response = await $fetch<{ models?: VehicleModel[] }>('/api/v1/cars/facets', {
      params: { fields: 'models', mark_id: markId },
    })
    models.value = response.models || []
  } catch (error: unknown) {
    logger.error('Error fetching models:', error)
    showToast.error('Ошибка при загрузке моделей')
  }
}

const onMarkChange = () => {
  form.value.model_id = ''
  fetchModels(form.value.mark_id)
}

const handleSubmit = async () => {
  try {
    loading.value = true

    const url = isEditing.value 
      ? `/api/v1/distributor/vehicles/${props.vehicle.id}`
      : '/api/v1/distributor/vehicles'
    
    const method = isEditing.value ? 'PUT' : 'POST'

    const response = await $fetch(url, {
      method,
      body: form.value
    })

    const data = response as { message?: string }
    showToast.success(data.message || 'Автомобиль сохранен')
    emit('success')
    emit('close')

  } catch (error: unknown) {
    logger.error('Error saving vehicle:', error)
    const e = error as { data?: { error?: string } }
    showToast.error(e.data?.error || 'Ошибка при сохранении автомобиля')
  } finally {
    loading.value = false
  }
}

// Сброс формы
const resetForm = () => {
  form.value = {
    mark_id: '',
    model_id: '',
    year: new Date().getFullYear(),
    vin: '',
    base_price: 0,
    special_price: null,
    discount_price: null,
    color: '',
    status: 'available',
    generation_id: '',
    configuration_id: '',
    complectation_id: ''
  }
  models.value = []
}

// Заполнение формы при редактировании
const fillForm = () => {
  if (props.vehicle) {
    const rawPrice = props.vehicle.price || props.vehicle.base_price || 0
    const rawSpecialPrice = props.vehicle.special_price
    const rawDiscountPrice = props.vehicle.discount_price
    
    form.value = {
      mark_id: props.vehicle.mark_id || '',
      model_id: props.vehicle.model_id || '',
      year: Number(props.vehicle.year) || new Date().getFullYear(),
      vin: props.vehicle.vin || '',
      base_price: Number(rawPrice) || 0,
      special_price: rawSpecialPrice != null ? Number(rawSpecialPrice) : null,
      discount_price: rawDiscountPrice != null ? Number(rawDiscountPrice) : null,
      color: props.vehicle.color || '',
      status: props.vehicle.status || 'available',
      generation_id: props.vehicle.generation_id || '',
      configuration_id: props.vehicle.configuration_id || '',
      complectation_id: props.vehicle.complectation_id || ''
    }
    
    if (form.value.mark_id) {
      fetchModels(form.value.mark_id)
    }
  }
}

// Отслеживаем изменения пропсов
watch(() => props.vehicle, () => {
  if (props.vehicle) {
    fillForm()
  } else {
    resetForm()
  }
}, { immediate: true })

watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    if (props.vehicle) {
      fillForm()
    } else {
      resetForm()
    }
  }
})

onMounted(() => {
  fetchMarks()
})
</script>
