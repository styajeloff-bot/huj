import { Chart, registerables } from 'chart.js'
import type { Ref } from 'vue'
import { onBeforeUnmount } from 'vue'
import { observeChartTheme, readChartChrome, readChartColor } from '~/components/ui/analytics/chartTheme'

Chart.register(...registerables)

interface Payment {
  month: number
  principal: number
  interest: number
  remainingBalance: number
}

interface ComparisonData {
  total: number
}

type CanvasRef = Ref<(HTMLCanvasElement & { chart?: Chart<keyof import('chart.js').ChartTypeRegistry> }) | null>

const formatRub = (value: number, fractionDigits = 2) =>
  `${new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: fractionDigits
  }).format(value)} ₽`

export const useChart = () => {
  const themeObservers = new Map<HTMLCanvasElement, () => void>()
  const observePalette = (canvas: HTMLCanvasElement, redraw: () => void) => {
    themeObservers.get(canvas)?.()
    themeObservers.set(canvas, observeChartTheme(canvas, redraw))
  }
  onBeforeUnmount(() => {
    for (const stop of themeObservers.values()) stop()
    themeObservers.clear()
  })

  const createPaymentChart = (canvasRef: CanvasRef, payments: Payment[]) => {
    if (!canvasRef.value || !payments || payments.length === 0) return null

    const ctx = canvasRef.value.getContext('2d')!
    if (canvasRef.value.chart) canvasRef.value.chart.destroy()
    canvasRef.value.dataset.storefrontBlock = 'charts.calculator-payment'
    const colors = readChartChrome(canvasRef.value)
    const series = (index: number, fallback: string, opacity = 1) =>
      readChartColor(canvasRef.value!, `chart-series-${index}`, fallback, opacity)

    const chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: payments.map((p) => `${p.month} мес`),
        datasets: [
          {
            label: 'Основной долг',
            data: payments.map((p) => p.principal),
            backgroundColor: series(1, '#3B82F6', 0.8),
            borderColor: series(1, '#3B82F6'),
            borderWidth: 1,
            stack: 'payment'
          },
          {
            label: 'Проценты',
            data: payments.map((p) => p.interest),
            backgroundColor: series(2, '#F97316', 0.8),
            borderColor: series(2, '#F97316'),
            borderWidth: 1,
            stack: 'payment'
          },
          {
            label: 'Остаток долга',
            data: payments.map((p) => p.remainingBalance),
            type: 'line',
            backgroundColor: series(3, '#22C55E', 0.2),
            borderColor: series(3, '#22C55E'),
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          title: {
            color: colors.titleText,
            display: true,
            text: 'График платежей по лизингу',
            font: { size: 16, weight: 'bold' }
          },
          legend: { position: 'top', labels: { color: colors.legendText } },
          tooltip: {
            ...colors.tooltip,
            mode: 'index',
            intersect: false,
            callbacks: {
              footer: (tooltipItems) => {
                let sum = 0
                tooltipItems.forEach((item) => {
                  if (item.datasetIndex < 2) sum += (item.parsed.y ?? 0)
                })
                return `Общий платеж: ${formatRub(sum)}`
              },
              label: (context) => {
                const label = context.dataset.label || ''
                return `${label}: ${formatRub(context.parsed.y ?? 0)}`
              }
            }
          }
        },
        scales: {
          x: { ...colors.axis, title: { display: true, text: 'Месяц', color: colors.axis.ticks.color } },
          y: {
            ...colors.axis,
            type: 'linear',
            display: true,
            position: 'left',
            title: { display: true, text: 'Платеж (₽)', color: colors.axis.ticks.color },
            ticks: { ...colors.axis.ticks, callback: (value) => formatRub(Number(value), 0) }
          },
          y1: {
            ...colors.axis,
            type: 'linear',
            display: true,
            position: 'right',
            title: { display: true, text: 'Остаток долга (₽)', color: colors.axis.ticks.color },
            grid: { ...colors.axis.grid, drawOnChartArea: false },
            ticks: { ...colors.axis.ticks, callback: (value) => formatRub(Number(value), 0) }
          }
        }
      }
    })

    canvasRef.value.chart = chart
    observePalette(canvasRef.value, () => createPaymentChart(canvasRef, payments))
    return chart
  }

  const createComparisonChart = (
    canvasRef: CanvasRef,
    leasingData: ComparisonData,
    creditData: ComparisonData,
    cashData: ComparisonData
  ) => {
    if (!canvasRef.value) return null

    const ctx = canvasRef.value.getContext('2d')!
    if (canvasRef.value.chart) canvasRef.value.chart.destroy()
    canvasRef.value.dataset.storefrontBlock = 'charts.calculator-comparison'
    const colors = readChartChrome(canvasRef.value)
    const series = (index: number, fallback: string, opacity = 1) =>
      readChartColor(canvasRef.value!, `chart-series-${index}`, fallback, opacity)

    const chart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Лизинг', 'Кредит', 'Наличные'],
        datasets: [
          {
            data: [leasingData.total, creditData.total, cashData.total],
            backgroundColor: [
              series(1, '#3B82F6', 0.8),
              series(2, '#F97316', 0.8),
              series(3, '#22C55E', 0.8)
            ],
            borderColor: [
              series(1, '#3B82F6'),
              series(2, '#F97316'),
              series(3, '#22C55E')
            ],
            borderWidth: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            color: colors.titleText,
            display: true,
            text: 'Сравнение способов покупки',
            font: { size: 16, weight: 'bold' }
          },
          legend: { position: 'bottom', labels: { color: colors.legendText } },
          tooltip: {
            ...colors.tooltip,
            callbacks: {
              label: (context) => {
                const label = context.label || ''
                const value = formatRub(context.raw as number)
                const total = (context.dataset.data as number[]).reduce((a, b) => a + b, 0)
                const percentage = (((context.raw as number) / total) * 100).toFixed(1)
                return `${label}: ${value} (${percentage}%)`
              }
            }
          }
        }
      }
    })

    canvasRef.value.chart = chart as Chart<keyof import('chart.js').ChartTypeRegistry>
    observePalette(canvasRef.value, () => createComparisonChart(canvasRef, leasingData, creditData, cashData))
    return chart
  }

  const destroyChart = (canvasRef: CanvasRef) => {
    if (canvasRef.value) {
      themeObservers.get(canvasRef.value)?.()
      themeObservers.delete(canvasRef.value)
    }
    if (canvasRef.value?.chart) {
      canvasRef.value.chart.destroy()
      canvasRef.value.chart = undefined
    }
  }

  return { createPaymentChart, createComparisonChart, destroyChart }
}
