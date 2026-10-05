<template>
  <div class="bar-chart">
    <canvas ref="canvasRef" data-storefront-block="charts.bar" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import Chart from 'chart.js/auto'
import { observeChartTheme, readChartChrome, readChartColor } from './chartTheme'

interface BarChartDataset {
  name: string
  data: number[]
  color: string
}

interface BarChartData {
  labels: string[]
  datasets: BarChartDataset[]
}

const props = defineProps<{
  data: BarChartData
  horizontal?: boolean
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null
let stopTheme: (() => void) | undefined

function buildChart() {
  if (!canvasRef.value) return
  if (chart) {
    chart.destroy()
  }
  const colors = readChartChrome(canvasRef.value, 0.05)

  chart = new Chart(canvasRef.value, {
    type: props.horizontal ? 'bar' : 'bar',
    data: {
      labels: props.data.labels,
      datasets: props.data.datasets.map((ds, index) => ({
        label: ds.name,
        data: ds.data,
        backgroundColor: readChartColor(canvasRef.value!, `chart-series-${index % 8 + 1}`, ds.color, 0.8),
        borderColor: readChartColor(canvasRef.value!, `chart-series-${index % 8 + 1}`, ds.color),
        borderWidth: 1,
        borderRadius: 4,
      })),
    },
    options: {
      indexAxis: props.horizontal ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: colors.legendText,
            usePointStyle: true,
            padding: 12,
          },
        },
        tooltip: colors.tooltip,
      },
      scales: {
        x: {
          ...colors.axis,
        },
        y: {
          ...colors.axis,
          beginAtZero: true,
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
onBeforeUnmount(() => { stopTheme?.(); chart?.destroy() })
</script>

<style scoped>
.bar-chart {
  height: 320px;
  position: relative;
}
</style>
