<template>
  <Modal :show="isOpen" @close="$emit('close')" size="lg">
    <template #header>
      <h3 class="text-lg font-semibold text-gray-900">
        Инвентаризация склада
      </h3>
      <p class="text-sm text-gray-600 mt-1">
        Проверка и подтверждение наличия автомобилей на складе
      </p>
    </template>

    <template #body>
      <div class="space-y-6">
        <!-- Выбор типа инвентаризации -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-3">
            Тип инвентаризации
          </label>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <button
              @click="inventoryType = 'full'"
              :class="{
                'bg-blue-600 text-white border-blue-600': inventoryType === 'full',
                'bg-white text-gray-700 border-gray-300 hover:bg-gray-50': inventoryType !== 'full'
              }"
              class="p-4 border-2 rounded-lg text-left transition-colors"
            >
              <div class="flex items-center">
                <svg class="w-6 h-6 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"></path>
                </svg>
                <div>
                  <div class="font-medium">Полная инвентаризация</div>
                  <div class="text-sm opacity-75">Проверка всех автомобилей</div>
                </div>
              </div>
            </button>

            <button
              @click="inventoryType = 'selective'"
              :class="{
                'bg-blue-600 text-white border-blue-600': inventoryType === 'selective',
                'bg-white text-gray-700 border-gray-300 hover:bg-gray-50': inventoryType !== 'selective'
              }"
              class="p-4 border-2 rounded-lg text-left transition-colors"
            >
              <div class="flex items-center">
                <svg class="w-6 h-6 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.586-3.586a2 2 0 112.828 2.828l-8.586 8.586a1 1 0 01-.707.293H8a1 1 0 01-1-1v-2.828a1 1 0 01.293-.707l8.586-8.586z"></path>
                </svg>
                <div>
                  <div class="font-medium">Выборочная проверка</div>
                  <div class="text-sm opacity-75">Проверка выбранных автомобилей</div>
                </div>
              </div>
            </button>
          </div>
        </div>

        <!-- Фильтры для выборочной проверки -->
        <div v-if="inventoryType === 'selective'" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Критерии отбора
            </label>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <select
                v-model="filters.brand"
                class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">Все марки</option>
                <option v-for="brand in brands" :key="brand" :value="brand">{{ brand }}</option>
              </select>

              <select
                v-model="filters.status"
                class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">Все статусы</option>
                <option value="available">В наличии</option>
                <option value="reserved">Зарезервировано</option>
              </select>

              <input
                v-model="filters.dateFrom"
                type="date"
                class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Дата добавления от"
              >

              <input
                v-model="filters.dateTo"
                type="date"
                class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Дата добавления до"
              >
            </div>
          </div>

          <div>
            <label class="flex items-center">
              <input
                v-model="filters.onlyDiscrepancies"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Только автомобили с расхождениями в предыдущих проверках</span>
            </label>
          </div>
        </div>

        <!-- Информация о предыдущей инвентаризации -->
        <div v-if="lastInventory" class="bg-gray-50 p-4 rounded-lg">
          <h4 class="font-medium text-gray-900 mb-2">Последняя инвентаризация</h4>
          <div class="text-sm text-gray-600 space-y-1">
            <div>Дата: {{ formatDate(lastInventory.date) }}</div>
            <div>Проверено: {{ lastInventory.checked }} автомобилей</div>
            <div>Расхождений: {{ lastInventory.discrepancies }}</div>
            <div>Ответственный: {{ lastInventory.responsible }}</div>
          </div>
        </div>

        <!-- Настройки проверки -->
        <div class="space-y-4">
          <h4 class="font-medium text-gray-900">Настройки проверки</h4>
          
          <div class="space-y-3">
            <label class="flex items-center">
              <input
                v-model="settings.checkPhysicalPresence"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Проверить физическое наличие</span>
            </label>

            <label class="flex items-center">
              <input
                v-model="settings.checkCondition"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Проверить состояние автомобиля</span>
            </label>

            <label class="flex items-center">
              <input
                v-model="settings.checkDocuments"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Проверить документы</span>
            </label>

            <label class="flex items-center">
              <input
                v-model="settings.updatePrices"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Обновить рыночные цены</span>
            </label>

            <label class="flex items-center">
              <input
                v-model="settings.takePhotos"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Сделать новые фотографии</span>
            </label>
          </div>
        </div>

        <!-- Ответственные лица -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            Ответственные за проведение инвентаризации
          </label>
          <div class="space-y-2">
            <div v-for="(person, index) in responsiblePersons" :key="index" class="flex items-center space-x-2">
              <input
                v-model="person.name"
                type="text"
                class="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Имя и должность"
              >
              <input
                v-model="person.phone"
                type="tel"
                class="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Телефон"
              >
              <button
                @click="removeResponsiblePerson(index)"
                class="text-red-600 hover:text-red-800"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                </svg>
              </button>
            </div>
            <button
              @click="addResponsiblePerson"
              class="text-blue-600 hover:text-blue-800 text-sm"
            >
              + Добавить ответственного
            </button>
          </div>
        </div>

        <!-- Комментарий -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            Комментарий к инвентаризации
          </label>
          <textarea
            v-model="comment"
            rows="3"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Укажите цель проведения инвентаризации, особые условия..."
          ></textarea>
        </div>

        <!-- Прогресс инвентаризации -->
        <div v-if="inventoryInProgress" class="space-y-4">
          <div class="bg-blue-50 p-4 rounded-lg">
            <div class="flex items-center">
              <svg class="animate-spin w-5 h-5 text-blue-600 mr-3" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <div>
                <div class="text-sm font-medium text-blue-800">
                  {{ inventoryStatus }}
                </div>
                <div v-if="inventoryProgress.total > 0" class="text-sm text-blue-700">
                  Проверено: {{ inventoryProgress.checked }} из {{ inventoryProgress.total }}
                </div>
              </div>
            </div>
          </div>

          <!-- Прогресс-бар -->
          <div v-if="inventoryProgress.total > 0" class="w-full bg-gray-200 rounded-full h-2">
            <div
              class="bg-blue-600 h-2 rounded-full transition-all duration-300"
              :style="{ width: `${(inventoryProgress.checked / inventoryProgress.total) * 100}%` }"
            ></div>
          </div>

          <!-- Текущие расхождения -->
          <div v-if="currentDiscrepancies.length > 0" class="bg-yellow-50 p-4 rounded-lg">
            <h4 class="text-sm font-medium text-yellow-800 mb-2">Обнаружены расхождения:</h4>
            <div class="space-y-1 text-sm text-yellow-700 max-h-32 overflow-y-auto">
              <div v-for="discrepancy in currentDiscrepancies" :key="discrepancy.id">
                VIN {{ discrepancy.vin }}: {{ discrepancy.issue }}
              </div>
            </div>
          </div>
        </div>

        <!-- Результаты инвентаризации -->
        <div v-if="inventoryResults" class="space-y-4">
          <div class="bg-green-50 p-4 rounded-lg">
            <div class="flex">
              <svg class="w-5 h-5 text-green-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              <div class="ml-3">
                <h3 class="text-sm font-medium text-green-800">Инвентаризация завершена</h3>
                <div class="text-sm text-green-700 mt-1">
                  <div>Проверено: {{ inventoryResults.checked }} автомобилей</div>
                  <div>Подтверждено: {{ inventoryResults.confirmed }} автомобилей</div>
                  <div>Расхождений: {{ inventoryResults.discrepancies }} записей</div>
                  <div>Обновлено: {{ inventoryResults.updated }} записей</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Детали расхождений -->
          <div v-if="inventoryResults.discrepancyDetails && inventoryResults.discrepancyDetails.length > 0" class="bg-red-50 p-4 rounded-lg">
            <h4 class="text-sm font-medium text-red-800 mb-2">Детали расхождений:</h4>
            <div class="space-y-1 text-sm text-red-700 max-h-32 overflow-y-auto">
              <div v-for="detail in inventoryResults.discrepancyDetails" :key="detail.id">
                VIN {{ detail.vin }}: {{ detail.issue }}
              </div>
            </div>
          </div>

          <!-- Действия после инвентаризации -->
          <div class="flex space-x-2">
            <button
              @click="generateReport"
              class="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
            >
              Сформировать отчет
            </button>
            <button
              @click="exportResults"
              class="flex-1 bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg transition-colors"
            >
              Экспорт результатов
            </button>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-between">
        <div v-if="inventoryResults" class="text-sm text-gray-600">
          Инвентаризация завершена
        </div>
        <div v-else-if="inventoryInProgress" class="text-sm text-blue-600">
          Выполняется инвентаризация...
        </div>
        <div v-else class="text-sm text-gray-600">
          {{ inventoryType === 'full' ? 'Полная проверка всех автомобилей' : 'Выборочная проверка' }}
        </div>
        
        <div class="flex space-x-3">
          <button
            @click="$emit('close')"
            :disabled="inventoryInProgress"
            class="px-4 py-2 text-gray-700 bg-gray-200 hover:bg-gray-300 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ inventoryResults ? 'Закрыть' : 'Отменить' }}
          </button>
          <button
            v-if="!inventoryInProgress && !inventoryResults"
            @click="startInventory"
            :disabled="!canStartInventory"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Начать инвентаризацию
          </button>
          <button
            v-if="inventoryResults"
            @click="resetInventory"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            Новая инвентаризация
          </button>
        </div>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import { useLogger } from '@/composables/useLogger'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  }
})

