<template>
  <Modal :isOpen="isOpen" @close="$emit('close')" size="lg">
    <template #header>
      <h3 class="text-lg font-semibold text-gray-900">
        Создать отчет
      </h3>
      <p class="text-sm text-gray-600 mt-1">
        Настройте параметры отчета
      </p>
    </template>

    <template #body>
      <div class="space-y-6">
        <!-- Тип отчета -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-3">
            Тип отчета
          </label>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <button
              v-for="type in reportTypes"
              :key="type.value"
              @click="reportData.type = type.value"
              :class="{
                'bg-blue-600 text-white border-blue-600': reportData.type === type.value,
                'bg-white text-gray-700 border-gray-300 hover:bg-gray-50': reportData.type !== type.value
              }"
              class="p-4 border-2 rounded-lg text-left transition-colors"
            >
              <div class="flex items-center">
                <component :is="type.icon" class="w-6 h-6 mr-3" />
                <div>
                  <div class="font-medium">{{ type.name }}</div>
                  <div class="text-sm opacity-75">{{ type.description }}</div>
                </div>
              </div>
            </button>
          </div>
        </div>

        <!-- Название отчета -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            Название отчета
          </label>
          <input
            v-model="reportData.name"
            type="text"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Введите название отчета"
          >
        </div>

        <!-- Период отчета -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Период
            </label>
            <select
              v-model="reportData.period"
              @change="handlePeriodChange"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="today">Сегодня</option>
              <option value="yesterday">Вчера</option>
              <option value="week">Эта неделя</option>
              <option value="month">Этот месяц</option>
              <option value="quarter">Этот квартал</option>
              <option value="year">Этот год</option>
              <option value="custom">Произвольный период</option>
            </select>
          </div>

          <div v-if="reportData.period === 'custom'">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Дата от
            </label>
            <input
              v-model="reportData.date_from"
              type="date"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>
        </div>

        <div v-if="reportData.period === 'custom'" class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Дата до
            </label>
            <input
              v-model="reportData.date_to"
              type="date"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Формат файла
            </label>
            <select
              v-model="reportData.format"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="pdf">PDF</option>
              <option value="excel">Excel</option>
              <option value="csv">CSV</option>
            </select>
          </div>
        </div>

        <!-- Фильтры отчета -->
        <div v-if="reportData.type">
          <label class="block text-sm font-medium text-gray-700 mb-3">
            Дополнительные фильтры
          </label>
          
          <!-- Фильтры для складского отчета -->
          <div v-if="reportData.type === 'inventory'" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm text-gray-600 mb-1">Марка</label>
                <select
                  v-model="reportData.filters.brand"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="">Все марки</option>
                  <option value="Toyota">Toyota</option>
                  <option value="BMW">BMW</option>
                  <option value="Mercedes">Mercedes</option>
                </select>
              </div>
              
              <div>
                <label class="block text-sm text-gray-600 mb-1">Статус</label>
                <select
                  v-model="reportData.filters.status"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="">Все статусы</option>
                  <option value="available">В наличии</option>
                  <option value="reserved">Зарезервировано</option>
                  <option value="sold">Продано</option>
                </select>
              </div>
            </div>
            
            <div class="flex items-center">
              <input
                v-model="reportData.filters.include_photos"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Включить фотографии автомобилей</span>
            </div>
          </div>

          <!-- Фильтры для отчета по продажам -->
          <div v-if="reportData.type === 'sales'" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm text-gray-600 mb-1">Дилер</label>
                <select
                  v-model="reportData.filters.dealer"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="">Все дилеры</option>
                  <option value="1">ООО Автосалон Север</option>
                  <option value="2">ИП Иванов И.И.</option>
                </select>
              </div>
              
              <div>
                <label class="block text-sm text-gray-600 mb-1">Группировка</label>
                <select
                  v-model="reportData.filters.group_by"
                  class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="day">По дням</option>
                  <option value="week">По неделям</option>
                  <option value="month">По месяцам</option>
                  <option value="dealer">По дилерам</option>
                  <option value="brand">По маркам</option>
                </select>
              </div>
            </div>
          </div>

          <!-- Фильтры для финансового отчета -->
          <div v-if="reportData.type === 'financial'" class="space-y-4">
            <div class="flex items-center">
              <input
                v-model="reportData.filters.include_forecasts"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Включить прогнозы</span>
            </div>
            
            <div class="flex items-center">
              <input
                v-model="reportData.filters.detailed_breakdown"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Детальная разбивка по статьям</span>
            </div>
          </div>
        </div>

        <!-- Настройки отправки -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-3">
            Настройки отправки
          </label>
          
          <div class="space-y-3">
            <div class="flex items-center">
              <input
                v-model="reportData.send_email"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Отправить на email после генерации</span>
            </div>
            
            <div v-if="reportData.send_email">
              <input
                v-model="reportData.email"
                type="email"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Email для отправки отчета"
              >
            </div>
            
            <div class="flex items-center">
              <input
                v-model="reportData.schedule_recurring"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              >
              <span class="ml-2 text-sm text-gray-700">Создавать автоматически</span>
            </div>
            
            <div v-if="reportData.schedule_recurring" class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <select
                v-model="reportData.recurring_frequency"
                class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="daily">Ежедневно</option>
                <option value="weekly">Еженедельно</option>
                <option value="monthly">Ежемесячно</option>
                <option value="quarterly">Ежеквартально</option>
              </select>
              
              <input
                v-model="reportData.recurring_time"
                type="time"
                class="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
            </div>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-between">
        <div class="text-sm text-gray-600">
          Отчет будет сгенерирован в фоновом режиме
        </div>
        <div class="flex space-x-3">
          <button
            @click="$emit('close')"
            class="px-4 py-2 text-gray-700 bg-gray-200 hover:bg-gray-300 rounded-lg transition-colors"
          >
            Отменить
          </button>
          <button
            @click="createReport"
            :disabled="!canCreate || creating"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span v-if="creating" class="inline-flex items-center">
              <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Создание...
            </span>
            <span v-else>Создать отчет</span>
          </button>
        </div>
      </div>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
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

