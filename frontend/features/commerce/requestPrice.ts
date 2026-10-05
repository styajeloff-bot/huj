export type CommerceCatalogPrice = string | number | null

export interface CommerceRequestPricingView {
  price: CommerceCatalogPrice
  price_from?: CommerceCatalogPrice
  price_on_request?: boolean
}

const normalizeDisplaySpaces = (value: string): string =>
  value.replace(/[\u00a0\u202f]/g, ' ')

export const formatCommerceCatalogPrice = (
  value: Exclude<CommerceCatalogPrice, null>,
): string => {
  const amount = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(amount)) return 'Цена по запросу'
  const formatted = new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(amount)
  return `${normalizeDisplaySpaces(formatted)} ₽`
}

export const formatCommerceRequestPrice = (
  pricing: CommerceRequestPricingView,
): string => {
  if (pricing.price_on_request === true
    && pricing.price_from !== null
    && pricing.price_from !== undefined) {
    const formatted = formatCommerceCatalogPrice(pricing.price_from)
    return formatted === 'Цена по запросу' ? formatted : `от ${formatted}`
  }
  if (pricing.price === null || pricing.price === undefined) return 'Цена по запросу'
  return formatCommerceCatalogPrice(pricing.price)
}