const emit = defineEmits(['close', 'success'])

const { showToast } = useToast()
const logger = useLogger()

// Реактивные данные
const inventoryType = ref('full')
const inventoryInProgress = ref(false)
const inventoryStatus = ref('')
const inventoryProgress = ref({ checked: 0, total: 0 })
import type { InventoryResults, InventoryDiscrepancy, LastInventory } from '~/types/admin'

const inventoryResults = ref<InventoryResults | null>(null)
const currentDiscrepancies = ref<InventoryDiscrepancy[]>([])
const lastInventory = ref<LastInventory | null>(null)
const brands = ref<string[]>([])

// Фильтры
const filters = ref({
  brand: '',
  status: '',
  dateFrom: '',
  dateTo: '',
  onlyDiscrepancies: false
})

// Настройки
const settings = ref({
  checkPhysicalPresence: true,
  checkCondition: false,
  checkDocuments: false,
  updatePrices: false,
  takePhotos: false
})

// Ответственные лица
const responsiblePersons = ref([
  { name: '', phone: '' }
])

const comment = ref('')

// Вычисляемые свойства
const canStartInventory = computed(() => {
  return responsiblePersons.value.some(person => person.name.trim() !== '')
})

// Методы
const addResponsiblePerson = () => {
  responsiblePersons.value.push({ name: '', phone: '' })
}

