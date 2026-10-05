export interface VehicleStockStatus {
  status?: string | null
  purchase_pending?: boolean
  sale_completed?: boolean
  reserved_until?: string | null
}
/** Warehouse sold can precede payment; only explicit completion means bought. */
export function vehicleStockStatusLabel(vehicle: VehicleStockStatus): string {
  if (vehicle.status === 'sold') {
    if (vehicle.purchase_pending) return 'Ожидает оплаты'
    if (vehicle.sale_completed) return 'Куплена'
    return 'Продана (статус склада)'
  }
  return ({ available: 'На складе', reserved: 'Забронирована', maintenance: 'На обслуживании' } as Record<string, string>)[vehicle.status ?? ''] ?? vehicle.status ?? 'Не указан'
}
