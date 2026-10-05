export function readChartColor(
  canvas: HTMLCanvasElement,
  token: string,
  fallback: string,
  opacity = 1,
): string {
  let color = fallback
  if (canvas.closest('.storefront-theme')) {
    const configured = canvas.ownerDocument.defaultView?.getComputedStyle(canvas)
      .getPropertyValue(`--storefront-${token}`).trim()
    if (configured && /^#[\dA-F]{6}$/i.test(configured)) color = configured
  }
  if (opacity === 1 || !/^#[\dA-F]{6}$/i.test(color)) return color
  const rgb = [1, 3, 5].map(index => Number.parseInt(color.slice(index, index + 2), 16))
  return `rgba(${rgb.join(', ')}, ${opacity})`
}

const CHART_TOKENS = [
  ...Array.from({ length: 8 }, (_, index) => `chart-series-${index + 1}`),
  'chart-axis-text', 'chart-legend-text', 'chart-title', 'chart-grid', 'chart-axis-border',
  'chart-tooltip-background', 'chart-tooltip-title', 'chart-tooltip-text', 'chart-tooltip-border',
  'chart-segment-border',
]

export function readChartChrome(canvas: HTMLCanvasElement, gridOpacity = 0.1) {
  return {
    legendText: readChartColor(canvas, 'chart-legend-text', '#666666'),
    titleText: readChartColor(canvas, 'chart-title', '#666666'),
    axis: {
      grid: { color: readChartColor(canvas, 'chart-grid', '#000000', gridOpacity) },
      border: { color: readChartColor(canvas, 'chart-axis-border', '#000000', 0.1) },
      ticks: { color: readChartColor(canvas, 'chart-axis-text', '#666666') },
    },
    tooltip: {
      backgroundColor: readChartColor(canvas, 'chart-tooltip-background', '#000000', 0.8),
      titleColor: readChartColor(canvas, 'chart-tooltip-title', '#FFFFFF'),
      bodyColor: readChartColor(canvas, 'chart-tooltip-text', '#FFFFFF'),
      footerColor: readChartColor(canvas, 'chart-tooltip-text', '#FFFFFF'),
      borderColor: readChartColor(canvas, 'chart-tooltip-border', '#000000'),
      borderWidth: canvas.closest('.storefront-theme') ? 1 : 0,
    },
  }
}

/** Canvas paints resolved colors, not CSS var() expressions. Observe only theme
 * inputs and redraw when their computed palette changes; never change Chart.defaults.
 */
export function observeChartTheme(canvas: HTMLCanvasElement, redraw: () => void): () => void {
  const document = canvas.ownerDocument
  const view = document.defaultView
  if (!view) return () => {}
  const signature = () => {
    if (!canvas.closest('.storefront-theme')) return ''
    const style = view.getComputedStyle(canvas)
    return CHART_TOKENS.map(token => style.getPropertyValue(`--storefront-${token}`)).join('|')
  }
  let previous = signature()
  let pending: number | null = null
  const observer = new MutationObserver(() => {
    if (pending !== null) return
    pending = view.requestAnimationFrame(() => {
      pending = null
      const current = signature()
      if (current === previous) return
      previous = current
      redraw()
    })
  })
  for (let node: Element | null = canvas; node; node = node.parentElement) {
    observer.observe(node, { attributes: true, attributeFilter: ['style', 'class', 'data-storefront-block'] })
  }
  observer.observe(document.head, { childList: true, characterData: true, subtree: true })
  return () => {
    observer.disconnect()
    if (pending !== null) view.cancelAnimationFrame(pending)
  }
}
