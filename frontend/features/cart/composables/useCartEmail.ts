import {
  commerceCartBillableQuantity,
  commerceCartLinePrice,
  type CommerceCartLine,
} from '~/features/commerce/cartProjection'
import { getCommerceLineDiscountSummary } from '~/utils/vehicleDiscount'
import type {
  CartCalculationData,
  LeasingCalculationResult,
  SupportBreakdown,
} from '~/features/cart/types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

function formatPrice(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

function escapeHtml(value: unknown): string {
  if (value == null) return ''
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

export interface CartEmailParams {
  down_payment_percent?: number
  lease_term_months?: number
  buyout_percent?: number
}

interface EmailLineItem {
  vehicleTitle: string
  quantity: number
  quantityLine: string
  priceLine: string
  discountLines: string[]
  termMonths: number
  buyoutPct: number
  calcRows: { label: string; value: string }[]
  supportRow: string | null
  details: { label: string; value: string }[]
}

interface EmailData {
  downPercent: number
  termMonths: number
  buyoutPct: number
  items: EmailLineItem[]
  totalAmount: number
  appliedDiscountsTotal: number
  overallCalc: LeasingCalculationResult | null
  overallSupport: SupportBreakdown | null
}

export function buildEmailData(
  selectedItems: readonly CommerceCartLine[],
  calculationData: CartCalculationData | null,
  params: CartEmailParams,
  totalAmount: number,
): EmailData {
  const downPercent = params.down_payment_percent ?? 20
  const termMonths = params.lease_term_months ?? 36
  const buyoutPct = params.buyout_percent ?? 0
  const perVehicleCalcs = calculationData?.calculations_per_vehicle || []
  const items: EmailLineItem[] = []

  for (const item of selectedItems) {
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
    const priceLine = `Цена за 1 ТС: ${formatPrice(pricePerUnit)}`

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
    const discountLines: string[] = []
    if (discountSummary) {
      discountLines.push(
        `Выгода: −${formatPrice(discountSummary.amount)} (${discountSummary.percent}%)`,
        `Цена с выгодой: ${formatPrice(discountSummary.discountedPrice)}`,
      )
    }

    const calcRows = calcResult
      ? [
          { label: 'Ежемесячный платёж', value: formatPrice(calcResult.monthlyPayment) },
          { label: 'Первоначальный взнос', value: `${downPercent}%` },
          { label: 'Сумма договора', value: formatPrice(calcResult.totalCost) },
        ]
      : [{ label: 'Статус', value: 'Нет данных расчета' }]
    const details: { label: string; value: string }[] = []
    if (item.mark_name) details.push({ label: 'Марка', value: String(item.mark_name) })
    if (item.model_name) details.push({ label: 'Модель', value: String(item.model_name) })
    if (item.group_name) details.push({ label: 'Комплектация', value: String(item.group_name) })
    if (item.vin) details.push({ label: 'VIN', value: String(item.vin) })
    if (item.year) details.push({ label: 'Год', value: String(item.year) })
    if (item.color) details.push({ label: 'Цвет', value: String(item.color) })
    details.push({ label: item.ref.type === 'vehicle' ? 'Цена в каталоге' : 'Цена с выгодой', value: formatPrice(item.base_price || 0) })
    if (item.comment) details.push({ label: 'Комментарий', value: String(item.comment) })

    const supportRow = (() => {
      if (!itemSupport) return null
      const dp = Number(itemSupport.down_payment_support) || 0
      const vd = Number(itemSupport.vehicle_discount_support) || 0
      const in_ = Number(itemSupport.interest_support) || 0
      if (dp === 0 && vd === 0 && in_ === 0) return null
      const parts: string[] = []
      if (dp > 0) parts.push(`Поддержка первого взноса: ${formatPrice(dp)}`)
      if (vd > 0) parts.push(`Поддержка на ТС: ${formatPrice(vd)}`)
      if (in_ > 0) parts.push(`Поддержка процентов: ${formatPrice(in_)}`)
      return parts.join('; ')
    })()

    items.push({ vehicleTitle, quantity, quantityLine, priceLine, discountLines, termMonths, buyoutPct, calcRows, supportRow, details })
  }

  const appliedDiscountsTotal = selectedItems
    .filter(line => line.ref.type === 'special_equipment')
    .reduce((sum, line) => {
      const s = getCommerceLineDiscountSummary(line)
      return s ? sum + s.amount * commerceCartBillableQuantity(line) : sum
    }, 0)

  return {
    downPercent,
    termMonths,
    buyoutPct,
    items,
    totalAmount,
    appliedDiscountsTotal,
    overallCalc: calculationData?.calculation ?? null,
    overallSupport: calculationData?.support ?? null,
  }
}

export function buildText(data: EmailData): string {
  const lines = ['Расчет лизинга — выбранные ТС и общий расчет', '', '']
  for (let i = 0; i < data.items.length; i++) {
    const it = data.items[i]
    if (i > 0) lines.push('---', '')
    lines.push(it.vehicleTitle, '')
    lines.push(it.priceLine)
    for (const dLine of it.discountLines) {
      lines.push(dLine)
    }
    lines.push(it.quantityLine)
    lines.push(`Срок договора: ${it.termMonths} мес.`)
    lines.push(`Выкупная стоимость: ${it.buyoutPct}%`, '')
    for (const row of it.calcRows) lines.push(`${row.label}: ${row.value}`)
    if (it.supportRow) lines.push(`Учтено в расчёте: ${it.supportRow}`, '')
    lines.push('Подробные характеристики:')
    for (const row of it.details) lines.push(`${row.label}: ${row.value}`)
    lines.push('')
  }
  lines.push('Общий расчет (все выбранные ТС)', '')
  lines.push(`Стоимость имущества: ${formatPrice(data.totalAmount)}`)
  if (data.appliedDiscountsTotal > 0) {
    lines.push(`Выгода: −${formatPrice(data.appliedDiscountsTotal)}`)
  }
  lines.push(`Срок договора: ${data.termMonths} мес.`)
  lines.push(`Первоначальный взнос: ${data.downPercent}%`)
  lines.push(`Выкупная стоимость: ${data.buyoutPct}%`, '')
  if (data.overallCalc) {
    lines.push(`Ежемесячный платёж: ${formatPrice(data.overallCalc.monthlyPayment)}`)
    lines.push(`Сумма договора: ${formatPrice(data.overallCalc.totalCost)}`)
  } else {
    lines.push('Выполните расчет в калькуляторе на странице корзины для отображения общего ежемесячного платежа.')
  }
  if (data.overallSupport) {
    const dp = Number(data.overallSupport.down_payment_support) || 0
    const vd = Number(data.overallSupport.vehicle_discount_support) || 0
    const in_ = Number(data.overallSupport.interest_support) || 0
    if (dp > 0 || vd > 0 || in_ > 0) {
      const parts: string[] = []
      if (dp > 0) parts.push(`Поддержка первого взноса: ${formatPrice(dp)}`)
      if (vd > 0) parts.push(`Поддержка на ТС: ${formatPrice(vd)}`)
      if (in_ > 0) parts.push(`Поддержка процентов: ${formatPrice(in_)}`)
      lines.push('', `Учтено в расчёте: ${parts.join('; ')}`)
    }
  }
  return lines.join('\n')
}

export function buildHtml(data: EmailData): string {
  const itemBlocks = data.items
    .map((it) => {
      const calcRows = it.calcRows
        .map(
          (row) => `
        <tr>
          <td style="padding: 6px 0; color: #4b5563;">${escapeHtml(row.label)}</td>
          <td style="padding: 6px 0; color: #111827; font-weight: 600; text-align: right;">${escapeHtml(row.value)}</td>
        </tr>`,
        )
        .join('')
      const detailsRows = it.details
        .map(
          (row) => `
        <tr>
          <td style="padding: 6px 0; color: #4b5563;">${escapeHtml(row.label)}</td>
          <td style="padding: 6px 0; color: #111827; font-weight: 600; text-align: right;">${escapeHtml(row.value)}</td>
        </tr>`,
        )
        .join('')
      const supportBlock = it.supportRow
        ? `<div style="font-size: 12px; color: #059669; margin: 6px 0;">Учтено в расчёте: ${escapeHtml(it.supportRow)}</div>`
        : ''
      const discountHtml = it.discountLines
        .map(
          (dLine) => `
        <div style="font-size: 14px; color: #059669; font-weight: 500; margin-bottom: 4px;">${escapeHtml(dLine)}</div>`,
        )
        .join('')

      return `
      <div style="margin: 0 0 20px 0; padding: 14px; border: 1px solid #e5e7eb; border-radius: 10px;">
        <div style="font-size: 16px; font-weight: 600; color: #111827; margin-bottom: 8px;">${escapeHtml(it.vehicleTitle)}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">${escapeHtml(it.priceLine)}</div>
        ${discountHtml}
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">${escapeHtml(it.quantityLine)}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">Срок договора: ${it.termMonths} мес.</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 10px;">Выкупная стоимость: ${it.buyoutPct}%</div>
        <table style="width: 100%; border-collapse: collapse;">${calcRows}</table>
        ${supportBlock}
        <div style="margin-top: 10px; font-size: 13px; font-weight: 600;">Подробные характеристики</div>
        <table style="width: 100%; border-collapse: collapse;">${detailsRows}</table>
      </div>`
    })
    .join('')

  let overallBlock = `
    <div style="margin-top: 16px; padding: 14px; border: 1px solid #d1d5db; border-radius: 10px; background: #f9fafb;">
      <div style="font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 8px;">Общий расчет (все выбранные ТС)</div>
      <div style="font-size: 14px; color: #374151;">Стоимость имущества: ${escapeHtml(formatPrice(data.totalAmount))}</div>`
  if (data.appliedDiscountsTotal > 0) {
    overallBlock += `
      <div style="font-size: 14px; color: #059669; font-weight: 600;">Выгода: −${escapeHtml(formatPrice(data.appliedDiscountsTotal))}</div>`
  }
  overallBlock += `
      <div style="font-size: 14px; color: #374151;">Срок договора: ${data.termMonths} мес.</div>
      <div style="font-size: 14px; color: #374151;">Первоначальный взнос: ${data.downPercent}%</div>
      <div style="font-size: 14px; color: #374151; margin-bottom: 8px;">Выкупная стоимость: ${data.buyoutPct}%</div>`
  if (data.overallCalc) {
    overallBlock += `
      <div style="font-size: 14px; font-weight: 600;">Ежемесячный платёж: ${escapeHtml(formatPrice(data.overallCalc.monthlyPayment))}</div>
      <div style="font-size: 14px; font-weight: 600;">Сумма договора: ${escapeHtml(formatPrice(data.overallCalc.totalCost))}</div>`
  } else {
    overallBlock += `<div style="font-size: 14px; color: #6b7280;">Выполните расчет в калькуляторе на странице корзины для отображения общего платежа.</div>`
  }
  if (data.overallSupport) {
    const dp = Number(data.overallSupport.down_payment_support) || 0
    const vd = Number(data.overallSupport.vehicle_discount_support) || 0
    const in_ = Number(data.overallSupport.interest_support) || 0
    if (dp > 0 || vd > 0 || in_ > 0) {
      const parts: string[] = []
      if (dp > 0) parts.push(`Поддержка первого взноса: ${formatPrice(dp)}`)
      if (vd > 0) parts.push(`Поддержка на ТС: ${formatPrice(vd)}`)
      if (in_ > 0) parts.push(`Поддержка процентов: ${formatPrice(in_)}`)
      overallBlock += `<div style="font-size: 12px; color: #059669; margin-top: 6px;">Учтено в расчёте: ${escapeHtml(parts.join('; '))}</div>`
    }
  }
  overallBlock += '</div>'

  return `
    <div style="font-family: Arial, sans-serif; max-width: 680px; margin: 0 auto; color: #111827; background: #ffffff;">
      <div style="padding: 18px; border: 1px solid #e5e7eb; border-radius: 12px;">
        <h2 style="margin: 0 0 14px 0; font-size: 20px; text-align: center;">Расчет лизинга — выбранные ТС и общий расчет</h2>
        ${itemBlocks}
        ${overallBlock}
      </div>
    </div>`
}

export const useCartEmail = (config: RuntimeConfig) => {
  const sendingCartEmail = ref(false)

  const sendCartByEmail = async (
    email: string,
    selectedItems: readonly CommerceCartLine[],
    calculationData: CartCalculationData | null,
    params: CartEmailParams,
    totalAmount: number,
    toast: any,
    onSuccess?: () => void,
  ) => {
    if (!email || !selectedItems.length) return
    sendingCartEmail.value = true
    try {
      const data = buildEmailData(selectedItems, calculationData, params, totalAmount)
      const text = buildText(data)
      const html = buildHtml(data)
      await $fetch('/api/v1/calculator/send-calculation-email', {
        method: 'POST',
        body: { to: email, subject: 'Расчет лизинга — корзина', text, html },
        baseURL: config.public?.apiBase,
        credentials: 'include',
      })
      onSuccess?.()
      toast?.success?.('Расчет отправлен на указанный email')
    } catch (e: any) {
      console.error('Send cart email error:', e)
      toast?.error?.(e?.data?.error || 'Не удалось отправить письмо')
    } finally {
      sendingCartEmail.value = false
    }
  }

  return { sendingCartEmail, sendCartByEmail }
}
