<template>
  <div class="dash-grid">
    <!-- Table 1: Продажи по маркам -->
    <WidgetCard title="Продажи по маркам" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3 font-medium">Месяц</th>
              <th class="text-left py-2 px-3 font-medium">Марка</th>
              <th class="text-left py-2 px-3 font-medium">Модель</th>
              <th
                v-for="col in markColumns"
                :key="col"
                class="text-right py-2 px-3 font-medium"
              >
                {{ col }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in markRows" :key="idx" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ row.month }}</td>
              <td class="py-2 px-3">{{ row.mark }}</td>
              <td class="py-2 px-3">{{ row.model }}</td>
              <td
                v-for="col in markColumns"
                :key="col"
                class="py-2 px-3 text-right"
              >
                {{ Number(row[col] || 0).toLocaleString('ru-RU') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <SimplePagination
        v-if="markPagination"
        :total="markPagination.total"
        :limit="markPagination.limit"
        :offset="(markPagination.page - 1) * markPagination.limit"
        @change="$emit('page-change', $event)"
      />
    </WidgetCard>

    <!-- Table 2: Продажи по городам -->
    <WidgetCard title="Продажи по городам" class="chart-wide">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b text-gray-500 bg-gray-50">
              <th class="text-left py-2 px-3 font-medium">Месяц</th>
              <th class="text-left py-2 px-3 font-medium">Город</th>
              <th
                v-for="col in cityColumns"
                :key="col"
                class="text-right py-2 px-3 font-medium"
              >
                {{ col }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, idx) in cityRows" :key="idx" class="border-b hover:bg-gray-50">
              <td class="py-2 px-3">{{ row.month }}</td>
              <td class="py-2 px-3">{{ row.city }}</td>
              <td
                v-for="col in cityColumns"
                :key="col"
                class="py-2 px-3 text-right"
              >
                {{ Number(row[col] || 0).toLocaleString('ru-RU') }}
              </td>
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
import type { SalesDcRegionsTabResponse } from '../../api/analytics'
import { getWidgetPagination } from '../../api/analytics'
import WidgetCard from '~/components/ui/analytics/WidgetCard.vue'
import SimplePagination from '~/components/ui/analytics/SimplePagination.vue'

const props = defineProps<{
  data: SalesDcRegionsTabResponse | null
  loading: boolean
}>()

defineEmits<{
  (e: 'page-change', offset: number): void
}>()

const markWidget = computed(() => {
  const w = props.data?.widgets?.['W-SDR-01']
  if (w && typeof w === 'object' && 'items' in w && 'columns' in w) {
    return w as { items: Record<string, any>[]; columns: string[]; pagination?: any }
  }
  return null
})

const markRows = computed(() => markWidget.value?.items || [])
const markColumns = computed(() => markWidget.value?.columns || [])
const markPagination = computed(() => markWidget.value?.pagination || null)

const cityWidget = computed(() => {
  const w = props.data?.widgets?.['W-SDR-02']
  if (w && typeof w === 'object' && 'items' in w && 'columns' in w) {
    return w as { items: Record<string, any>[]; columns: string[]; pagination?: any }
  }
  return null
})

const cityRows = computed(() => cityWidget.value?.items || [])
const cityColumns = computed(() => cityWidget.value?.columns || [])
const cityPagination = computed(() => cityWidget.value?.pagination || null)
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
