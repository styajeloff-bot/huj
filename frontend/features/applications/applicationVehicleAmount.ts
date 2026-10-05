const historicalStatuses = new Set(['removed', 'replaced', 'rejected'])

interface VehicleAmountLine {
  final_price?: number | string | null
  unit_price?: number | string | null
  catalog_price?: number | string | null
  catalog_price_from?: number | string | null
  price?: number | string | null
  total_price?: number | string | null
  quantity?: number | string | null
  status?: string | null
}

interface VehicleAmountItem extends VehicleAmountLine {
  type?: string
}

interface VehicleAmountApplication {
  items?: VehicleAmountItem[]
  vehicles?: VehicleAmountLine[]
}

const numericMoney = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined || value === '') return null
  const amount = Number(value)
  return Number.isFinite(amount) ? amount : null
}

const lineQuantity = (value: number | string | null | undefined): number => {
  const quantity = Number(value)
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1
}

const isLiveLine = (line: VehicleAmountLine): boolean => (
  !line.status || !historicalStatuses.has(line.status)
)

const completeVehicleLinesAmount = (lines: VehicleAmountLine[]): number | null => {
  if (lines.length === 0) return null

  let total = 0
  for (const line of lines) {
    const price = numericMoney(line.final_price)
      ?? numericMoney(line.unit_price)
      ?? numericMoney(line.catalog_price)
      ?? numericMoney(line.catalog_price_from)
      ?? numericMoney(line.price)
    if (price !== null) {
      const quantity = lineQuantity(line.quantity)
      total += price * quantity
    } else {
      const totalPrice = numericMoney(line.total_price)
      if (totalPrice !== null) {
        total += totalPrice
      } else {
        return null
      }
    }
  }
  return total
}

export const calculateApplicationVehicleAmount = (
  application: VehicleAmountApplication,
): number => {
  const normalizedVehicleLines = (application.items ?? [])
    .filter(item => !item.type || item.type === 'vehicle' || item.type === 'special_equipment')
    .filter(isLiveLine)
  const normalizedAmount = completeVehicleLinesAmount(normalizedVehicleLines)
  if (normalizedAmount !== null) return normalizedAmount

  const legacyVehicleLines = (application.vehicles ?? []).filter(isLiveLine)
  const legacyAmount = completeVehicleLinesAmount(legacyVehicleLines)
  if (legacyAmount !== null) return legacyAmount

  return 0
}
