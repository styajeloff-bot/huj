<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Всего" :value="kpi('W-PRP-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Принято" :value="kpi('W-PRP-02')?.value" color="#2E7D32" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Отклонено" :value="kpi('W-PRP-03')?.value" color="#FF3D64" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="В ожидании" :value="kpi('W-PRP-04')?.value" color="#F5A623" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Ср. ставка" :value="kpi('W-PRP-05')?.value" color="#7B3FA0" suffix="%" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Ср. срок" :value="kpi('W-PRP-06')?.value" color="#00ACC1" />
    </WidgetCard>

    <WidgetCard title="Динамика предложений" class="chart-wide">
      <LineChart :series="lineSeries('W-PRP-08')" />
    </WidgetCard>

    <WidgetCard title="Список предложений" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">ID</th>
              <th class="text-left py-2 px-3">Тип</th>
              <th class="text-right py-2 px-3">Сумма</th>
              <th class="text-right py-2 px-3">Ставка</th>
              <th class="text-right py-2 px-3">Срок</th>
              <th class="text-right py-2 px-3">Платёж</th>
              <th class="text-left py-2 px-3">Решение</th>
              <th class="text-left py-2 px-3">Дата</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in tableItems" :key="item.proposal_id" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.proposal_id }}</td>
              <td class="py-2 px-3">{{ item.kind === 'preliminary' ? 'Предв.' : 'Оконч.' }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.total_amount) }}</td>
              <td class="py-2 px-3 text-right">{{ item.rate }}%</td>
              <td class="py-2 px-3 text-right">{{ item.lease_term_months }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.monthly_payment) }}</td>
              <td class="py-2 px-3">
                <span :class="decisionClass(item.client_decision_action)">{{ decisionLabel(item.client_decision_action) }}</span>
              </td>
              <td class="py-2 px-3">{{ formatDate(item.proposal_created_at) }}</td>
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
  const w = props.data?.widgets?.['W-PRP-09']
  if (w && typeof w === 'object' && 'items' in w) return (w as any).items
  return []
})

const pagination = computed(() => {
  const w = props.data?.widgets?.['W-PRP-09']
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

function decisionLabel(d: string | null) {
  const map: Record<string, string> = { accepted: 'Принято', rejected: 'Отклонено' }
  return d ? map[d] || d : 'В ожидании'
}

function decisionClass(d: string | null) {
  if (d === 'accepted') return 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800'
  if (d === 'rejected') return 'px-2 py-0.5 rounded text-xs bg-red-100 text-red-800'
  return 'px-2 py-0.5 rounded text-xs bg-yellow-100 text-yellow-800'
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
