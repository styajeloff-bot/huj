<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Отчеты и аналитика
      </h2>
      <div class="flex space-x-3">
        <button @click="exportReport" class="btn-secondary">
          Экспорт в Excel
        </button>
        <button @click="generateReport" class="btn-primary">
          Создать отчет
        </button>
      </div>
    </div>

    <!-- Фильтры периода -->
    <div class="bg-white p-4 rounded-lg border border-gray-200 mb-6">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Период</label>
          <select v-model="filters.period" class="select-field" @change="fetchReports">
            <option value="week">Последняя неделя</option>
            <option value="month">Последний месяц</option>
            <option value="quarter">Последний квартал</option>
            <option value="year">Последний год</option>
            <option value="custom">Произвольный период</option>
          </select>
        </div>
        <div v-if="filters.period === 'custom'">
          <label class="block text-sm font-medium text-gray-700 mb-1">Дата от</label>
          <input
            v-model="filters.dateFrom"
            type="date"
            class="input-field"
            @change="fetchReports"
          >
        </div>
        <div v-if="filters.period === 'custom'">
          <label class="block text-sm font-medium text-gray-700 mb-1">Дата до</label>
          <input
            v-model="filters.dateTo"
            type="date"
            class="input-field"
            @change="fetchReports"
          >
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Тип отчета</label>
          <select v-model="activeReport" class="select-field">
            <option value="overview">Общий обзор</option>
            <option value="sales">Продажи</option>
            <option value="applications">Заявки</option>
            <option value="clients">Клиенты</option>
            <option value="inventory">Склад</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Общая статистика -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
      <div class="bg-white p-6 rounded-lg border border-gray-200">
        <div class="flex items-center">
          <div class="flex-shrink-0">
            <div class="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
              <svg class="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z">
                </path>
              </svg>
            </div>
          </div>
          <div class="ml-4">
            <p class="text-sm font-medium text-gray-500">Выручка</p>
            <p class="text-2xl font-semibold text-gray-900">{{ formatMoney(reports.revenue) }}</p>
            <p class="text-sm" :class="(reports.revenue_change ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ (reports.revenue_change ?? 0) >= 0 ? '+' : '' }}{{ reports.revenue_change }}%
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white p-6 rounded-lg border border-gray-200">
        <div class="flex items-center">
          <div class="flex-shrink-0">
            <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
              <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
                </path>
              </svg>
            </div>
          </div>
          <div class="ml-4">
            <p class="text-sm font-medium text-gray-500">Заявки</p>
            <p class="text-2xl font-semibold text-gray-900">{{ reports.applications_count }}</p>
            <p class="text-sm" :class="(reports.applications_change ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ (reports.applications_change ?? 0) >= 0 ? '+' : '' }}{{ reports.applications_change }}%
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white p-6 rounded-lg border border-gray-200">
        <div class="flex items-center">
          <div class="flex-shrink-0">
            <div class="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center">
              <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z">
                </path>
              </svg>
            </div>
          </div>
          <div class="ml-4">
            <p class="text-sm font-medium text-gray-500">Новые клиенты</p>
            <p class="text-2xl font-semibold text-gray-900">{{ reports.new_clients }}</p>
            <p class="text-sm" :class="(reports.clients_change ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ (reports.clients_change ?? 0) >= 0 ? '+' : '' }}{{ reports.clients_change }}%
            </p>
          </div>
        </div>
      </div>

      <div class="bg-white p-6 rounded-lg border border-gray-200">
        <div class="flex items-center">
          <div class="flex-shrink-0">
            <div class="w-8 h-8 bg-yellow-100 rounded-full flex items-center justify-center">
              <svg class="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6">
                </path>
              </svg>
            </div>
          </div>
          <div class="ml-4">
            <p class="text-sm font-medium text-gray-500">Конверсия</p>
            <p class="text-2xl font-semibold text-gray-900">{{ reports.conversion_rate }}%</p>
            <p class="text-sm" :class="(reports.conversion_change ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'">
              {{ (reports.conversion_change ?? 0) >= 0 ? '+' : '' }}{{ reports.conversion_change }}%
            </p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-600">Загружаем отчеты...</p>
    </div>

    <div v-else-if="error" class="text-center py-8">
      <p class="text-red-600 mb-4">{{ error }}</p>
      <button @click="fetchReports" class="btn-primary">
        Попробовать снова
      </button>
    </div>

    <div v-else class="space-y-6">
      <!-- Общий обзор -->
      <div v-if="activeReport === 'overview'" class="space-y-6">
        <!-- График продаж -->
        <div class="bg-white p-6 rounded-lg border border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">График продаж</h3>
          <div class="h-64 flex items-center justify-center bg-gray-50 rounded-lg">
            <div class="text-center">
              <svg class="mx-auto h-12 w-12 text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z">
                </path>
              </svg>
              <p class="text-gray-500">График продаж будет здесь</p>
            </div>
          </div>
        </div>

        <!-- Топ моделей -->
        <div class="bg-white p-6 rounded-lg border border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Топ моделей</h3>
          <div class="space-y-3">
            <div v-for="model in reports.top_models" :key="model.id" class="flex items-center justify-between">
              <div class="flex items-center">
                <div class="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center mr-3">
                  <span class="text-sm font-medium text-blue-600">{{ model.rank }}</span>
                </div>
                <div>
                  <div class="text-sm font-medium text-gray-900">{{ model.brand }} {{ model.model }}</div>
                  <div class="text-sm text-gray-500">{{ model.sales_count }} продаж</div>
                </div>
              </div>
              <div class="text-right">
                <div class="text-sm font-medium text-gray-900">{{ formatMoney(model.revenue) }}</div>
                <div class="text-sm text-gray-500">{{ model.percentage }}%</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Отчет по продажам -->
      <div v-if="activeReport === 'sales'" class="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <h3 class="text-lg font-medium text-gray-900">Отчет по продажам</h3>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Автомобиль
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Клиент
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Сумма
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Дата продажи
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Статус
                </th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="sale in reports.sales" :key="sale.id" class="hover:bg-gray-50">
                <td class="px-6 py-4 whitespace-nowrap">
                  <div class="text-sm font-medium text-gray-900">
                    {{ sale.brand }} {{ sale.model }}
                  </div>
                  <div class="text-sm text-gray-500">{{ sale.year }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <div class="text-sm text-gray-900">{{ sale.client_name }}</div>
                  <div class="text-sm text-gray-500">{{ sale.client_email }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {{ formatMoney(sale.amount) }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {{ formatDate(sale.sale_date) }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800">
                    Завершена
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Отчет по заявкам -->
      <div v-if="activeReport === 'applications'" class="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <h3 class="text-lg font-medium text-gray-900">Отчет по заявкам</h3>
        </div>
        
        <!-- Статистика по статусам заявок -->
        <div class="p-6 border-b border-gray-200">
          <h4 class="text-sm font-medium text-gray-700 mb-3">Статусы заявок</h4>
          <div class="grid grid-cols-3 gap-4">
            <div class="text-center">
              <div class="text-2xl font-semibold text-blue-600">{{ reports.applications_stats?.active || 0 }}</div>
              <div class="text-sm text-gray-500">Активные</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-semibold text-red-600">{{ reports.applications_stats?.rejected || 0 }}</div>
              <div class="text-sm text-gray-500">Отклонены</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-semibold text-green-600">{{ reports.applications_stats?.issued || 0 }}</div>
              <div class="text-sm text-gray-500">Выданы</div>
            </div>
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Заявка
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Клиент
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Сумма
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Дата подачи
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Статус
                </th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="application in reports.applications" :key="application.id" class="hover:bg-gray-50">
                <td class="px-6 py-4 whitespace-nowrap">
                  <div class="text-sm font-medium text-gray-900">
                    Заявка {{ formatApplicationNumber(application as any) }}
                  </div>
                  <div class="text-sm text-gray-500">{{ application.vehicles_count }} автомобилей</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <div class="text-sm text-gray-900">{{ application.client_name }}</div>
                  <div class="text-sm text-gray-500">{{ application.client_email }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                  {{ formatMoney(application.total_amount) }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {{ formatDate(application.created_at) }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                  <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                        :class="getApplicationStatusColor(application.status)">
                    {{ getApplicationStatusLabel(application.status) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Отчет по клиентам -->
      <div v-if="activeReport === 'clients'" class="space-y-6">
        <div class="bg-white p-6 rounded-lg border border-gray-200">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Топ клиенты</h3>
          <div class="space-y-3">
            <div v-for="client in reports.top_clients" :key="client.id" class="flex items-center justify-between">
              <div class="flex items-center">
                <div class="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center mr-3">
                  <span class="text-sm font-medium text-blue-600">
                    {{ getInitials(client.name) }}
                  </span>
                </div>
                <div>
                  <div class="text-sm font-medium text-gray-900">{{ client.name }}</div>
                  <div class="text-sm text-gray-500">{{ client.applications_count }} заявок</div>
                </div>
              </div>
              <div class="text-right">
                <div class="text-sm font-medium text-gray-900">{{ formatMoney(client.total_amount) }}</div>
                <div class="text-sm text-gray-500">Средний чек: {{ formatMoney(client.average_deal) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Отчет по складу -->
      <div v-if="activeReport === 'inventory'" class="space-y-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="bg-white p-6 rounded-lg border border-gray-200">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Статистика склада</h3>
            <div class="space-y-3">
              <div class="flex justify-between">
                <span class="text-gray-600">Всего автомобилей:</span>
                <span class="font-medium">{{ reports.inventory_stats?.total || 0 }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">В наличии:</span>
                <span class="font-medium text-green-600">{{ reports.inventory_stats?.available || 0 }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Зарезервировано:</span>
                <span class="font-medium text-yellow-600">{{ reports.inventory_stats?.reserved || 0 }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Продано:</span>
                <span class="font-medium text-gray-600">{{ reports.inventory_stats?.sold || 0 }}</span>
              </div>
            </div>
          </div>

          <div class="bg-white p-6 rounded-lg border border-gray-200">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Оборачиваемость</h3>
            <div class="space-y-3">
              <div class="flex justify-between">
                <span class="text-gray-600">Средний срок продажи:</span>
                <span class="font-medium">{{ reports.inventory_stats?.avg_sale_days || 0 }} дней</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Самый быстрый:</span>
                <span class="font-medium text-green-600">{{ reports.inventory_stats?.fastest_sale || 0 }} дней</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Самый медленный:</span>
                <span class="font-medium text-red-600">{{ reports.inventory_stats?.slowest_sale || 0 }} дней</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DealerReportsData, DealerApplicationStatus } from '~/types/features'
import { formatApplicationNumber } from '~/utils'

const config = useRuntimeConfig()
const { showToast } = useToast()
const logger = useLogger()

const reports = ref<Partial<DealerReportsData>>({})
const loading = ref(true)
const error = ref('')
const activeReport = ref('overview')

const filters = ref({
  period: 'month',
  dateFrom: '',
  dateTo: ''
})

const fetchReports = async () => {
  loading.value = true
  error.value = ''

  try {
    const params = new URLSearchParams({
      period: filters.value.period,
      report_type: activeReport.value
    })

    if (filters.value.period === 'custom') {
      if (filters.value.dateFrom) params.append('date_from', filters.value.dateFrom)
      if (filters.value.dateTo) params.append('date_to', filters.value.dateTo)
    }

    const response = await $fetch<{ reports: DealerReportsData }>(`/api/v1/dealer/reports?${params.toString()}`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    reports.value = response.reports
  } catch (err: unknown) {
    logger.error('Error fetching dealer reports', err)
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке отчетов'
  } finally {
    loading.value = false
  }
}

const generateReport = async () => {
  try {
    showToast.info('Генерируем отчет...')
    await fetchReports()
    showToast.success('Отчет обновлен')
  } catch (err) {
    logger.error('Error generating report', err)
    showToast.error('Ошибка при генерации отчета')
  }
}

const exportReport = async () => {
  try {
    showToast.info('Экспортируем отчет...')

    const params = new URLSearchParams({
      period: filters.value.period,
      report_type: activeReport.value,
      format: 'xlsx',
    })

    if (filters.value.period === 'custom') {
      if (filters.value.dateFrom) params.append('dateFrom', filters.value.dateFrom)
      if (filters.value.dateTo) params.append('dateTo', filters.value.dateTo)
    }

    const response = await $fetch<Blob>(
      `/api/v1/dealer/reports?${params.toString()}`,
      {
        baseURL: config.public.apiBase,
        credentials: 'include',
        responseType: 'blob',
      },
    )

    const blob =
      response instanceof Blob
        ? response
        : new Blob([response as BlobPart], {
            type:
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `dealer_report_${new Date().toISOString().split('T')[0]}.xlsx`
    link.click()
    URL.revokeObjectURL(url)

    showToast.success('Отчет экспортирован')
  } catch (err) {
    logger.error('Error exporting report', err)
    showToast.error('Ошибка при экспорте отчета')
  }
}

const applicationStatusLabels: Record<DealerApplicationStatus, string> = {
  active: 'Активная',
  rejected: 'Отклонена',
  issued: 'Выдана'
}

const getApplicationStatusLabel = (status: DealerApplicationStatus): string => {
  return applicationStatusLabels[status] || status
}

const applicationStatusColors: Record<DealerApplicationStatus, string> = {
  active: 'bg-blue-100 text-blue-800',
  rejected: 'bg-red-100 text-red-800',
  issued: 'bg-green-100 text-green-800'
}

const getApplicationStatusColor = (status: DealerApplicationStatus): string => {
  return applicationStatusColors[status] || 'bg-gray-100 text-gray-800'
}

const getInitials = (name: string): string => {
  return name
    .split(' ')
    .map((part: string) => part.charAt(0))
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

const formatDate = (dateString: string | undefined | null): string => {
  if (!dateString) return '-'
  return formatSharedDate(dateString)
}

const formatMoney = (amount: number | undefined | null): string => {
  if (!amount) return '0 ₽'
  return formatSharedPrice(amount)
}

// Следим за изменением типа отчета
watch(activeReport, () => {
  fetchReports()
})

onMounted(() => {
  fetchReports()
})
</script>
