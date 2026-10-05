<template>
  <Modal :show="isOpen" @close="$emit('close')" size="lg">
    <template #header>
      <h3 data-storefront-block="shared.form" class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
        Массовое редактирование
      </h3>
      <p data-storefront-block="shared.form" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">
        Выбрано автомобилей: {{ selectedVehicles.length }}
      </p>
    </template>

    <template #body>
      <div data-storefront-block="shared.form" class="space-y-6">
        <!-- Выбор типа операции -->
        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Тип операции
          </label>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <button
              @click="operationType = 'price'"
              :class="{
                'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)]': operationType === 'price',
                'bg-[color:rgb(var(--storefront-primary-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,229_231_235)/var(--tw-bg-opacity,1))]': operationType !== 'price'
              }"
              class="storefront-action-primary p-3 rounded-lg border text-center transition-colors"
            >
              <svg class="w-6 h-6 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"></path>
              </svg>
              <div class="text-sm font-medium">Цены</div>
            </button>
            
            <button
              @click="operationType = 'status'"
              :class="{
                'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)]': operationType === 'status',
                'bg-[color:rgb(var(--storefront-primary-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,229_231_235)/var(--tw-bg-opacity,1))]': operationType !== 'status'
              }"
              class="storefront-action-primary p-3 rounded-lg border text-center transition-colors"
            >
              <svg class="w-6 h-6 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              <div class="text-sm font-medium">Статус</div>
            </button>
            
            <button
              @click="operationType = 'availability'"
              :class="{
                'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)]': operationType === 'availability',
                'bg-[color:rgb(var(--storefront-primary-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,229_231_235)/var(--tw-bg-opacity,1))]': operationType !== 'availability'
              }"
              class="storefront-action-primary p-3 rounded-lg border text-center transition-colors"
            >
              <svg class="w-6 h-6 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
              </svg>
              <div class="text-sm font-medium">Доступность</div>
            </button>
          </div>
        </div>

        <!-- Настройки цены -->
        <div v-if="operationType === 'price'" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
              Тип изменения цены
            </label>
            <select
              v-model="priceOperation"
              class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
            >
              <option value="set">Установить фиксированную цену</option>
              <option value="increase_amount">Увеличить на сумму</option>
              <option value="decrease_amount">Уменьшить на сумму</option>
              <option value="increase_percent">Увеличить на процент</option>
              <option value="decrease_percent">Уменьшить на процент</option>
              <option value="set_discount">Установить выгоду</option>
              <option value="remove_discount">Убрать выгоду</option>
            </select>
          </div>

          <div v-if="priceOperation !== 'remove_discount'">
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
              {{ getPriceLabel() }}
            </label>
            <div class="relative">
              <input
                v-model="priceValue"
                type="number"
                :step="priceOperation.includes('percent') ? '0.1' : '1000'"
                :min="0"
                :max="priceOperation.includes('percent') ? '100' : undefined"
                class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
                :placeholder="getPricePlaceholder()"
              >
              <div class="absolute inset-y-0 right-3 flex items-center">
                <span class="text-[color:var(--storefront-text-muted,#6b7280)] text-sm">
                  {{ priceOperation.includes('percent') ? '%' : '₽' }}
                </span>
              </div>
            </div>
          </div>

          <!-- Предварительный просмотр изменений -->
          <div v-if="pricePreview.length > 0" class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
            <h4 class="font-medium text-[color:var(--storefront-title,#1e3a8a)] mb-2">Предварительный просмотр (первые 5):</h4>
            <div class="space-y-2 text-sm">
              <div v-for="preview in pricePreview.slice(0, 5)" :key="preview.id" class="flex justify-between">
                <span class="text-[color:var(--storefront-text,#1d4ed8)]">{{ preview.vin }}</span>
                <span class="text-[color:var(--storefront-text,#1e3a8a)]">
                  {{ formatPrice(preview.oldPrice) }} → {{ formatPrice(preview.newPrice) }}
                </span>
              </div>
              <div v-if="pricePreview.length > 5" class="text-[color:var(--storefront-text-muted,#2563eb)] font-medium">
                И еще {{ pricePreview.length - 5 }} автомобилей...
              </div>
            </div>
          </div>
        </div>

        <!-- Настройки статуса -->
        <div v-if="operationType === 'status'" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
              Новый статус
            </label>
            <select
              v-model="newStatus"
              class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
            >
              <option value="available">В наличии</option>
              <option value="reserved">Зарезервировано</option>
              <option value="sold">Продано</option>
            </select>
          </div>

          <div class="bg-[color:rgb(var(--storefront-warning-rgb,254_252_232)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
            <div class="flex">
              <svg class="w-5 h-5 text-[color:var(--storefront-warning-icon,#facc15)] mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 15.5c-.77.833.192 2.5 1.732 2.5z"></path>
              </svg>
              <div class="ml-3">
                <h3 class="text-sm font-medium text-[color:var(--storefront-warning-text,#854d0e)]">Внимание</h3>
                <div class="text-sm text-[color:var(--storefront-warning-text,#a16207)] mt-1">
                  Изменение статуса повлияет на {{ selectedVehicles.length }} автомобилей.
                  Статус "Продано" сделает автомобили недоступными для заказа.
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Настройки доступности -->
        <div v-if="operationType === 'availability'" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
              Доступность для заказа
            </label>
            <div class="flex space-x-4">
              <label class="flex items-center">
                <input
                  v-model="newAvailability"
                  type="radio"
                  :value="true"
                  class="storefront-control text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                >
                <span class="ml-2 text-sm text-[color:var(--storefront-text,#374151)]">Доступен</span>
              </label>
              <label class="flex items-center">
                <input
                  v-model="newAvailability"
                  type="radio"
                  :value="false"
                  class="storefront-control text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                >
                <span class="ml-2 text-sm text-[color:var(--storefront-text,#374151)]">Недоступен</span>
              </label>
            </div>
          </div>

          <div class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
            <div class="flex">
              <svg class="w-5 h-5 text-[color:var(--storefront-icon,#60a5fa)] mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              <div class="ml-3">
                <h3 class="text-sm font-medium text-[color:var(--storefront-title,#1e40af)]">Информация</h3>
                <div class="text-sm text-[color:var(--storefront-text,#1d4ed8)] mt-1">
                  Недоступные автомобили не будут отображаться в каталоге для клиентов,
                  но останутся видимыми в системе управления складом.
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Причина изменения -->
        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Комментарий к изменению (необязательно)
          </label>
          <textarea
            v-model="changeReason"
            rows="3"
            class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
            placeholder="Укажите причину массового изменения..."
          ></textarea>
        </div>
      </div>
    </template>

    <template #footer>
      <div data-storefront-block="shared.form" class="flex justify-between">
        <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Будет изменено: {{ selectedVehicles.length }} автомобилей
        </div>
        <div class="flex space-x-3">
          <button
            @click="$emit('close')"
            class="storefront-action-ghost px-4 py-2 text-[color:var(--storefront-ghost-foreground,#374151)] bg-[color:rgb(var(--storefront-ghost-rgb,229_231_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,209_213_219)/var(--tw-bg-opacity,1))] rounded-lg transition-colors"
          >
            Отменить
          </button>
          <button
            @click="applyChanges"
            :disabled="!canApply || loading"
            class="storefront-action-primary px-4 py-2 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span v-if="loading" class="inline-flex items-center">
              <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-[color:var(--storefront-primary-icon,#ffffff)]" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Применяем...
            </span>
            <span v-else>Применить изменения</span>
          </button>
        </div>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { PropType } from 'vue'
import { useFormatPrice } from '@/composables/useFormatPrice'
import { useToast } from '@/composables/useToast'
import type { BulkEditVehicle, PriceOperation } from '@/types'
import { useLogger } from '@/composables/useLogger'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  },
  selectedVehicles: {
    type: Array as PropType<Array<number | string>>,
    required: true
  }
})

