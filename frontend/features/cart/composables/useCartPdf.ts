import { imageBlobToPdfSafeDataUrl } from '~/features/cart/utils/pdfImage'
import {
  commerceCartBillableQuantity,
  commerceCartLinePrice,
  type CommerceCartLine,
} from '~/features/commerce/cartProjection'
import { getCommerceLineDiscountSummary } from '~/utils/vehicleDiscount'
import type {
  CartCalculationData,
  SupportBreakdown,
} from '~/features/cart/types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

function formatPrice(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

async function getItemImageDataUrl(item: CommerceCartLine, config: RuntimeConfig) {
  const path = item.image_url
  if (!path?.startsWith('/api/')) return null
  const apiBase = String(config.public?.apiBase || '').replace(/\/$/, '')
  const imageUrl = apiBase
    ? `${apiBase}${path}`
    : (typeof window !== 'undefined' ? `${window.location.origin}${path}` : path)
  try {
    // nosemgrep: nodejs_scan.javascript-ssrf-rule-node_ssrf -- Browser-only fetch of a fixed API path.
    const response = await fetch(imageUrl, { credentials: 'include' })
    if (!response.ok) return null
    const blob = await response.blob()
    return await imageBlobToPdfSafeDataUrl(blob)
  } catch {
    return null
  }
}

function addSupportBlock(
  content: any[],
  support: SupportBreakdown | null,
) {
  if (!support) return
  const dp = Number(support.down_payment_support) || 0
  const vd = Number(support.vehicle_discount_support) || 0
  const in_ = Number(support.interest_support) || 0
  if (dp === 0 && vd === 0 && in_ === 0) return
  content.push({ text: 'Учтено в расчёте:', style: 'subheader' })
  if (dp > 0) {
    content.push({
      columns: [
        { text: 'Поддержка первого взноса', style: 'label' },
        { text: formatPrice(dp), style: 'value', alignment: 'right' },
      ],
      margin: [0, 0, 0, 4],
    })
  }
  if (vd > 0) {
    content.push({
      columns: [
        { text: 'Поддержка на ТС', style: 'label' },
        { text: formatPrice(vd), style: 'value', alignment: 'right' },
      ],
      margin: [0, 0, 0, 4],
    })
  }
  if (in_ > 0) {
    content.push({
      columns: [
        { text: 'Поддержка процентов', style: 'label' },
        { text: formatPrice(in_), style: 'value', alignment: 'right' },
      ],
      margin: [0, 0, 0, 4],
    })
  }
  content.push({ text: '\n' })
}

export interface CartPdfParams {
  down_payment_percent?: number
  lease_term_months?: number
  buyout_percent?: number
}

export const useCartPdf = (config: RuntimeConfig) => {
  const generatingCartPdf = ref(false)

  const downloadCartPdf = async (
    selectedItems: readonly CommerceCartLine[],
    calculationData: CartCalculationData | null,
    params: CartPdfParams,
    totalAmount: number,
    toast: any,
  ) => {
    if (!selectedItems.length) return
    generatingCartPdf.value = true
    try {
      const pdfMake = await import('pdfmake/build/pdfmake')
      const pdfFonts = await import('pdfmake/build/vfs_fonts')
      const pdfMakeInstance = (pdfMake as any).default || pdfMake
      if ((pdfFonts as any).pdfMake?.vfs) pdfMakeInstance.vfs = (pdfFonts as any).pdfMake.vfs
      else if ((pdfFonts as any).default) pdfMakeInstance.vfs = (pdfFonts as any).default
      else throw new Error('Шрифты PDF не загружены')

      const downPercent = params.down_payment_percent ?? 20
      const termMonths = params.lease_term_months ?? 36
      const buyoutPct = params.buyout_percent ?? 0
      const content: any[] = []

      content.push({ text: 'Расчет лизинга — выбранные ТС и общий расчет', style: 'header', alignment: 'center' })
      content.push({ text: '\n' })

      const perVehicleCalcs = calculationData?.calculations_per_vehicle || []

      for (let idx = 0; idx < selectedItems.length; idx++) {
        const item = selectedItems[idx]
        if (idx > 0) {
          content.push({ text: '', margin: [0, 12, 0, 0] })
          content.push({
            table: { body: [['']], widths: ['*'] },
            layout: { hLineWidth: (i: number) => (i === 1 ? 0.5 : 0), vLineWidth: () => 0 },
            margin: [0, 4, 0, 12],
          })
        }
        const quantity = Math.max(1, Number(item.quantity) || 1)
        const pricePerUnit = commerceCartLinePrice(item)
        let calcResult = null
        let itemSupport = null
        const perVehicle = item.ref.type === 'vehicle'
          ? perVehicleCalcs.find((row) => row.vehicle_id === item.ref.id)
          : null
        if (perVehicle) {
          calcResult = perVehicle.calculation ?? null
          itemSupport = perVehicle.support_breakdown ?? null
        }

        const vehicleTitle = `${item.mark_name || ''} ${item.model_name || ''}`.trim() || 'Транспортное средство'
        const imageDataUrl = await getItemImageDataUrl(item, config)

        const hasOverstock = item.ref.type === 'special_equipment'
          && item.allow_overstock
          && typeof item.available_count === 'number'
          && quantity > item.available_count
        const quantityLine = hasOverstock
          ? `Количество: ${quantity} шт. (в наличии ${item.available_count}, сверх наличия ${quantity - (item.available_count ?? 0)} — не входят в расчёт)`
          : `Количество: ${quantity}`

        const discountSummary = item.ref.type === 'special_equipment'
          ? getCommerceLineDiscountSummary(item)
          : null

        const stackItems: any[] = [
          { text: `Цена за 1 ТС: ${formatPrice(pricePerUnit)}`, style: 'normal' },
        ]
        if (discountSummary) {
          stackItems.push(
            { text: `Выгода: −${formatPrice(discountSummary.amount)} (${discountSummary.percent}%)`, style: 'normal' },
            { text: `Цена с выгодой: ${formatPrice(discountSummary.discountedPrice)}`, style: 'normal' },
          )
        }
        stackItems.push(
          { text: quantityLine, style: 'normal' },
          { text: `Срок договора: ${termMonths} мес.`, style: 'normal' },
          { text: `Выкупная стоимость: ${buyoutPct}%`, style: 'normal' },
        )

        content.push({ text: vehicleTitle, style: 'sectionHeader' })
        content.push({
          columns: [
            imageDataUrl ? { image: imageDataUrl, fit: [140, 90], margin: [0, 0, 12, 0] } : { text: '', width: 0 },
            {
              width: '*',
              stack: stackItems,
            },
          ],
        })
        content.push({ text: '\n' })

        const blockTitle = quantity > 1 ? `Расчет на ${quantity} ТС` : 'Расчет на 1 ТС'
        content.push({ text: blockTitle, style: 'subheader' })
        const calcRows = calcResult
          ? [
              { label: 'Ежемесячный платёж', value: formatPrice(calcResult.monthlyPayment) },
              { label: 'Первоначальный взнос', value: `${downPercent}%` },
              { label: 'Сумма договора', value: formatPrice(calcResult.totalCost) },
            ]
          : [{ label: 'Статус', value: 'Нет данных расчета' }]
        for (const row of calcRows) {
          content.push({
            columns: [
              { text: row.label, style: 'label' },
              { text: row.value, style: 'value', alignment: 'right' },
            ],
            margin: [0, 0, 0, 4],
          })
        }
        addSupportBlock(content, itemSupport)

        content.push({ text: 'Подробные характеристики', style: 'subheader' })
        const details: { label: string; value: string }[] = []
        if (item.mark_name) details.push({ label: 'Марка', value: String(item.mark_name) })
        if (item.model_name) details.push({ label: 'Модель', value: String(item.model_name) })
        if (item.group_name) details.push({ label: 'Комплектация', value: String(item.group_name) })
        if (item.vin) details.push({ label: 'VIN', value: String(item.vin) })
        if (item.year) details.push({ label: 'Год', value: String(item.year) })
        if (item.color) details.push({ label: 'Цвет', value: String(item.color) })
        details.push({ label: item.ref.type === 'vehicle' ? 'Цена в каталоге' : 'Цена с выгодой', value: formatPrice(item.base_price || 0) })
        if (item.comment) details.push({ label: 'Комментарий', value: String(item.comment) })
        for (const row of details) {
          content.push({
            columns: [
              { text: row.label, style: 'label' },
              { text: row.value, style: 'value', alignment: 'right' },
            ],
            margin: [0, 0, 0, 4],
          })
        }
        content.push({ text: '\n' })
      }

      content.push({ text: 'Общий расчет (все выбранные ТС)', style: 'header', alignment: 'center' })
      content.push({ text: '\n' })
      const overallCalc = calculationData?.calculation ?? null
      const overallSupport = calculationData?.support ?? null
      content.push({ text: `Стоимость имущества: ${formatPrice(totalAmount)}`, style: 'subheader' })
      const appliedDiscountsTotal = selectedItems
        .filter(line => line.ref.type === 'special_equipment')
        .reduce((sum, line) => {
          const s = getCommerceLineDiscountSummary(line)
          return s ? sum + s.amount * commerceCartBillableQuantity(line) : sum
        }, 0)
      if (appliedDiscountsTotal > 0) {
        content.push({ text: `Выгода: −${formatPrice(appliedDiscountsTotal)}`, style: 'subheader' })
      }
      content.push({ text: `Срок договора: ${termMonths} мес.`, style: 'normal' })
      content.push({ text: `Первоначальный взнос: ${downPercent}%`, style: 'normal' })
      content.push({ text: `Выкупная стоимость: ${buyoutPct}%`, style: 'normal' })
      content.push({ text: '\n' })
      if (overallCalc) {
        content.push({
          columns: [
            { text: 'Ежемесячный платёж', style: 'label' },
            { text: formatPrice(overallCalc.monthlyPayment), style: 'value', alignment: 'right' },
          ],
          margin: [0, 0, 0, 4],
        })
        content.push({
          columns: [
            { text: 'Сумма договора', style: 'label' },
            { text: formatPrice(overallCalc.totalCost), style: 'value', alignment: 'right' },
          ],
          margin: [0, 0, 0, 4],
        })
      } else {
        content.push({
          text: 'Выполните расчет в калькуляторе выше для отображения общего ежемесячного платежа и суммы договора.',
          style: 'normal',
        })
      }
      addSupportBlock(content, overallSupport)

      const doc = pdfMakeInstance.createPdf({
        pageSize: 'A4',
        pageMargins: [36, 36, 36, 36],
        content,
        styles: {
          header: { fontSize: 18, bold: true, margin: [0, 0, 0, 10] },
          subheader: { fontSize: 13, bold: true, margin: [0, 0, 0, 6] },
          sectionHeader: { fontSize: 12, bold: true, margin: [0, 8, 0, 6] },
          normal: { fontSize: 10, margin: [0, 0, 0, 3] },
          label: { fontSize: 10, color: '#374151' },
          value: { fontSize: 10, bold: true, color: '#111827' },
        },
        defaultStyle: { fontSize: 10 },
      })
      doc.getBlob((blob: Blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `raschet-korzina-${Date.now()}.pdf`
        a.click()
        URL.revokeObjectURL(url)
      })
      toast?.success?.('PDF сформирован')
    } catch (e) {
      console.error('PDF error:', e)
      toast?.error?.('Не удалось сформировать PDF')
    } finally {
      generatingCartPdf.value = false
    }
  }

  return { generatingCartPdf, downloadCartPdf }
}
