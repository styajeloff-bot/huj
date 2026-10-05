<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Всего запросов" :value="kpi('W-EXC-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Активных" :value="kpi('W-EXC-02')?.value" color="#4DA2F1" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Всего ставок" :value="kpi('W-EXC-03')?.value" color="#2E7D32" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Принято" :value="kpi('W-EXC-04')?.value" color="#F5A623" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Ср. цена" :value="kpi('W-EXC-05')?.value" color="#00ACC1" prefix="₽" />
    </WidgetCard>

    <WidgetCard title="Динамика биржи" class="chart-wide">
      <LineChart :series="lineSeries('W-EXC-07')" />
    </WidgetCard>

    <WidgetCard title="Запросы на бирже" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">ID</th>
              <th class="text-left py-2 px-3">Статус</th>
              <th class="text-right py-2 px-3">Кол-во</th>
              <th class="text-left py-2 px-3">Тип выгоды</th>
              <th class="text-right py-2 px-3">Выгода</th>
              <th class="text-right py-2 px-3">Ставок</th>
              <th class="text-right py-2 px-3">Принято</th>
              <th class="text-right py-2 px-3">Ср. цена</th>
              <th class="text-left py-2 px-3">Дата</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in tableItems" :key="item.request_id" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.request_id }}</td>
              <td class="py-2 px-3"><span :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span></td>
              <td class="py-2 px-3 text-right">{{ item.quantity }}</td>
              <td class="py-2 px-3">{{ item.discount_type || '—' }}</td>
              <td class="py-2 px-3 text-right">{{ item.discount_percent }}%</td>
              <td class="py-2 px-3 text-right">{{ item.bids_count }}</td>
              <td class="py-2 px-3 text-right">{{ item.accepted_bids }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.average_price) }}</td>
              <td class="py-2 px-3">{{ formatDate(item.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="pagination"
        :total="pagination.total"
        :limit="pagination.limit"
        :offset="pagination.offset"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LkDashboardResponse } from '../api/analytics'
import { getWidgetKpi, getWidgetLineSeries } from '../api/analytics'
import KpiCard from '~/components/ui/analytics/KpiCard.vue'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import LineChart from '~/components/ui/analytics/LineChart.vue'
import SimplePagination from '~/components/ui/analytics/SimplePagination.vue'

const props = defineProps<{
  data: LkDashboardResponse | null
  loading: boolean
}>()

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const kpi = (key: string) => getWidgetKpi(props.data?.widgets || {}, key)
const lineSeries = (key: string) => getWidgetLineSeries(props.data?.widgets || {}, key)

const tableItems = computed(() => {
  const w = props.data?.widgets?.['W-EXC-08']
  if (w && typeof w === 'object' && 'items' in w) return (w as any).items
  return []
})

const pagination = computed(() => {
  const w = props.data?.widgets?.['W-EXC-08']
  if (w && typeof w === 'object' && 'pagination' in w) return (w as any).pagination
  return null
})

function formatPrice(v: number) {
  if (!v) return '—'
  return formatSharedPrice(v)
}

function formatDate(d: string) {
  if (!d || d === 'null') return '—'
  return formatSharedDate(d)
}

function statusLabel(s: string) {
  const map: Record<string, string> = {
    active: 'Активен',
    closed: 'Закрыт',
    cancelled: 'Отменён',
  }
  return map[s] || s
}

function statusClass(s: string) {
  const map: Record<string, string> = {
    active: 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800',
    closed: 'px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-800',
    cancelled: 'px-2 py-0.5 rounded text-xs bg-red-100 text-red-800',
  }
  return map[s] || 'px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-800'
}
</script>

<style scoped>
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 16px;
  align-items: start;
}

.kpi-span-2 {
  grid-column: span 2;
  padding: 16px;
}

.kpi-span-3 {
  grid-column: span 3;
  padding: 16px;
}

.chart-wide {
  grid-column: span 12;
}

@media (max-width: 1024px) {
  .kpi-span-2 {
    grid-column: span 3;
  }
  .kpi-span-3 {
    grid-column: span 4;
  }
}

</style>