// Типы отчетов
const reportTypes = [
  {
    value: 'inventory',
    name: 'Складской отчет',
    description: 'Остатки и движение товаров',
    icon: 'svg'
  },
  {
    value: 'sales',
    name: 'Отчет по продажам',
    description: 'Статистика продаж и доходов',
    icon: 'svg'
  },
  {
    value: 'financial',
    name: 'Финансовый отчет',
    description: 'Прибыль, убытки и прогнозы',
    icon: 'svg'
  },
  {
    value: 'analytics',
    name: 'Аналитический отчет',
    description: 'Детальная аналитика и KPI',
    icon: 'svg'
  }
]

// Данные отчета
const reportData = ref({
  type: '',
  name: '',
  period: 'month',
  date_from: '',
  date_to: '',
  format: 'pdf',
  filters: {
    brand: '',
    status: '',
    dealer: '',
    group_by: 'day',
    include_photos: false,
    include_forecasts: false,
    detailed_breakdown: false
  },
  send_email: false,
  email: '',
  schedule_recurring: false,
  recurring_frequency: 'monthly',
  recurring_time: '09:00'
})

const creating = ref(false)

// Вычисляемые свойства
const canCreate = computed(() => {
  return reportData.value.type && 
         reportData.value.name.trim() !== '' &&
         (reportData.value.period !== 'custom' || 
          (reportData.value.date_from && reportData.value.date_to))
})

// Методы
const handlePeriodChange = () => {
  if (reportData.value.period !== 'custom') {
    reportData.value.date_from = ''
    reportData.value.date_to = ''
  }
  
  // Генерируем название по умолчанию
  if (!reportData.value.name || reportData.value.name === getDefaultName(reportData.value.type)) {
    reportData.value.name = getDefaultName(reportData.value.type)
  }
}

const getDefaultName = (type: string) => {
  const typeNames: Record<string, string> = {
    inventory: 'Складской отчет',
    sales: 'Отчет по продажам',
    financial: 'Финансовый отчет',
    analytics: 'Аналитический отчет'
  }

  const periodNames: Record<string, string> = {
    today: 'за сегодня',
    yesterday: 'за вчера',
    week: 'за неделю',
    month: 'за месяц',
    quarter: 'за квартал',
    year: 'за год',
    custom: 'за период'
  }

  return `${typeNames[type] || 'Отчет'} ${periodNames[reportData.value.period] || ''} - ${new Date().toLocaleDateString('ru-RU')}`
}

const createReport = async () => {
  try {
    creating.value = true
    
    await $fetch('/api/v1/distributor/reports', {
      method: 'POST',
      body: reportData.value
    })
    
    showToast.success('Отчет поставлен в очередь на генерацию')
    emit('success')

  } catch (err) {
    logger.error('Error creating report:', err)
    showToast.error('Ошибка при создании отчета')
  } finally {
    creating.value = false
  }
}

// Наблюдатели
watch(() => reportData.value.type, (newType) => {
  if (newType && !reportData.value.name) {
    reportData.value.name = getDefaultName(newType)
  }
})

watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    // Сброс формы при открытии
    reportData.value = {
      type: '',
      name: '',
      period: 'month',
      date_from: '',
      date_to: '',
      format: 'pdf',
      filters: {
        brand: '',
        status: '',
        dealer: '',
        group_by: 'day',
        include_photos: false,
        include_forecasts: false,
        detailed_breakdown: false
      },
      send_email: false,
      email: '',
      schedule_recurring: false,
      recurring_frequency: 'monthly',
      recurring_time: '09:00'
    }
  }
})
</script>
