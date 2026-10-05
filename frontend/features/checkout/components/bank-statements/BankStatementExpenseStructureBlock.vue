<template>
  <div data-storefront-block="client.checkout" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
    <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">Структура расходов</h4>
    <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Структура расходов {{ formattedTotal }}</p>

    <div v-if="chartData.length === 0" class="mt-4 rounded-md bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-6 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
      Нет данных за выбранный период
    </div>
    <DonutChart
      v-else
      class="mt-3"
      :data="chartData"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DonutChart from '~/components/ui/analytics/DonutChart.vue'
import type { BankStatementExpenseSlice } from '../../types/bankStatementAnalytics'

const props = defineProps<{
  items: BankStatementExpenseSlice[]
}>()

const { formatMoneyCompact } = useFormatPrice()

// Workspace fallbacks; DonutChart resolves each series from its storefront scope.
const colors = [
  '#2563eb',
  '#16a34a',
  '#dc2626',
  '#9333ea',
  '#f59e0b',
  '#0891b2',
  '#db2777',
  '#4b5563',
]

const total = computed(() => props.items.reduce((sum, item) => sum + Number(item.amount || 0), 0))
const formattedTotal = computed(() => formatMoneyCompact(total.value))
const chartData = computed(() => {
  if (total.value <= 0) return []
  return props.items
    .filter((item) => Number(item.amount || 0) > 0)
    .map((item, index) => ({
      label: item.operation_kind || 'Без категории',
      value: Number(item.amount || 0),
      color: colors[index % colors.length],
    }))
})
</script>
