import type { UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'
import { createCarsApi } from '~/features/cars/api/carsApi'

export function useVehicleAvailability() {
  const config = useRuntimeConfig()
  const baseURL = config.public.apiBase
  const { apiPath } = useStorefront()
  const api = createCarsApi(config, apiPath)
  const normalizeVehicleIds = (vehicleIds: Array<UUID | null | undefined>): UUID[] =>
    vehicleIds.filter((id): id is UUID => typeof id === 'string' && id.length > 0)

  /**
   * Check availability status for multiple vehicle IDs.
   * Returns array of { vehicle_id, status } where status is 'available' | 'reserved' | 'sold'.
   * Vehicles not found in DB will be missing from the result.
   */
  async function checkAvailability(vehicleIds: Array<UUID | null | undefined>): Promise<{ vehicle_id: UUID; status: string }[]> {
    const ids = normalizeVehicleIds(vehicleIds)
    if (!ids.length) return []
    // GET /api/v1/cars/check-availability?vehicle_id=1&vehicle_id=2 (Phase 11 R9:
    // POST form removed, GET with repeated vehicle_id is canonical).
    const res = await api.checkAvailability(ids)
    return res.statuses
  }

  /**
   * Get vehicle IDs that the current user has active orders for.
   * Returns array of { vehicle_id, status, purchase_type }.
   */
  async function getMyReservedVehicles(): Promise<{ vehicle_id: UUID; status: string; purchase_type: string }[]> {
    const res = await $fetch<{ vehicles: { vehicle_id: UUID; status: string; purchase_type: string }[] }>('/api/v1/purchases/my-vehicle-ids', {
      baseURL,
      credentials: 'include'
    })
    return res.vehicles
  }

  /**
   * Get available count per vehicle_id (same complectation).
   * Returns array of { vehicle_id, complectation_id, available_count }.
   */
  async function getAvailableCounts(vehicleIds: Array<UUID | null | undefined>): Promise<{ vehicle_id: UUID; available_count: number }[]> {
    const ids = normalizeVehicleIds(vehicleIds)
    if (!ids.length) return []
    const res = await api.getAvailableCounts(ids)
    return res.counts
  }

  return { checkAvailability, getMyReservedVehicles, getAvailableCounts }
}
