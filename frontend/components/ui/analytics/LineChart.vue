<template>
  <div class="line-chart">
    <canvas ref="canvasRef" data-storefront-block="charts.line" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import Chart from 'chart.js/auto'
import { observeChartTheme, readChartChrome, readChartColor } from './chartTheme'

interface ChartPoint {
  x: string
  y: number
}

interface LineChartSeries {
  name: string
  color: string
  data: ChartPoint[]
  dashed?: boolean
}

const props = defineProps<{
  series: LineChartSeries[]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null
let stopTheme: (() => void) | undefined

function buildChart() {
  if (!canvasRef.value) return
  if (chart) {
    chart.destroy()
  }

  if (!props.series.length) {
    chart = new Chart(canvasRef.value, {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
      },
    })
    return
  }

  const labels = props.series[0]?.data.map(d => d.x) || []
  const colors = readChartChrome(canvasRef.value)

  chart = new Chart(canvasRef.value, {
    type: 'line',
    data: {
      labels,
      datasets: props.series.map((s, index) => ({
        label: s.name,
        data: s.data.map(d => d.y),
        borderColor: readChartColor(canvasRef.value!, `chart-series-${index % 8 + 1}`, s.color),
        backgroundColor: readChartColor(canvasRef.value!, `chart-series-${index % 8 + 1}`, s.color, 32 / 255),
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointHoverRadius: 6,
        borderDash: s.dashed ? [6, 2] : undefined,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: colors.legendText },
        },
        tooltip: colors.tooltip,
      },
      scales: {
        x: { ...colors.axis },
        y: {
          ...colors.axis,
          beginAtZero: true,
          ticks: {
            ...colors.axis.ticks,
            precision: 0,
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
watch(() => props.series, buildChart, { deep: true })
onBeforeUnmount(() => { stopTheme?.(); chart?.destroy() })
</script>

<style scoped>
.line-chart {
  height: 320px;
  position: relative;
}
</style>
