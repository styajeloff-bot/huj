<template>
  <div data-storefront-block="client.checkout" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
    <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">Ключевые показатели</h4>
    <div class="mt-3 grid grid-cols-2 gap-3 xl:grid-cols-4">
      <div
        v-for="metric in metrics"
        :key="metric.key"
        class="min-h-[92px] rounded-md border border-[color:var(--storefront-border,#f3f4f6)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3"
      >
        <KpiCard
          :title="metric.label"
          :value="metric.value ?? undefined"
          suffix="₽"
          :color="metric.color"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import KpiCard from '~/components/ui/analytics/KpiCard.vue'
import type { BankStatementAnalyticsKpi } from '../../types/bankStatementAnalytics'

const props = defineProps<{
  kpi: BankStatementAnalyticsKpi
}>()

const balanceChangeColor = computed(() => {
  const value = props.kpi.balance_change
  if (!value) return 'var(--storefront-text, #111827)'
  return value > 0 ? 'var(--storefront-success-text, #047857)' : 'var(--storefront-error-text, #dc2626)'
})

const metrics = computed(() => [
  { key: 'income', label: 'Поступления', value: props.kpi.income, color: undefined },
  { key: 'expense', label: 'Списания', value: props.kpi.expense, color: undefined },
  { key: 'turnover', label: 'Общий оборот', value: props.kpi.turnover, color: undefined },
  { key: 'average_monthly_turnover', label: 'Среднемесячный оборот', value: props.kpi.average_monthly_turnover, color: undefined },
  { key: 'external_revenue', label: 'Внешняя выручка', value: props.kpi.external_revenue, color: undefined },
  { key: 'opening_balance', label: 'Начальный остаток', value: props.kpi.opening_balance, color: undefined },
  { key: 'closing_balance', label: 'Конечный остаток', value: props.kpi.closing_balance, color: undefined },
  { key: 'balance_change', label: 'Изменение остатка', value: props.kpi.balance_change, color: balanceChangeColor.value },
])
</script>
