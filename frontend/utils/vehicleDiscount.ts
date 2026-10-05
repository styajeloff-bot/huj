export interface VehicleDiscountSummary {
  basePrice: number
  discountedPrice: number
  amount: number
  percent: number
}

type VehiclePrice = number | null | undefined

export const getVehicleDiscountSummary = (
  basePrice: VehiclePrice,
  specialPrice: VehiclePrice,
): VehicleDiscountSummary | null => {
  if (
    typeof basePrice !== 'number'
    || typeof specialPrice !== 'number'
    || !Number.isFinite(basePrice)
    || !Number.isFinite(specialPrice)
    || basePrice <= 0
    || specialPrice <= 0
    || specialPrice >= basePrice
  ) {
    return null
  }

  const amount = basePrice - specialPrice

  return {
    basePrice,
    discountedPrice: specialPrice,
    amount,
    percent: Math.round((amount / basePrice) * 100),
  }
}

const finiteMoney = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export const getCommerceLineDiscountSummary = (
  line: import('~/features/commerce/cartProjection').CommerceCartLine,
): VehicleDiscountSummary | null => {
  if (line.price_on_request) return null
  const effective = finiteMoney(line.custom_price) ?? finiteMoney(line.base_price)
  const list = finiteMoney(line.list_price)
  if (
    effective === null
    || list === null
    || list <= 0
    || effective <= 0
    || effective >= list
  ) {
    return null
  }

  const amount = list - effective
  const percent = Math.round((amount / list) * 100)

  return {
    basePrice: list,
    discountedPrice: effective,
    amount,
    percent,
  }
}
