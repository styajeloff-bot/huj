import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'
import {
  createWarehousesAdminApi,
  type VehicleDeletionCheck,
  type VehicleDeletionReason,
  type WarehouseBulkDeleteResult,
  type WarehouseDeletionCheck
} from '~/features/admin/warehouses/api/warehousesAdminApi'

type RowCheck = { pending: boolean; error: string; data?: VehicleDeletionCheck }
type Operation = 'single' | 'unbind' | 'bulk'

export function useWarehouseVehicleDeletion(
  warehouseId: () => string,
  readOnly: () => boolean,
  refresh: () => Promise<void>,
  successMessage: Ref<string>
) {
  const auth = useAuthStore()
  const isAdmin = computed(() => auth.isCarCraftEmployee && !readOnly())
  const api = createWarehousesAdminApi(useRuntimeConfig())
  const checks = ref<Record<string, RowCheck>>({})
  const operation = ref<Operation | null>(null)
  const selected = ref<{ id: string; check: VehicleDeletionCheck } | null>(null)
  const confirmation = ref('')
  const reason = ref('')
  const pending = ref(false)
  const summaryPending = ref(false)
  const summary = ref<WarehouseDeletionCheck | null>(null)
  const dialogError = ref('')
  const conflictReasons = ref<VehicleDeletionReason[]>([])
  const result = ref<WarehouseBulkDeleteResult | null>(null)
  let generation = 0
  let dialogGeneration = 0

  const canConfirm = computed(() => {
    if (!isAdmin.value || pending.value || summaryPending.value) return false
    if (operation.value === 'unbind') return true
    if (operation.value === 'bulk') return !!summary.value && confirmation.value === 'УДАЛИТЬ'
    return operation.value === 'single' && selected.value?.check.can_delete === true && (
      confirmation.value === 'УДАЛИТЬ' || (!!selected.value.check.vin && confirmation.value === selected.value.check.vin)
    )
  })

  const checkVehicle = async (id: string, version = generation) => {
    if (!isAdmin.value) return
    checks.value[id] = { pending: true, error: '' }
    try {
      const data = await api.checkVehicleDeletion(id)
      if (version === generation && isAdmin.value) checks.value[id] = { pending: false, error: '', data }
    } catch {
      if (version === generation && isAdmin.value) checks.value[id] = { pending: false, error: 'Не удалось проверить возможность удаления.' }
    }
  }

  const checkRows = async (ids: string[]) => {
    const version = ++generation
    checks.value = {}
    if (!isAdmin.value) return
    await Promise.all(ids.map(id => checkVehicle(id, version)))
  }

  const loadSummary = async () => {
    if (!isAdmin.value || pending.value) return
    const version = ++dialogGeneration
    summaryPending.value = true
    summary.value = null
    dialogError.value = ''
    try {
      const data = await api.checkWarehouseDeletion(warehouseId())
      if (version === dialogGeneration && isAdmin.value) summary.value = data
    } catch {
      if (version === dialogGeneration) dialogError.value = 'Не удалось получить сводку по всему складу. Повторите проверку.'
    } finally {
      if (version === dialogGeneration) summaryPending.value = false
    }
  }

  const open = (mode: Operation, id?: string) => {
    if (!isAdmin.value || pending.value) return
    if (mode === 'single') {
      const check = id ? checks.value[id]?.data : undefined
      if (!id || !check?.can_delete || checks.value[id]?.pending || checks.value[id]?.error) return
      selected.value = { id, check }
    } else selected.value = null
    operation.value = mode
    confirmation.value = ''
    reason.value = ''
    dialogError.value = ''
    conflictReasons.value = []
    summary.value = null
    if (mode === 'bulk') void loadSummary()
  }

  const close = () => {
    if (pending.value) return
    ++dialogGeneration
    summaryPending.value = false
    operation.value = null
  }

  const submit = async () => {
    if (!canConfirm.value) return
    pending.value = true
    dialogError.value = ''
    conflictReasons.value = []
    successMessage.value = ''
    result.value = null
    try {
      if (operation.value === 'single' && selected.value) {
        await api.deleteVehicle(selected.value.id, {
          confirmation: confirmation.value,
          ...(reason.value.trim() ? { reason: reason.value.trim() } : {})
        })
        successMessage.value = `Автомобиль ${selected.value.check.vin || selected.value.check.name} удалён.`
      } else if (operation.value === 'unbind') {
        const data = await api.unbindAllVehicles(warehouseId())
        successMessage.value = `Отвязано автомобилей: ${data.unbound_count}.`
      } else if (operation.value === 'bulk') {
        result.value = await api.deleteWarehouseVehicles(warehouseId(), confirmation.value)
        successMessage.value = `Всего: ${result.value.requested_count}. Удалено: ${result.value.deleted_count}. Пропущено: ${result.value.skipped_count}.`
      }
    } catch (err: unknown) {
      const failure = err as {
        statusCode?: number; status?: number
        data?: { detail?: { blocking_reasons?: VehicleDeletionReason[] }; blocking_reasons?: VehicleDeletionReason[] }
      }
      if ((failure.statusCode ?? failure.status) === 409 && selected.value) {
        const reasons = failure.data?.detail?.blocking_reasons ?? failure.data?.blocking_reasons ?? []
        selected.value.check = { ...selected.value.check, can_delete: false, blocking_reasons: reasons }
        checks.value[selected.value.id] = { pending: false, error: '', data: selected.value.check }
        conflictReasons.value = reasons
        dialogError.value = 'Удаление отменено: появились блокирующие связи. Автомобиль сохранён.'
        if (!reasons.length) {
          await checkVehicle(selected.value.id)
          conflictReasons.value = checks.value[selected.value.id]?.data?.blocking_reasons ?? []
        }
      } else {
        dialogError.value = 'Не удалось выполнить операцию. Обновите проверку и повторите попытку.'
      }
      pending.value = false
      return
    }
    operation.value = null
    // Refresh failures must never present a committed deletion as a failed operation.
    try {
      await refresh()
    } finally {
      pending.value = false
    }
  }

  watch(isAdmin, allowed => {
    if (allowed) return
    ++generation
    ++dialogGeneration
    checks.value = {}
    operation.value = null
    selected.value = null
    summary.value = null
    result.value = null
    conflictReasons.value = []
  })
  onBeforeUnmount(() => { ++generation; ++dialogGeneration })

  return {
    isAdmin, checks, operation, selected, confirmation, reason, pending,
    summaryPending, summary, dialogError, conflictReasons, result, canConfirm,
    checkVehicle, checkRows, loadSummary, open, close, submit
  }
}
