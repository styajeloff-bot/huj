type CompensationTemplateLike = {
  payer: string
  recipient: string
  calculation_base: string
  value_type: string
  value: number
}

export interface SupportPricingLike {
  support_type?: string | null
  support_params?: object | null
  compensation_templates?: readonly CompensationTemplateLike[] | null
}

const formatNumber = (value: unknown): string => {
  const numeric = Number(value)
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat('ru-RU').format(numeric)
    : String(value)
}

const payerLabel = (value: string) => ({
  distributor: 'Дистрибьютор',
  dealer: 'Дилер',
  carcraft: 'CarCraft',
  minpromtorg: 'Минпромторг',
  client: 'Клиент',
} as Record<string, string>)[value] || value

const recipientLabel = (value: string) => ({
  leasing_company: 'ЛК',
  dealer: 'Дилер',
  carcraft: 'CarCraft',
  client: 'Клиент',
} as Record<string, string>)[value] || value

const compensationBaseLabel = (value: string) => ({
  base_price: 'РРЦ',
  special_price: 'Специальной цены',
  dealer_cost: 'Себестоимости',
  application_price: 'Цены в заявке',
  down_payment: 'Первого взноса',
  support_amount: 'Суммы поддержки',
} as Record<string, string>)[value] || value

export const formatSupportAmount = (value: unknown): string => `${formatNumber(value)} ₽`

export const formatSupportProgramPricing = (program: SupportPricingLike): string => {
  const params = (program.support_params || {}) as Record<string, unknown>
  const parts: string[] = []

  if (params.value_type === 'percent' && params.value != null) parts.push(`${params.value}%`)
  if (params.value_type === 'amount' && params.value != null) parts.push(formatSupportAmount(params.value))
  if (params.min_amount) parts.push(`мин. ${formatSupportAmount(params.min_amount)}`)
  if (params.max_amount) parts.push(`макс. ${formatSupportAmount(params.max_amount)}`)
  if (params.min_percent) parts.push(`мин. ${params.min_percent}%`)
  if (params.max_percent) parts.push(`макс. ${params.max_percent}%`)
  if (program.support_type === 'leasing_interest_compensation') {
    if (params.compensation_period_months) parts.push(`период ${params.compensation_period_months} мес.`)
    if (params.start_month) parts.push(`старт с ${params.start_month} мес.`)
  }

  for (const template of program.compensation_templates || []) {
    const value = template.value_type === 'percent'
      ? `${template.value}% от ${compensationBaseLabel(template.calculation_base).toLowerCase()}`
      : formatSupportAmount(template.value)
    parts.push(`${payerLabel(template.payer)} → ${recipientLabel(template.recipient)}: ${value}`)
  }

  return parts.join(', ') || 'Параметры не заданы'
}
