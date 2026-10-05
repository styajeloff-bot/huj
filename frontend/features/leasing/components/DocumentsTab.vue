<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Всего" :value="kpi('W-DOC-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Одобрено" :value="kpi('W-DOC-02')?.value" color="#2E7D32" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="На проверке" :value="kpi('W-DOC-03')?.value" color="#F5A623" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Отклонено" :value="kpi('W-DOC-04')?.value" color="#FF3D64" />
    </WidgetCard>

    <WidgetCard title="Динамика документов" class="chart-wide">
      <LineChart :series="lineSeries('W-DOC-06')" />
    </WidgetCard>

    <WidgetCard title="Список документов" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">Тип</th>
              <th class="text-left py-2 px-3">Файл</th>
              <th class="text-left py-2 px-3">Статус</th>
              <th class="text-left py-2 px-3">Статус ЛК</th>
              <th class="text-left py-2 px-3">Проверил</th>
              <th class="text-left py-2 px-3">Дата</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in tableItems" :key="item.document_id" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.document_type }}</td>
              <td class="py-2 px-3">{{ item.file_name }}</td>
              <td class="py-2 px-3"><span :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span></td>
              <td class="py-2 px-3"><span :class="statusClass(item.lc_status)">{{ statusLabel(item.lc_status) }}</span></td>
              <td class="py-2 px-3">{{ item.reviewer_name || '—' }}</td>
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

const { formatDate: formatSharedDate } = useFormatDate()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const kpi = (key: string) => getWidgetKpi(props.data?.widgets || {}, key)
const lineSeries = (key: string) => getWidgetLineSeries(props.data?.widgets || {}, key)

const tableItems = computed(() => {
  const w = props.data?.widgets?.['W-DOC-07']
  if (w && typeof w === 'object' && 'items' in w) return (w as any).items
  return []
})

const pagination = computed(() => {
  const w = props.data?.widgets?.['W-DOC-07']
  if (w && typeof w === 'object' && 'pagination' in w) return (w as any).pagination
  return null
})

function formatDate(d: string) {
  if (!d || d === 'null') return '—'
  return formatSharedDate(d)
}

function statusLabel(s: string) {
  const map: Record<string, string> = {
    pending: 'На проверке',
    approved: 'Одобрено',
    rejected: 'Отклонено',
    uploaded: 'Загружен',
  }
  return map[s] || s
}

function statusClass(s: string) {
  const map: Record<string, string> = {
    pending: 'px-2 py-0.5 rounded text-xs bg-yellow-100 text-yellow-800',
    approved: 'px-2 py-0.5 rounded text-xs bg-green-100 text-green-800',
    rejected: 'px-2 py-0.5 rounded text-xs bg-red-100 text-red-800',
    uploaded: 'px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-800',
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

.kpi-span-2 {
  grid-column: span 2;
  padding: 16px;
}

.chart-wide {
  grid-column: span 12;
}

@media (max-width: 1024px) {
  .kpi-span-3 {
    grid-column: span 4;
  }
  .kpi-span-2 {
    grid-column: span 3;
  }
}

</style>