const removeResponsiblePerson = (index: number) => {
  if (responsiblePersons.value.length > 1) {
    responsiblePersons.value.splice(index, 1)
  }
}

const formatDate = (dateString: string | undefined) => {
  if (!dateString) return ''
  return new Date(dateString).toLocaleString('ru-RU')
}

const fetchLastInventory = async () => {
  try {
    const response = await $fetch('/api/v1/distributor/inventory/last')
    lastInventory.value = (response as { inventory: LastInventory }).inventory
  } catch (_err: unknown) {
    // Не критичная ошибка
  }
}

const fetchBrands = async () => {
  try {
    const response = await $fetch('/api/v1/distributor/vehicles/brands')
    brands.value = (response as { brands: string[] }).brands
  } catch (err: unknown) {
    logger.error('Error fetching brands:', err)
  }
}

const startInventory = async () => {
  try {
    inventoryInProgress.value = true
    inventoryStatus.value = 'Подготовка к инвентаризации...'
    inventoryProgress.value = { checked: 0, total: 0 }
    currentDiscrepancies.value = []
    
    const payload = {
      type: inventoryType.value,
      filters: inventoryType.value === 'selective' ? filters.value : null,
      settings: settings.value,
      responsible_persons: responsiblePersons.value.filter(p => p.name.trim() !== ''),
      comment: comment.value
    }
    
    const response = await $fetch('/api/v1/distributor/inventory/start', {
      method: 'POST',
      body: payload
    })
    
    const inventoryId = (response as { inventoryId: string }).inventoryId
    
    // Отслеживаем прогресс
    const checkProgress = setInterval(async () => {
      try {
        const status = await $fetch<{
          status: string
          checked: number
          total: number
          completed?: boolean
          discrepancies?: InventoryDiscrepancy[]
          results?: InventoryResults
        }>(`/api/v1/distributor/inventory/status/${inventoryId}`)

        inventoryStatus.value = status.status
        inventoryProgress.value = {
          checked: status.checked,
          total: status.total
        }

        if (status.discrepancies) {
          currentDiscrepancies.value = status.discrepancies
        }

        if (status.completed) {
          inventoryResults.value = status.results || null
          inventoryInProgress.value = false
          clearInterval(checkProgress)
          emit('success')
        }
        
      } catch (err: unknown) {
        logger.error('Error checking inventory status:', err)
        clearInterval(checkProgress)
        inventoryInProgress.value = false
        showToast.error('Ошибка при проведении инвентаризации')
      }
    }, 3000)
    
  } catch (err: unknown) {
    logger.error('Error starting inventory:', err)
    showToast.error('Ошибка при запуске инвентаризации')
    inventoryInProgress.value = false
  }
}

const generateReport = async () => {
  try {
    const response = await $fetch('/api/v1/distributor/inventory/report', {
      method: 'POST',
      body: { results: inventoryResults.value }
    })
    
    const blob = new Blob([response as BlobPart], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `inventory_report_${new Date().toISOString().split('T')[0]}.pdf`
    link.click()
    URL.revokeObjectURL(url)
    
    showToast.success('Отчет сформирован')
  } catch (err: unknown) {
    logger.error('Error generating report:', err)
    showToast.error('Ошибка при формировании отчета')
  }
}

const exportResults = async () => {
  try {
    const response = await $fetch('/api/v1/distributor/inventory/export', {
      method: 'POST',
      body: { results: inventoryResults.value }
    })
    
    const blob = new Blob([response as BlobPart], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `inventory_results_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    URL.revokeObjectURL(url)
    
    showToast.success('Результаты экспортированы')
  } catch (err: unknown) {
    logger.error('Error exporting results:', err)
    showToast.error('Ошибка при экспорте результатов')
  }
}

const resetInventory = () => {
  inventoryResults.value = null
  inventoryProgress.value = { checked: 0, total: 0 }
  inventoryStatus.value = ''
  currentDiscrepancies.value = []
  comment.value = ''
  filters.value = {
    brand: '',
    status: '',
    dateFrom: '',
    dateTo: '',
    onlyDiscrepancies: false
  }
}

// Инициализация
onMounted(() => {
  if (props.isOpen) {
    fetchLastInventory()
    fetchBrands()
  }
})

watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    fetchLastInventory()
    fetchBrands()
  }
})
</script>
