import { computed, ref, watch } from 'vue'
import type { UUID } from '~/types/ids'
/** Workflow confirmation does not mean every requested vehicle has been allocated. */
export function vehicleNeedsFulfillment(vehicle: {
  fulfillment_version?: number
  confirmed_quantity?: number | null
  quantity?: number
  allocated_vehicle_ids?: UUID[]
  status?: string | null
  car_status?: string | null
}): boolean {
  const status = vehicle.status || vehicle.car_status || 'active'
  if (status !== 'active' && status !== 'confirmed') return false
  const allocated = vehicle.allocated_vehicle_ids?.length ?? 0
  if ((vehicle.fulfillment_version ?? 0) > 0) {
    return allocated < (vehicle.confirmed_quantity ?? vehicle.quantity ?? 1)
  }
  return vehicle.fulfillment_version === 0 && vehicle.confirmed_quantity == null && allocated === 0
}
export interface FulfillmentAllocation {
  id: UUID; vehicle_id: UUID; vin: string | null; unit_price: number; reserved_until: string | null; released_at: string | null; completed_at?: string | null; reservation_fixed?: boolean
}
export interface VehicleFulfillment {
  application_vehicle_id: UUID
  requested_quantity: number | null; confirmed_quantity: number | null; quantity: number; version: number
  editable: boolean; reservation_fixed?: boolean; allocated_quantity: number; remaining_quantity: number
  allocations: FulfillmentAllocation[]
  available_vehicles: Array<{ id: UUID; vin: string | null; base_price: number; discount_price?: number | null; color?: string | null; year?: number | null; status: string }>
  history: Array<{ id: UUID; actor_id: UUID; created_at: string; comment?: string | null }>
  calculation: Record<string, unknown>
  application_totals: Record<string, number | null>
}
export interface FulfillmentUpdate {
  version: number; confirmed_quantity: number; vehicle_ids: UUID[]; reserve_expires_at: string; comment?: string
}
type Request = <T>(path: string, options?: { method?: 'GET' | 'POST' | 'PATCH'; body?: FulfillmentUpdate }) => Promise<T>
export function useVehicleFulfillment(id: () => UUID, request: Request) {
  const current = ref<VehicleFulfillment | null>(null)
  const preview = ref<VehicleFulfillment | null>(null)
  const quantity = ref(1)
  const selected = ref<UUID[]>([])
  const expires = ref('')
  const comment = ref('')
  const pending = ref(false)
  const error = ref('')
  let revision = 0
  const active = computed(() => current.value?.allocations.filter(item => !item.released_at) ?? [])
  const replacing = computed(() => active.value.some(item => !selected.value.includes(item.vehicle_id)))
  const remaining = computed(() => quantity.value - selected.value.length)
  const valid = computed(() => Number.isSafeInteger(quantity.value) && quantity.value > 0 && remaining.value >= 0
    && !!expires.value && (!replacing.value || !!comment.value.trim()))
  watch([quantity, selected, expires, comment], () => { preview.value = null; revision++ }, { deep: true, flush: 'sync' })
  const path = () => `/api/v1/application-vehicles/${id()}/fulfillment`
  const body = (): FulfillmentUpdate => ({ version: current.value!.version, confirmed_quantity: quantity.value,
    vehicle_ids: [...selected.value], reserve_expires_at: expires.value, comment: comment.value.trim() || undefined })
  const message = (cause: unknown) => {
    const failure = cause as { data?: { detail?: unknown } }
    return typeof failure.data?.detail === 'string' ? failure.data.detail : 'Не удалось выполнить операцию. Обновите данные и повторите попытку.'
  }
  const adopt = (result: VehicleFulfillment) => {
    current.value = result
    quantity.value = result.confirmed_quantity ?? result.quantity
    selected.value = result.allocations.filter(item => !item.released_at).map(item => item.vehicle_id)
    const reserved = result.allocations.find(item => !item.released_at)?.reserved_until
    expires.value = reserved?.slice(0, 10) ?? new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10)
    comment.value = ''; preview.value = null
  }
  const load = async () => {
    pending.value = true; error.value = ''
    try { adopt(await request<VehicleFulfillment>(path())) }
    catch (cause) { error.value = message(cause) }
    finally { pending.value = false }
  }
  const calculate = async () => {
    if (!valid.value || !current.value?.editable || pending.value) return
    pending.value = true; error.value = ''
    const stamp = revision
    try {
      const result = await request<VehicleFulfillment>(`${path()}/preview`, { method: 'POST', body: body() })
      if (stamp === revision) preview.value = result
    } catch (cause) { error.value = message(cause) }
    finally { pending.value = false }
  }
  const save = async () => {
    if (!preview.value || !valid.value || !current.value?.editable || pending.value) return false
    pending.value = true; error.value = ''
    try { adopt(await request<VehicleFulfillment>(path(), { method: 'PATCH', body: body() })); return true }
    catch (cause) { error.value = message(cause); preview.value = null; return false }
    finally { pending.value = false }
  }
  return { current, preview, quantity, selected, expires, comment, pending, error, active, replacing, remaining, valid, load, calculate, save }
}
