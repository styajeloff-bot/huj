<template>
  <div class="space-y-6">
    <!-- Фильтры -->
    <div class="bg-white p-4 rounded-lg shadow-sm border">
      <div class="flex flex-wrap items-end gap-4">
        <div class="flex-1 min-w-[140px]">
          <label class="block text-sm font-medium text-gray-700 mb-1">Дата от</label>
          <input
            v-model="filters.dateFrom"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <div class="flex-1 min-w-[140px]">
          <label class="block text-sm font-medium text-gray-700 mb-1">Дата до</label>
          <input
            v-model="filters.dateTo"
            type="date"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <div class="flex-1 min-w-[180px]">
          <SearchableDropdown
            v-model="filters.cities"
            :items="meta.cities"
            :multiple="true"
            label="Город"
            item-value="id"
            item-label="name"
            search-placeholder="Поиск города..."
          />
        </div>
        <div class="flex-1 min-w-[180px]">
          <SearchableDropdown
            v-model="filters.dealers"
            :items="meta.dealers"
            :multiple="true"
            label="Дилерский центр"
            item-value="id"
            item-label="name"
            search-placeholder="Поиск дилера..."
          />
        </div>
        <div class="flex-1 min-w-[180px]">
          <SearchableDropdown
            v-model="filters.carBrands"
            :items="meta.carBrands"
            :multiple="true"
            label="Марка автомобиля"
            item-value="id"
            item-label="name"
            search-placeholder="Поиск марки..."
          />
        </div>
        <div>
          <button
            @click="fetchAnalytics"
            class="btn-primary px-4 py-2 rounded-lg"
            :disabled="loading"
          >
            <span v-if="loading" class="inline-block animate-spin h-4 w-4 border-b-2 border-white mr-2"></span>
            Применить
          </button>
        </div>
      </div>
    </div>

    <!-- Загрузка -->
    <div v-if="loading && !data.overview" class="text-center py-12">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-600">Загружаем аналитику...</p>
    </div>

    <template v-else>
      <!-- KPI -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="bg-gradient-to-r from-blue-500 to-blue-600 p-6 rounded-lg text-white">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-blue-100 text-sm">Новые</p>
              <p class="text-2xl font-bold">{{ data.overview.new_count }}</p>
            </div>
            <svg class="w-8 h-8 text-blue-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
        </div>

        <div class="bg-gradient-to-r from-green-500 to-green-600 p-6 rounded-lg text-white">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-green-100 text-sm">Профинансированы</p>
              <p class="text-2xl font-bold">{{ data.overview.financed_count }}</p>
            </div>
            <svg class="w-8 h-8 text-green-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>

        <div class="bg-gradient-to-r from-purple-500 to-purple-600 p-6 rounded-lg text-white">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-purple-100 text-sm">Конверсия общ %</p>
              <p class="text-2xl font-bold">{{ data.overview.conversion_rate }}%</p>
            </div>
            <svg class="w-8 h-8 text-purple-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
        </div>

        <div class="bg-gradient-to-r from-red-500 to-red-600 p-6 rounded-lg text-white">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-red-100 text-sm">Расторгнуто %</p>
              <p class="text-2xl font-bold">{{ data.overview.terminated_rate }}%</p>
              <p class="text-red-100 text-xs">{{ data.overview.terminated_count }} шт</p>
            </div>
            <svg class="w-8 h-8 text-red-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        </div>
      </div>

      <!-- График по статусам + TAT -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Количество заявок по статусам</h3>
          <div class="h-64">
            <canvas ref="statusChart"></canvas>
          </div>
        </div>

        <div class="bg-white p-6 rounded-lg shadow-sm border flex flex-col items-center justify-center">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">ТАТ дней</h3>
          <div class="text-center">
            <p class="text-5xl font-bold text-blue-600">{{ data.tat_days }}</p>
            <p class="text-gray-500 mt-2">среднее количество дней</p>
            <p class="text-xs text-gray-400 mt-1">(created_at → updated_at)</p>
          </div>
        </div>
      </div>

      <!-- Динамика заявок -->
      <div class="bg-white p-6 rounded-lg shadow-sm border">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Динамика по заявкам шт</h3>
        <div class="h-64">
          <canvas ref="dynamicsChart"></canvas>
        </div>
      </div>

      <!-- Таблица по дням -->
      <div class="bg-white p-6 rounded-lg shadow-sm border">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Динамика шт по дням</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Дата</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Всего</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Новые</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Профинансированы</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="row in data.timeline" :key="row.period">
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{{ formatPeriod(row.period) }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-gray-900">{{ row.count }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-blue-600 font-medium">{{ row.new_count }}</td>
                <td class="px-4 py-3 whitespace-nowrap text-sm text-green-600 font-medium">{{ row.financed_count }}</td>
              </tr>
              <tr v-if="data.timeline.length === 0">
                <td colspan="4" class="px-4 py-8 text-center text-gray-500">Нет данных за выбранный период</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Причины отказа -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Сегментация причин отказа</h3>
          <div class="h-64">
            <canvas ref="rejectionChart"></canvas>
          </div>
        </div>

        <div class="bg-white p-6 rounded-lg shadow-sm border">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Топ причин отказа</h3>
          <div class="space-y-3">
            <div v-for="(item, idx) in data.rejection_reasons" :key="idx" class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
              <div class="flex items-center">
                <span class="w-6 h-6 rounded-full bg-gray-200 text-gray-600 text-xs flex items-center justify-center mr-3">{{ idx + 1 }}</span>
                <span class="text-sm text-gray-900">{{ item.reason }}</span>
              </div>
              <span class="text-sm font-medium text-gray-600">{{ item.count }}</span>
            </div>
            <div v-if="data.rejection_reasons.length === 0" class="text-center text-gray-500 py-8">
              Нет данных о причинах отказа
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, onUnmounted } from 'vue'
import { Chart, registerables } from 'chart.js'
import type { ChartConfiguration } from 'chart.js'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useToast } from '@/composables/useToast'
import { useLogger } from '@/composables/useLogger'
import type { DropdownItem } from '@/types'

