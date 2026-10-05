<template>
  <div data-storefront-block="client.checkout" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
    <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">Динамика денежных потоков</h4>
    <div v-if="points.length === 0" class="mt-4 rounded-md bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-6 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
      Нет данных за выбранный период
    </div>
    <ComboCashflowChart
      v-else
      class="mt-3"
      :labels="labels"
      :income="income"
      :expense="expense"
      :closing-balance="closingBalance"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ComboCashflowChart from '~/components/ui/analytics/ComboCashflowChart.vue'
import type { BankStatementCashflowPoint } from '../../types/bankStatementAnalytics'

const props = defineProps<{
  points: BankStatementCashflowPoint[]
}>()

const monthFormatter = new Intl.DateTimeFormat('ru-RU', { month: 'short', year: 'numeric' })

const formatMonth = (month: string) => {
  const date = new Date(`${month}-01T00:00:00`)
  if (Number.isNaN(date.getTime())) return month
  return monthFormatter.format(date).replace('.', '')
}

const labels = computed(() => props.points.map((point) => formatMonth(point.month)))
const income = computed(() => props.points.map((point) => Number(point.income || 0)))
const expense = computed(() => props.points.map((point) => Number(point.expense || 0)))
const closingBalance = computed(() => props.points.map((point) => Number(point.closing_balance || 0)))
</script>
