<template>
  <div class="dash-grid">
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Новые заявки" :value="kpi('W-OVR-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Одобрено" :value="kpi('W-OVR-03')?.value" color="#2E7D32" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Выдано" :value="kpi('W-OVR-04')?.value" color="#4DA2F1" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Отказано" :value="kpi('W-OVR-05')?.value" color="#FF3D64" />
    </WidgetCard>

    <WidgetCard title="Динамика заявок шт (новые и профинансированные)" class="chart-wide">
      <LineChart :series="lineSeries('W-OVR-09')" />
    </WidgetCard>

    <WidgetCard v-if="hasBarData('W-OVR-11')" title="Количество заявок по статусам" class="chart-half">
      <BarChart :data="barData('W-OVR-11')!" />
    </WidgetCard>
    <WidgetCard v-if="hasBarData('W-OVR-12')" title="ТАТ, дней" class="chart-half">
      <BarChart :data="barData('W-OVR-12')!" horizontal />
    </WidgetCard>

    <WidgetCard v-if="hasDonut('W-OVR-10')" title="Распределение по статусам" class="chart-wide">
      <DonutChart :data="donutData('W-OVR-10')" />
    </WidgetCard>

    <WidgetCard class="kpi-span-3">
      <KpiCard title="На рассмотрении" :value="kpi('W-OVR-02')?.value" color="#F5A623" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Объём одобрено" :value="kpi('W-OVR-06')?.value" color="#2E7D32" prefix="₽" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Объём выдано" :value="kpi('W-OVR-07')?.value" color="#2E7D32" prefix="₽" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Ср. чек одобр." :value="kpi('W-OVR-08')?.value" color="#0077CC" prefix="₽" />
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import type { LkDashboardResponse } from '../api/analytics'
import {
  getWidgetKpi,
  getWidgetLineSeries,
  getWidgetDonut,
  getWidgetBarChart,
} from '../api/analytics'
import KpiCard from '~/components/ui/analytics/KpiCard.vue'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import LineChart from '~/components/ui/analytics/LineChart.vue'
import BarChart from '~/components/ui/analytics/BarChart.vue'
import DonutChart from '~/components/ui/analytics/DonutChart.vue'

const props = defineProps<{
  data: LkDashboardResponse | null
}>()

const kpi = (key: string) => getWidgetKpi(props.data?.widgets || {}, key)
const lineSeries = (key: string) => getWidgetLineSeries(props.data?.widgets || {}, key)

function hasDonut(key: string) {
  const d = getWidgetDonut(props.data?.widgets || {}, key)
  return d.length > 0
}
const donutData = (key: string) => getWidgetDonut(props.data?.widgets || {}, key)

function hasBarData(key: string) {
  const d = getWidgetBarChart(props.data?.widgets || {}, key)
  return !!d && d.labels.length > 0
}
const barData = (key: string) => getWidgetBarChart(props.data?.widgets || {}, key)
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