Chart.register(...registerables)

const { showToast } = useToast()
const logger = useLogger()
const config = useRuntimeConfig()

// Chart instances
let statusChartInstance: Chart | null = null
let dynamicsChartInstance: Chart | null = null
let rejectionChartInstance: Chart | null = null

const createChart = (canvas: HTMLCanvasElement, cfg: ChartConfiguration): Chart => {
  const ctx = canvas.getContext('2d')!
  return new Chart(ctx, cfg)
}

// Filters
const filters = ref({
  dateFrom: '',
  dateTo: '',
  cities: [] as string[],
  dealers: [] as number[],
  carBrands: [] as string[],
})

// Meta for filters
const meta = ref({
  cities: [] as DropdownItem[],
  dealers: [] as DropdownItem[],
  carBrands: [] as DropdownItem[],
})

// Data
const loading = ref(false)
const data = ref({
  overview: {
    new_count: 0,
    financed_count: 0,
    terminated_count: 0,
    conversion_rate: 0,
    terminated_rate: 0,
  },
  status_distribution: [] as { status: string; count: number; percentage: number }[],
  timeline: [] as { period: string; count: number; new_count: number; financed_count: number }[],
  tat_days: 0,
  rejection_reasons: [] as { reason: string; count: number }[],
})

const statusChart = ref<HTMLCanvasElement | null>(null)
const dynamicsChart = ref<HTMLCanvasElement | null>(null)
const rejectionChart = ref<HTMLCanvasElement | null>(null)
const { formatDate: formatSharedDate } = useFormatDate()

const formatPeriod = (period: string | null) => {
  if (!period) return '-'
  const d = new Date(period)
  if (isNaN(d.getTime())) return period
  return formatSharedDate(d)
}

