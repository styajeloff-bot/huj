export type SupportPaymentAmountsInput = {
  unitPrice: number
  quantity?: number
  downPaymentPercent: number
  vehicleDiscountSupport?: number
  downPaymentSupport?: number
  interestSupport?: number
}

export type SupportPaymentAmounts = {
  baseTotal: number
  effectiveTotal: number
  contractDownPayment: number
  clientDownPayment: number
  contractDownPaymentPercent: number
  clientDownPaymentPercent: number
  advanceSupportTotal: number
}

const nonNegative = (value: number | undefined): number => {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Number(value))
}

const percentOf = (amount: number, base: number, fallback: number): number => {
  if (base <= 0) return fallback
  return Math.round((amount / base) * 10000) / 100
}

export type AdvanceDifference = {
  amountDelta: number
  percentDelta: number
}

export type SupportPercentDifference = {
  text: string
  diffClass: string
}

export type SupportComparisonInput = {
  vehicle_discount_support?: number
  dealer_commission_support?: number
  down_payment_support?: number
  interest_support?: number
}

export type SupportComparisonRow = {
  key: 'vehicle_discount' | 'dealer_commission' | 'down_payment' | 'interest'
  label: string
  amount: number
}

const roundedPercentDelta = (value: number): number => (
  Math.round(value * 100) / 100
)

export function calculateAdvanceDifference(
  withoutAmount: number,
  withAmount: number,
  withoutPercent: number,
  withPercent: number,
): AdvanceDifference {
  return {
    amountDelta: Math.round(withAmount - withoutAmount),
    percentDelta: roundedPercentDelta(withPercent - withoutPercent),
  }
}

export function calculateDownPaymentSupportPercent(
  downPaymentSupport: number,
  totalAmount: number,
): number {
  const support = nonNegative(downPaymentSupport)
  const total = nonNegative(totalAmount)
  if (support <= 0 || total <= 0) return 0
  return Math.min(49, Math.round((support / total) * 10_000) / 100)
}

export function formatSupportPercentDifference(
  delta: number,
): SupportPercentDifference {
  const magnitude = Math.round(Math.abs(delta) * 100) / 100
  if (magnitude === 0) {
    return { text: '—', diffClass: 'text-gray-800' }
  }
  return {
    text: `−${magnitude}%`,
    diffClass: 'text-green-600',
  }
}

export function supportComparisonRows(
  breakdown: SupportComparisonInput,
): SupportComparisonRow[] {
  const totalVehicleSupport = Math.round(
    nonNegative(breakdown.vehicle_discount_support),
  )
  const dealerCommission = Math.min(
    totalVehicleSupport,
    Math.round(nonNegative(breakdown.dealer_commission_support)),
  )
  const directVehicleSupport = totalVehicleSupport - dealerCommission
  const downPaymentSupport = Math.round(
    nonNegative(breakdown.down_payment_support),
  )
  const interestSupport = Math.round(nonNegative(breakdown.interest_support))

  return [
    ...(directVehicleSupport > 0
      ? [{
          key: 'vehicle_discount' as const,
          label: 'Поддержка на ТС',
          amount: directVehicleSupport,
        }]
      : []),
    ...(dealerCommission > 0
      ? [{
          key: 'dealer_commission' as const,
          label: 'Комиссия дилеру',
          amount: dealerCommission,
        }]
      : []),
    ...(downPaymentSupport > 0
      ? [{
          key: 'down_payment' as const,
          label: 'Поддержка первоначального взноса',
          amount: downPaymentSupport,
        }]
      : []),
    ...(interestSupport > 0
      ? [{ key: 'interest' as const, label: 'Поддержка процентов', amount: interestSupport }]
      : []),
  ]
}

export function calculateSupportPaymentAmounts(
  input: SupportPaymentAmountsInput,
): SupportPaymentAmounts {
  const quantity = Math.max(1, Math.trunc(nonNegative(input.quantity)))
  const unitPrice = nonNegative(input.unitPrice)
  const downPaymentPercent = nonNegative(input.downPaymentPercent)
  const baseTotal = Math.round(unitPrice * quantity)
  const vehicleSupport = Math.round(
    nonNegative(input.vehicleDiscountSupport) * quantity,
  )
  const downPaymentSupport = Math.round(
    nonNegative(input.downPaymentSupport) * quantity,
  )
  const interestSupport = Math.round(
    nonNegative(input.interestSupport) * quantity,
  )
  const effectiveTotal = Math.max(0, baseTotal - vehicleSupport)
  const contractDownPayment = Math.round(
    baseTotal * (downPaymentPercent / 100),
  )
  const advanceSupportTotal = downPaymentSupport + interestSupport
  const clientDownPayment = Math.max(
    0,
    contractDownPayment - advanceSupportTotal,
  )

  return {
    baseTotal,
    effectiveTotal,
    contractDownPayment,
    clientDownPayment,
    contractDownPaymentPercent: percentOf(
      contractDownPayment,
      effectiveTotal,
      downPaymentPercent,
    ),
    clientDownPaymentPercent: percentOf(
      clientDownPayment,
      effectiveTotal,
      downPaymentPercent,
    ),
    advanceSupportTotal,
  }
}
