<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Всего запросов" :value="kpi('W-EXC-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Активных" :value="kpi('W-EXC-02')?.value" color="#4DA2F1" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Всего ставок" :value="kpi('W-EXC-03')?.value" color="#2E7D32" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Принято" :value="kpi('W-EXC-04')?.value" color="#F5A623" />
    </WidgetCard>

    <WidgetCard title="Динамика биржи" class="chart-wide">
      <LineChart :series="lineSeries('W-EXC-06')" />
    </WidgetCard>

    <WidgetCard title="Запросы на бирже" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">Статус</th>
              <th class="text-left py-2 px-3">Марка</th>
              <th class="text-left py-2 px-3">Модель</th>
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
            <tr v-for="(item, idx) in tableItems" :key="idx" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3"><span :class="statusClass(item.status)">{{ item.status_label || item.status }}</span></td>
              <td class="py-2 px-3">{{ item.mark || '—' }}</td>
              <td class="py-2 px-3">{{ item.model || '—' }}</td>
              <td class="py-2 px-3 text-right">{{ item.quantity }}</td>
              <td class="py-2 px-3">{{ item.discount_type_label || '—' }}</td>
              <td class="py-2 px-3 text-right">{{ formatDiscount(item) }}</td>
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
        :offset="(pagination.page - 1) * pagination.limit"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ExchangeTabResponse, ExchangeTableRow } from '../../api/analytics'
import { getWidgetKpi, getWidgetLineSeries, getWidgetTable, getWidgetPagination } from '../../api/analytics'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import KpiCard from '~/components/ui/analytics/KpiCard.vue'
import LineChart from '~/components/ui/analytics/LineChart.vue'
import SimplePagination from '~/components/ui/analytics/SimplePagination.vue'

const props = defineProps<{
  data: ExchangeTabResponse | null
  loading: boolean
}>()

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const kpi = (key: string) => getWidgetKpi(props.data?.widgets || {}, key)
const lineSeries = (key: string) => getWidgetLineSeries(props.data?.widgets || {}, key)

const tableItems = computed(() =>
  getWidgetTable<ExchangeTableRow>(props.data?.widgets || {}, 'W-EXC-07'),
)

const pagination = computed(() => getWidgetPagination(props.data?.widgets || {}, 'W-EXC-07'))

function formatPrice(v: number) {
  if (!v) return '—'
  return formatSharedPrice(v)
}

function formatDate(d: string) {
  if (!d || d === 'null') return '—'
  return formatSharedDate(d)
}

const PERCENT_DISCOUNT_TYPES = new Set(['percent', 'percentage'])

function formatDiscount(item: ExchangeTableRow) {
  if (!item.discount_value) return '—'
  // Percent discounts are clamped to 0..100 by the backend; everything else is
  // treated as a fixed-sum amount.
  if (PERCENT_DISCOUNT_TYPES.has((item.discount_type || '').toLowerCase())) {
    return `${item.discount_value}%`
  }
  return formatPrice(item.discount_value)
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

.kpi-span-3 {
  grid-column: span 3;
  padding: 16px;
}

.chart-wide {
  grid-column: span 12;
}

@media (max-width: 1024px) {
  .kpi-span-3 {
    grid-column: span 4;
  }
}

</style>
