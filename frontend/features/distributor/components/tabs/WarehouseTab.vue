<template>
  <div class="dash-grid">
    <!-- KPI Row -->
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Всего авто" :value="kpi('W-WHS-01')?.value" color="#1E69A9" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="В наличии" :value="kpi('W-WHS-02')?.value" color="#16a34a" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="В резерве" :value="kpi('W-WHS-03')?.value" color="#F5A623" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Продано" :value="kpi('W-WHS-04')?.value" color="#4DA2F1" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Общая стоимость" :value="kpi('W-WHS-05')?.value" color="#9333ea" prefix="₽" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Дилеры" :value="kpi('W-WHS-06')?.value" color="#ea580c" />
    </WidgetCard>
    <WidgetCard class="kpi-span-3">
      <KpiCard title="Средняя стоимость" :value="kpi('W-WHS-07')?.value" color="#00ACC1" prefix="₽" />
    </WidgetCard>

    <!-- Donut + Bar side by side -->
    <WidgetCard title="Распределение по статусам" class="chart-half">
      <DonutChart :data="donutData" />
    </WidgetCard>

    <WidgetCard title="По маркам и моделям (ТОП-10)" class="chart-half">
      <BarChart v-if="markBarData" :data="markBarData" horizontal />
    </WidgetCard>

    <!-- Monthly dynamics -->
    <WidgetCard title="Динамика по месяцам" class="chart-wide">
      <BarChart v-if="timelineBarData" :data="timelineBarData" />
    </WidgetCard>

    <!-- By dealer -->
    <WidgetCard title="По дилерам" class="chart-half">
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200 text-gray-500">
              <th class="text-left py-2 px-3 font-medium">Дилер</th>
              <th class="text-right py-2 px-3 font-medium">Кол-во авто</th>
              <th class="text-right py-2 px-3 font-medium">Стоимость</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="d in dealerItems"
              :key="d.dealer_name"
              class="border-b border-gray-100 hover:bg-gray-50"
            >
              <td class="py-2 px-3">{{ d.dealer_name }}</td>
              <td class="py-2 px-3 text-right">{{ d.count.toLocaleString('ru-RU') }}</td>
              <td class="py-2 px-3 text-right whitespace-nowrap tabular-nums">{{ formatPrice(d.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="dealerPagination"
        :total="dealerPagination.total"
        :limit="dealerPagination.limit"
        :offset="(dealerPagination.page - 1) * dealerPagination.limit"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>

    <!-- By city -->
    <WidgetCard title="По городам" class="chart-half">
      <div class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200 text-gray-500">
              <th class="text-left py-2 px-3 font-medium">Город</th>
              <th class="text-right py-2 px-3 font-medium">Кол-во</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in cityItems"
              :key="c.city"
              class="border-b border-gray-100 hover:bg-gray-50"
            >
              <td class="py-2 px-3">{{ c.city }}</td>
              <td class="py-2 px-3 text-right">{{ c.count.toLocaleString('ru-RU') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="cityPagination"
        :total="cityPagination.total"
        :limit="cityPagination.limit"
        :offset="(cityPagination.page - 1) * cityPagination.limit"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WarehouseTabResponse } from '../../api/analytics'
import { getWidgetKpi, getWidgetDonut, getWidgetBarChart, getWidgetTable, getWidgetPagination } from '../../api/analytics'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import KpiCard from '~/components/ui/analytics/KpiCard.vue'
import DonutChart from '~/components/ui/analytics/DonutChart.vue'
import BarChart from '~/components/ui/analytics/BarChart.vue'
import SimplePagination from '~/components/ui/analytics/SimplePagination.vue'

const props = defineProps<{
  data: WarehouseTabResponse | null
  loading: boolean
}>()

const { formatPrice } = useFormatPrice()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const kpi = (key: string) => getWidgetKpi(props.data?.widgets || {}, key)
const donutData = computed(() => getWidgetDonut(props.data?.widgets || {}, 'W-WHS-08'))
const markBarData = computed(() => getWidgetBarChart(props.data?.widgets || {}, 'W-WHS-09'))
const timelineBarData = computed(() => getWidgetBarChart(props.data?.widgets || {}, 'W-WHS-10'))

const dealerItems = computed(() => getWidgetTable<{ dealer_name: string; count: number; value: number }>(props.data?.widgets || {}, 'W-WHS-11'))
const dealerPagination = computed(() => getWidgetPagination(props.data?.widgets || {}, 'W-WHS-11'))

const cityItems = computed(() => getWidgetTable<{ city: string; count: number }>(props.data?.widgets || {}, 'W-WHS-12'))
const cityPagination = computed(() => getWidgetPagination(props.data?.widgets || {}, 'W-WHS-12'))
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

.chart-half {
  grid-column: span 6;
}

@media (max-width: 1024px) {
  .kpi-span-3 {
    grid-column: span 4;
  }
  .chart-half {
    grid-column: span 12;
  }
}

</style>