const emit = defineEmits(['close', 'success'])

const { formatPrice } = useFormatPrice()
const { showToast } = useToast()
const logger = useLogger()

// Реактивные данные
const loading = ref(false)
const operationType = ref('price')
const priceOperation = ref('set')
const priceValue = ref('')
const newStatus = ref('available')
const newAvailability = ref(true)
const changeReason = ref('')
const vehicleDetails = ref<BulkEditVehicle[]>([])

// Вычисляемые свойства
const canApply = computed(() => {
  if (operationType.value === 'price' && priceOperation.value !== 'remove_discount') {
    return priceValue.value && Number(priceValue.value) > 0
  }
  return true
})

const pricePreview = computed(() => {
  if (operationType.value !== 'price' || !priceValue.value || vehicleDetails.value.length === 0) {
    return []
  }
  
  return vehicleDetails.value.map(vehicle => {
    const oldPrice = vehicle.base_price
    let newPrice = oldPrice
    
    const value = Number(priceValue.value)
    
    switch (priceOperation.value) {
      case 'set':
        newPrice = value
        break
      case 'increase_amount':
        newPrice = oldPrice + value
        break
      case 'decrease_amount':
        newPrice = Math.max(0, oldPrice - value)
        break
      case 'increase_percent':
        newPrice = oldPrice * (1 + value / 100)
        break
      case 'decrease_percent':
        newPrice = oldPrice * (1 - value / 100)
        break
      case 'set_discount':
        newPrice = vehicle.base_price - value
        break
    }
    
    return {
      id: vehicle.id,
      vin: vehicle.vin,
      oldPrice,
      newPrice: Math.round(newPrice)
    }
  })
})

