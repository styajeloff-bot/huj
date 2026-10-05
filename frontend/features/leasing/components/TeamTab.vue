<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Сотрудников дилера" :value="kpi('W-TEA-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Проверяющих ЛК" :value="kpi('W-TEA-02')?.value" color="#4DA2F1" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Заявок на сотрудника" :value="kpi('W-TEA-03')?.value" color="#2E7D32" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Документов на проверяющего" :value="kpi('W-TEA-04')?.value" color="#F5A623" />
    </WidgetCard>

    <WidgetCard title="Сотрудники дилера" class="chart-half">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">Имя</th>
              <th class="text-right py-2 px-3">Заявки</th>
              <th class="text-right py-2 px-3">Одобрено</th>
              <th class="text-right py-2 px-3">Отказано</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in dealerItems" :key="item.employee_id" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.employee_name }}</td>
              <td class="py-2 px-3 text-right">{{ item.applications_count }}</td>
              <td class="py-2 px-3 text-right">{{ item.approved_count }}</td>
              <td class="py-2 px-3 text-right">{{ item.rejected_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="dealerPagination"
        :total="dealerPagination.total"
        :limit="dealerPagination.limit"
        :offset="dealerPagination.offset"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>

    <WidgetCard title="Проверяющие ЛК" class="chart-half">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3">Имя</th>
              <th class="text-right py-2 px-3">Документы</th>
              <th class="text-right py-2 px-3">Одобрено</th>
              <th class="text-right py-2 px-3">Отказано</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in lcItems" :key="item.employee_id" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ item.employee_name }}</td>
              <td class="py-2 px-3 text-right">{{ item.documents_count }}</td>
              <td class="py-2 px-3 text-right">{{ item.approved_count }}</td>
              <td class="py-2 px-3 text-right">{{ item.rejected_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="lcPagination"
        :total="lcPagination.total"
        :limit="lcPagination.limit"
        :offset="lcPagination.offset"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LkDashboardResponse } from '../api/analytics'
import { getWidgetKpi } from '../api/analytics'
import KpiCard from '~/components/ui/analytics/KpiCard.vue'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import SimplePagination from '~/components/ui/analytics/SimplePagination.vue'

const props = defineProps<{
  data: LkDashboardResponse | null
  loading: boolean
}>()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const kpi = (key: string) => getWidgetKpi(props.data?.widgets || {}, key)

const dealerItems = computed(() => {
  const w = props.data?.widgets?.['W-TEA-05']
  if (w && typeof w === 'object' && 'items' in w) return (w as any).items
  return []
})

const dealerPagination = computed(() => {
  const w = props.data?.widgets?.['W-TEA-05']
  if (w && typeof w === 'object' && 'pagination' in w) return (w as any).pagination
  return null
})

const lcItems = computed(() => {
  const w = props.data?.widgets?.['W-TEA-06']
  if (w && typeof w === 'object' && 'items' in w) return (w as any).items
  return []
})

const lcPagination = computed(() => {
  const w = props.data?.widgets?.['W-TEA-06']
  if (w && typeof w === 'object' && 'pagination' in w) return (w as any).pagination
  return null
})
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

.chart-half {
  grid-column: span 6;
}

@media (max-width: 1024px) {
  .chart-half {
    grid-column: span 12;
  }
  .kpi-span-3 {
    grid-column: span 4;
  }
  .kpi-span-2 {
    grid-column: span 3;
  }
}

</style>
