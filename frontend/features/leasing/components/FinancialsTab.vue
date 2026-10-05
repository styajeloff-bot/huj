<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-2">
      <KpiCard title="В работе" :value="kpi('W-FIN-01')?.value" color="#1E69A9" prefix="₽" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Одобрено" :value="kpi('W-FIN-02')?.value" color="#2E7D32" prefix="₽" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Выдано" :value="kpi('W-FIN-03')?.value" color="#4DA2F1" prefix="₽" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Ср. ставка" :value="kpi('W-FIN-04')?.value" color="#F5A623" suffix="%" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Ср. срок" :value="kpi('W-FIN-05')?.value" color="#7B3FA0" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Ср. аванс %" :value="kpi('W-FIN-06')?.value" color="#00ACC1" suffix="%" />
    </WidgetCard>

    <WidgetCard title="Динамика объёмов" class="chart-wide">
      <LineChart :series="lineSeries('W-FIN-08')" />
    </WidgetCard>

    <WidgetCard title="Финансовые показатели" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">№</th>
              <th class="text-left py-2 px-3">Статус</th>
              <th class="text-right py-2 px-3">Сумма</th>
              <th class="text-right py-2 px-3">ПВ</th>
              <th class="text-right py-2 px-3">ПВ %</th>
              <th class="text-right py-2 px-3">Срок</th>
              <th class="text-right py-2 px-3">Платёж</th>
              <th class="text-right py-2 px-3">Ставка</th>
              <th class="text-right py-2 px-3">Маржа</th>
              <th class="text-right py-2 px-3">Итого</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in tableItems" :key="item.display_number" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.display_number }}</td>
              <td class="py-2 px-3"><span :class="statusClass(item.status)">{{ formatStatus(item.status) }}</span></td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.total_amount) }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.down_payment) }}</td>
              <td class="py-2 px-3 text-right">{{ item.down_payment_percent }}%</td>
              <td class="py-2 px-3 text-right">{{ item.lease_term_months }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.monthly_payment) }}</td>
              <td class="py-2 px-3 text-right">{{ item.rate }}%</td>
              <td class="py-2 px-3 text-right">{{ item.markup }}%</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.total_cost) }}</td>
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

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const kpi = (key: string) => getWidgetKpi(props.data?.widgets || {}, key)
const lineSeries = (key: string) => getWidgetLineSeries(props.data?.widgets || {}, key)

const tableItems = computed(() => {
  const w = props.data?.widgets?.['W-FIN-09']
  if (w && typeof w === 'object' && 'items' in w) return (w as any).items
  return []
})

const pagination = computed(() => {
  const w = props.data?.widgets?.['W-FIN-09']
  if (w && typeof w === 'object' && 'pagination' in w) return (w as any).pagination
  return null
})

function formatPrice(v: number) {
  if (!v) return '—'
  return formatSharedPrice(v)
}

function formatStatus(s: string) {
  const map: Record<string, string> = {
    under_review: 'На рассмотрении',
    approved: 'Одобрено',
    rejected: 'Отказано',
    issued: 'Выдано',
  }
  return map[s] || s
}

function statusClass(s: string) {
  const map: Record<string, string> = {
    under_review: 'px-2 py-0.5 rounded text-xs bg-yellow-100 text-yellow-800',
    approved: 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800',
    rejected: 'px-2 py-0.5 rounded text-xs bg-red-100 text-red-800',
    issued: 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800',
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
