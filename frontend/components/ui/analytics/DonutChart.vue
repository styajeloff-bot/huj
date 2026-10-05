<template>
  <div class="donut-chart">
    <canvas ref="canvasRef" data-storefront-block="charts.donut" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import Chart from 'chart.js/auto'
import { observeChartTheme, readChartChrome, readChartColor } from './chartTheme'

interface DonutSlice {
  label: string
  value: number
  color: string
}

const props = defineProps<{
  data: DonutSlice[]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null
let stopTheme: (() => void) | undefined

function buildChart() {
  if (!canvasRef.value) return
  if (chart) {
    chart.destroy()
  }

  const labels = props.data.map(d => d.label)
  const values = props.data.map(d => d.value)
  const colors = props.data.map((d, index) =>
    readChartColor(canvasRef.value!, `chart-series-${index % 8 + 1}`, d.color))
  const chrome = readChartChrome(canvasRef.value)

  chart = new Chart(canvasRef.value, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderWidth: 2,
          borderColor: readChartColor(canvasRef.value, 'chart-segment-border', '#FFFFFF'),
          hoverOffset: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '60%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: chrome.legendText,
            usePointStyle: true,
            padding: 16,
            font: {
              size: 12,
            },
          },
        },
        tooltip: {
          ...chrome.tooltip,
          callbacks: {
            label: (context) => {
              const total = context.dataset.data.reduce((a, b) => a + b, 0)
              const value = context.raw as number
              const percent = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0'
              return ` ${context.label}: ${value.toLocaleString('ru-RU')} (${percent}%)`
            },
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
watch(() => props.data, buildChart, { deep: true })
onBeforeUnmount(() => {
  stopTheme?.()
  chart?.destroy()
  chart = null
})
</script>

<style scoped>
.donut-chart {
  height: 320px;
  position: relative;
}
</style>
