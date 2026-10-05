<template>
  <div class="combo-chart">
    <canvas ref="canvasRef" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import Chart from 'chart.js/auto'
import type { ComboChartData } from '../api/analytics'

const props = defineProps<{
  data: ComboChartData
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let chart: Chart | null = null

function buildChart() {
  if (!canvasRef.value) return
  if (chart) {
    chart.destroy()
  }

  const labels = props.data.labels
  const barDatasets = props.data.barDatasets.map((ds) => ({
    label: ds.name,
    data: ds.data,
    backgroundColor: ds.color + 'CC',
    borderColor: ds.color,
    borderWidth: 1,
    borderRadius: 4,
    type: 'bar' as const,
  }))

  const lineDataset = props.data.lineDataset
    ? {
        label: props.data.lineDataset.name,
        data: props.data.lineDataset.data.map((d) => d.y),
        borderColor: props.data.lineDataset.color,
        backgroundColor: props.data.lineDataset.color + '20',
        fill: false,
        tension: 0.3,
        pointRadius: 4,
        pointHoverRadius: 6,
        borderDash: props.data.lineDataset.dashed ? [6, 2] : undefined,
        type: 'line' as const,
      }
    : null

  chart = new Chart(canvasRef.value, {
    type: 'bar',
    data: {
      labels,
      datasets: lineDataset ? [...barDatasets, lineDataset] : barDatasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            usePointStyle: true,
            padding: 12,
          },
        },
      },
      scales: {
        x: {
          grid: {
            color: 'rgba(0,0,0,0.05)',
          },
        },
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(0,0,0,0.05)',
          },
        },
      },
    },
  } as any)
}

onMounted(buildChart)
watch(() => props.data, buildChart, { deep: true })
</script>

<style scoped>
.combo-chart {
  height: 320px;
  position: relative;
}
</style>