const buildParams = () => {
  const params: Record<string, any> = {}
  if (filters.value.dateFrom) params.date_from = filters.value.dateFrom + 'T00:00:00+00:00'
  if (filters.value.dateTo) params.date_to = filters.value.dateTo + 'T23:59:59+00:00'
  if (filters.value.cities.length) params.city_ids = filters.value.cities
  if (filters.value.dealers.length) params.dealer_ids = filters.value.dealers
  if (filters.value.carBrands.length) params.car_brand_ids = filters.value.carBrands
  return params
}

const fetchAnalytics = async () => {
  try {
    loading.value = true
    const response = await $fetch<any>(
      `${config.public.apiBase}/api/v1/leasing/analytics`,
      {
        params: buildParams(),
        credentials: 'include',
      }
    )
    data.value.overview = response.overview
    data.value.status_distribution = response.status_distribution
    data.value.timeline = response.timeline
    data.value.tat_days = response.tat_days
    data.value.rejection_reasons = response.rejection_reasons

    meta.value.cities = (response.filters_meta?.cities || []).map((c: string) => ({ id: c, name: c }))
    meta.value.dealers = (response.filters_meta?.dealers || []).map((d: any) => ({ id: d.id, name: d.name }))
    meta.value.carBrands = (response.filters_meta?.car_brands || []).map((b: any) => ({ id: b.id, name: b.name }))

    await nextTick()
    createCharts()
  } catch (err) {
    logger.error('Error fetching analytics:', err)
    showToast.error('Ошибка при загрузке аналитики')
  } finally {
    loading.value = false
  }
}

const createCharts = () => {
  if (statusChartInstance) { statusChartInstance.destroy(); statusChartInstance = null }
  if (dynamicsChartInstance) { dynamicsChartInstance.destroy(); dynamicsChartInstance = null }
  if (rejectionChartInstance) { rejectionChartInstance.destroy(); rejectionChartInstance = null }

  // Status bar chart
  if (statusChart.value && data.value.status_distribution.length) {
    statusChartInstance = createChart(statusChart.value, {
      type: 'bar',
      data: {
        labels: data.value.status_distribution.map(i => i.status),
        datasets: [{
          label: 'Заявки',
          data: data.value.status_distribution.map(i => i.count),
          backgroundColor: 'rgba(59, 130, 246, 0.8)',
          borderColor: 'rgb(59, 130, 246)',
          borderWidth: 1,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } }
      }
    })
  }

  // Dynamics line chart
  if (dynamicsChart.value && data.value.timeline.length) {
    dynamicsChartInstance = createChart(dynamicsChart.value, {
      type: 'line',
      data: {
        labels: data.value.timeline.map(i => formatPeriod(i.period)),
        datasets: [
          {
            label: 'Новые',
            data: data.value.timeline.map(i => i.new_count),
            borderColor: 'rgb(59, 130, 246)',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            tension: 0.3,
          },
          {
            label: 'Профинансированы',
            data: data.value.timeline.map(i => i.financed_count),
            borderColor: 'rgb(16, 185, 129)',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            tension: 0.3,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } },
        scales: { y: { beginAtZero: true } }
      }
    })
  }

  // Rejection doughnut chart
  if (rejectionChart.value && data.value.rejection_reasons.length) {
    rejectionChartInstance = createChart(rejectionChart.value, {
      type: 'doughnut',
      data: {
        labels: data.value.rejection_reasons.map(i => i.reason),
        datasets: [{
          data: data.value.rejection_reasons.map(i => i.count),
          backgroundColor: [
            '#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6',
            '#06B6D4', '#EC4899', '#84CC16', '#F97316', '#6366F1'
          ]
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' } }
      }
    })
  }
}

onMounted(() => {
  fetchAnalytics()
})

onUnmounted(() => {
  if (statusChartInstance) statusChartInstance.destroy()
  if (dynamicsChartInstance) dynamicsChartInstance.destroy()
  if (rejectionChartInstance) rejectionChartInstance.destroy()
})
</script>
