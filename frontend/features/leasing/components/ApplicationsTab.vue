<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Всего" :value="kpi('W-APP-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Новых" :value="kpi('W-APP-02')?.value" color="#4DA2F1" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Одобрено" :value="kpi('W-APP-03')?.value" color="#2E7D32" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Отказано" :value="kpi('W-APP-04')?.value" color="#FF3D64" />
    </WidgetCard>
    <WidgetCard class="kpi-span-2">
      <KpiCard title="Ср. срок (дн.)" :value="kpi('W-APP-05')?.value" color="#DB9101" />
    </WidgetCard>

    <WidgetCard title="Динамика заявок" class="chart-wide">
      <LineChart :series="lineSeries('W-APP-07')" />
    </WidgetCard>

    <WidgetCard v-if="hasBarData('W-APP-06')" title="Количество заявок по статусам" class="chart-half">
      <BarChart :data="barData('W-APP-06')!" />
    </WidgetCard>

    <WidgetCard title="Список заявок" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">№</th>
              <th class="text-left py-2 px-3">Дата</th>
              <th class="text-left py-2 px-3">Марка</th>
              <th class="text-left py-2 px-3">Модель</th>
              <th class="text-left py-2 px-3">Статус</th>
              <th class="text-right py-2 px-3">Сумма</th>
              <th class="text-right py-2 px-3">ПВ</th>
              <th class="text-right py-2 px-3">Срок</th>
              <th class="text-right py-2 px-3">Платёж</th>
              <th class="text-right py-2 px-3">Ставка</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in tableItems" :key="item.display_number" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.display_number }}</td>
              <td class="py-2 px-3">{{ formatDate(item.created_at) }}</td>
              <td class="py-2 px-3">{{ item.mark_id }}</td>
              <td class="py-2 px-3">{{ item.model_id }}</td>
              <td class="py-2 px-3"><span :class="statusClass(item.status)">{{ formatStatus(item.status) }}</span></td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.total_amount) }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.down_payment) }}</td>
              <td class="py-2 px-3 text-right">{{ item.lease_term_months }}</td>
              <td class="py-2 px-3 text-right">{{ formatPrice(item.monthly_payment) }}</td>
              <td class="py-2 px-3 text-right">{{ item.rate }}%</td>
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
import { getWidgetKpi, getWidgetLineSeries, getWidgetBarChart } from '../api/analytics'
import KpiCard from '~/components/ui/analytics/KpiCard.vue'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import LineChart from '~/components/ui/analytics/LineChart.vue'
import BarChart from '~/components/ui/analytics/BarChart.vue'
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

function hasBarData(key: string) {
  const d = getWidgetBarChart(props.data?.widgets || {}, key)
  return !!d && d.labels.length > 0
}
const barData = (key: string) => getWidgetBarChart(props.data?.widgets || {}, key)

const tableItems = computed(() => {
  const w = props.data?.widgets?.['W-APP-08']
  if (w && typeof w === 'object' && 'items' in w) return (w as any).items
  return []
})

const pagination = computed(() => {
  const w = props.data?.widgets?.['W-APP-08']
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

function formatStatus(s: string) {
  const map: Record<string, string> = {
    submitted: 'Подана',
    under_review: 'На рассмотрении',
    under_review_with_docs: 'На рассмотрении с доп. документами',
    approved_scoring: 'Одобрено на скоринге',
    approved_scoring_another_cond: 'Одобрено на других условиях',
    rejected_prescoring: 'Отказано на скоринге',
    documents_required: 'Требуются доп доки',
    approved_final: 'Одобрение итоговое',
    approved_final_another_cond: 'Одобрение итоговое на других условиях',
    rejected_approved: 'Отказано после рассмотрения',
    selected_lc: 'Выбрана ЛК',
    deal: 'Профинансировано',
    closed: 'Закрыта клиентом',
  }
  return map[s] || s
}

function statusClass(s: string) {
  const map: Record<string, string> = {
    submitted: 'px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-800',
    under_review: 'px-2 py-0.5 rounded text-xs bg-yellow-100 text-yellow-800',
    under_review_with_docs: 'px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800',
    approved_scoring: 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800',
    approved_scoring_another_cond: 'px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-800',
    rejected_prescoring: 'px-2 py-0.5 rounded text-xs bg-red-100 text-red-800',
    documents_required: 'px-2 py-0.5 rounded text-xs bg-orange-100 text-orange-800',
    approved_final: 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800',
    approved_final_another_cond: 'px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-800',
    rejected_approved: 'px-2 py-0.5 rounded text-xs bg-red-100 text-red-800',
    selected_lc: 'px-2 py-0.5 rounded text-xs bg-purple-100 text-purple-800',
    deal: 'px-2 py-0.5 rounded text-xs bg-teal-100 text-teal-800',
    closed: 'px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-800',
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

.chart-half {
  grid-column: span 6;
}

@media (max-width: 1024px) {
  .chart-half {
    grid-column: span 12;
  }
  .kpi-span-2 {
    grid-column: span 3;
  }
  .kpi-span-3 {
    grid-column: span 4;
  }
}

</style>