// Методы
const getPriceLabel = (): string => {
  const labels: Record<string, string> = {
    set: 'Новая цена',
    increase_amount: 'Сумма увеличения',
    decrease_amount: 'Сумма уменьшения',
    increase_percent: 'Процент увеличения',
    decrease_percent: 'Процент уменьшения',
    set_discount: 'Размер выгоды'
  }
  return labels[priceOperation.value] || 'Значение'
}

const getPricePlaceholder = (): string => {
  const placeholders: Record<string, string> = {
    set: 'Введите новую цену',
    increase_amount: 'Введите сумму в рублях',
    decrease_amount: 'Введите сумму в рублях',
    increase_percent: 'Введите процент (например, 10)',
    decrease_percent: 'Введите процент (например, 15)',
    set_discount: 'Введите размер выгоды в рублях'
  }
  return placeholders[priceOperation.value] || 'Введите значение'
}

const fetchVehicleDetails = async () => {
  if (props.selectedVehicles.length === 0) return
  
  try {
    const query = props.selectedVehicles
      .map((id) => `ids=${encodeURIComponent(String(id))}`)
      .join('&')
    const response = await $fetch(`/api/v1/distributor/vehicles?${query}`)

    const typedResponse = response as { vehicles?: BulkEditVehicle[] }
    vehicleDetails.value = typedResponse.vehicles || []
  } catch (err) {
    logger.error('Error fetching vehicle details:', err)
  }
}

const applyChanges = async () => {
  try {
    loading.value = true

    const patch: Record<string, unknown> = {}
    if (operationType.value === 'price') {
      if (priceOperation.value === 'set') {
        patch.base_price = Number(priceValue.value)
      } else if (priceOperation.value === 'set_discount') {
        patch.discount_price = Number(priceValue.value)
      } else if (priceOperation.value === 'remove_discount') {
        patch.discount_price = null
      } else if (priceOperation.value === 'increase_amount') {
        patch.base_price = Number(priceValue.value)
      } else if (priceOperation.value === 'decrease_amount') {
        patch.base_price = Number(priceValue.value)
      } else if (priceOperation.value === 'increase_percent') {
        patch.base_price = Number(priceValue.value)
      } else if (priceOperation.value === 'decrease_percent') {
        patch.base_price = Number(priceValue.value)
      }
    } else if (operationType.value === 'status') {
      patch.status = newStatus.value
    } else if (operationType.value === 'availability') {
      patch.is_available = newAvailability.value
    }

    await $fetch('/api/v1/distributor/vehicles', {
      method: 'PATCH',
      body: {
        ids: props.selectedVehicles,
        patch,
      },
    })

    showToast.success(`Успешно обновлено ${props.selectedVehicles.length} автомобилей`)
    emit('success')

  } catch (err) {
    logger.error('Error applying bulk changes:', err)
    showToast.error('Ошибка при массовом обновлении')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  operationType.value = 'price'
  priceOperation.value = 'set'
  priceValue.value = ''
  newStatus.value = 'available'
  newAvailability.value = true
  changeReason.value = ''
  vehicleDetails.value = []
}

// Наблюдатели
watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    fetchVehicleDetails()
  } else {
    resetForm()
  }
})

watch(() => props.selectedVehicles, () => {
  if (props.isOpen) {
    fetchVehicleDetails()
  }
})
</script>
