<template>
  <div class="dash-grid">
    <!-- Combo Chart: Applications -->
    <WidgetCard title="Заявки (текущий vs предыдущий период)" class="chart-wide">
      <ComboChart v-if="comboData('W-APP-06')" :data="comboData('W-APP-06')!" />
    </WidgetCard>

    <!-- Combo Chart: Deals -->
    <WidgetCard title="Сделки (текущий vs предыдущий период)" class="chart-wide">
      <ComboChart v-if="comboData('W-APP-07')" :data="comboData('W-APP-07')!" />
    </WidgetCard>

    <!-- Detailed per-status statistics -->
    <WidgetCard title="Статистика по статусам" class="chart-wide">
      <div v-if="statusStats.length" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">Статус</th>
              <th class="text-right py-2 px-3">Кол-во</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in statusStats" :key="row.status" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ row.status_label }}</td>
              <td class="py-2 px-3 text-right">{{ row.count.toLocaleString('ru-RU') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="text-sm text-gray-400 py-4 text-center">Нет данных</p>
    </WidgetCard>

    <!-- Table -->
    <WidgetCard title="Заявки" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">№ заявки</th>
              <th class="text-left py-2 px-3">Дата</th>
              <th class="text-left py-2 px-3">Лизинговая</th>
              <th class="text-left py-2 px-3">Дилер</th>
              <th class="text-left py-2 px-3">Марка</th>
              <th class="text-left py-2 px-3">Модель</th>
              <th class="text-right py-2 px-3">Сумма</th>
              <th class="text-right py-2 px-3">Срок сделки</th>
              <th class="text-left py-2 px-3">Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in tableItems" :key="item.display_number" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.display_number }}</td>
              <td class="py-2 px-3">{{ formatDate(item.created_at) }}</td>
              <td class="py-2 px-3">{{ item.leasing_company || '—' }}</td>
              <td class="py-2 px-3">{{ item.dealer_name }}</td>
              <td class="py-2 px-3">{{ item.mark }}</td>
              <td class="py-2 px-3">{{ item.model }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.total_amount) }}</td>
              <td class="py-2 px-3 text-right">{{ formatDuration(item.deal_duration_days) }}</td>
              <td class="py-2 px-3">
                <span :class="statusClass(item.status_bucket)">{{ item.status_label }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="pagination"
        :total="pagination.total"
        :limit="pagination.limit"
        :offset="(pagination.page - 1) * pagination.limit"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ApplicationsTabResponse, ApplicationsStatusStatRow, ApplicationsTableRow, ComboChartData, StatusBucket } from '../../api/analytics'
import { getWidgetTable, getWidgetPagination } from '../../api/analytics'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import ComboChart from '~/features/distributor/components/ComboChart.vue'
import SimplePagination from '~/components/ui/analytics/SimplePagination.vue'

const props = defineProps<{
  data: ApplicationsTabResponse | null
  loading: boolean
}>()

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

function comboData(key: string): ComboChartData | undefined {
  const widgets = props.data?.widgets as Record<string, any> | undefined
  const w = widgets?.[key]
  if (w && typeof w === 'object' && 'labels' in w && 'barDatasets' in w) {
    return w as ComboChartData
  }
  return undefined
}

const tableItems = computed(() =>
  getWidgetTable<ApplicationsTableRow>(props.data?.widgets || {}, 'W-APP-08'),
)

const pagination = computed(() => getWidgetPagination(props.data?.widgets || {}, 'W-APP-08'))

const statusStats = computed(() => {
  const w = props.data?.widgets?.['W-APP-10']
  return Array.isArray(w) ? (w as ApplicationsStatusStatRow[]) : []
})

function formatPrice(v: number) {
  if (!v) return '—'
  return formatSharedPrice(v)
}

function formatDate(d: string) {
  if (!d || d === 'null') return '—'
  return formatSharedDate(d)
}

function formatDuration(days: number | null | undefined) {
  if (days === null || days === undefined) return '—'
  return `${days} дн.`
}

function statusClass(bucket: StatusBucket | string) {
  const map: Record<string, string> = {
    active: 'px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-800',
    rejected: 'px-2 py-0.5 rounded text-xs bg-red-100 text-red-800',
    issued: 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800',
  }
  return map[bucket] || 'px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-800'
}
</script>

<style scoped>
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 16px;
  align-items: start;
}

.chart-wide {
  grid-column: span 12;
}

</style>
