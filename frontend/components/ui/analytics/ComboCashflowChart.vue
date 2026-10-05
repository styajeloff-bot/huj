<template>
  <div class="combo-cashflow-chart">
    <canvas ref="canvasRef" data-storefront-block="charts.cashflow" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Chart from 'chart.js/auto'
import type { TooltipItem } from 'chart.js'
import { observeChartTheme, readChartChrome, readChartColor } from './chartTheme'

const props = defineProps<{
  labels: string[]
  income: number[]
  expense: number[]
  closingBalance: number[]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null
let stopTheme: (() => void) | undefined

const formatRubles = (value: number) => `${new Intl.NumberFormat('ru-RU').format(Math.round(value))} ₽`
const formatThousands = (value: number) => {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} млн`
  if (Math.abs(value) >= 1_000) return `${Math.round(value / 1_000)} тыс`
  return String(Math.round(value))
}

function buildChart() {
  if (!canvasRef.value) return
  chart?.destroy()
  const colors = readChartChrome(canvasRef.value, 0.06)
  const series = (index: number, fallback: string, opacity = 1) =>
    readChartColor(canvasRef.value!, `chart-series-${index}`, fallback, opacity)

  chart = new Chart(canvasRef.value, {
    type: 'bar',
    data: {
      labels: props.labels,
      datasets: [
        {
          type: 'bar',
          label: 'Поступления',
          data: props.income,
          backgroundColor: series(2, '#16A34A', 0.75),
          borderColor: series(2, '#16A34A'),
          borderWidth: 1,
          borderRadius: 4,
          order: 2,
        },
        {
          type: 'bar',
          label: 'Списания',
          data: props.expense,
          backgroundColor: series(3, '#DC2626', 0.72),
          borderColor: series(3, '#DC2626'),
          borderWidth: 1,
          borderRadius: 4,
          order: 2,
        },
        {
          type: 'line',
          label: 'Остаток',
          data: props.closingBalance,
          borderColor: series(1, '#2563EB'),
          backgroundColor: series(1, '#2563EB', 0.12),
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.25,
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: colors.legendText,
            boxWidth: 10,
            font: { size: 11 },
          },
        },
        tooltip: {
          ...colors.tooltip,
          callbacks: {
            label: (context: TooltipItem<'bar' | 'line'>) => `${context.dataset.label}: ${formatRubles(Number(context.raw || 0))}`,
          },
        },
      },
      scales: {
        x: {
          ...colors.axis,
          grid: { display: false },
        },
        y: {
          ...colors.axis,
          ticks: {
            ...colors.axis.ticks,
            callback: (value: string | number) => formatThousands(Number(value)),
          },
        },
      },
    },
  })
}

onMounted(() => {
  buildChart()
  if (canvasRef.value) stopTheme = observeChartTheme(canvasRef.value, buildChart)
})
watch(() => [props.labels, props.income, props.expense, props.closingBalance], buildChart, { deep: true })
onBeforeUnmount(() => {
  stopTheme?.()
  chart?.destroy()
})
</script>

<style scoped>
.combo-cashflow-chart {
  height: 320px;
  position: relative;
}
</style>
