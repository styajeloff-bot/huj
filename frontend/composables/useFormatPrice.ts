export const useFormatPrice = () => {
  const normalizeNumber = (value: number | string | null | undefined): number => {
    const numValue = Number(value)
    return Number.isFinite(numValue) ? numValue : 0
  }

  const formatPrice = (price: number | string | null | undefined): string => {
    const numPrice = normalizeNumber(price)
    return `${formatNumber(Math.round(numPrice))} ₽`
  }

  const formatMoneyCompact = (price: number | string | null | undefined): string => {
    const numPrice = Math.round(normalizeNumber(price))
    if (Math.abs(numPrice) < 1_000_000) {
      return formatPrice(numPrice)
    }

    const compactMillions = Math.round(numPrice / 1_000_000)
    return `${formatNumber(compactMillions)} млн ₽`
  }

  const formatNumber = (num: number | string | null | undefined): string => {
    const numValue = normalizeNumber(num)
    return new Intl.NumberFormat('ru-RU').format(numValue)
  }

  // ТЗ №18 п.2.2: денежный формат — пробел-разделитель разрядов, 2 знака после запятой
  const formatMoneyDecimal = (price: number | string | null | undefined): string => {
    if (price === null || price === undefined || price === '') return '—'
    const numPrice = normalizeNumber(price)
    return new Intl.NumberFormat('ru-RU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numPrice)
  }

  return {
    formatMoneyFull: formatPrice,
    formatPrice,
    formatMoneyCompact,
    formatNumber,
    formatMoneyDecimal
  }
}
