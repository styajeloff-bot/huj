import { useAuthStore } from '~/features/auth/store/auth'
import {
  supportCandidateCompatibilityError,
  type SupportBadgeProgram,
} from '~/types/support'
import { isUuid, type UUID } from '~/types/ids'

const BASE_STORAGE_KEY = 'cart-support'

type VehicleSupportState = {
  selected_support_ids: UUID[]
  excluded_support_ids: UUID[]
}

type StorageState = Record<UUID, VehicleSupportState>

function scopedKey(): string {
  if (typeof window === 'undefined') return `${BASE_STORAGE_KEY}:guest`
  try {
    const auth = useAuthStore()
    const id = (auth.user as { id?: UUID } | null)?.id
    if (id !== undefined && id !== null) return `${BASE_STORAGE_KEY}:u${id}`
  } catch {
    // Pinia not available during SSR pre-hydration — fall back to guest.
  }
  return `${BASE_STORAGE_KEY}:guest`
}

function loadState(): StorageState {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(scopedKey())
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}
    const out: StorageState = {}
    let needsPersist = false
    for (const [key, rawVehicle] of Object.entries(parsed)) {
      if (!rawVehicle || typeof rawVehicle !== 'object') continue
      const normalized = normalizeVehicleSupportState(rawVehicle as Partial<VehicleSupportState>)
      out[key] = normalized
      if (!vehicleSupportStateEqual(normalized, rawVehicle as VehicleSupportState)) {
        needsPersist = true
      }
    }
    if (needsPersist) {
      saveState(out)
    }
    return out
  } catch (e) {
    console.error('[useCartSupportSelection] Failed to load state:', e)
  }
  return {}
}

function saveState(state: StorageState) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(scopedKey(), JSON.stringify(state))
  } catch (e) {
    console.error('[useCartSupportSelection] Failed to save state:', e)
  }
}

const sortIds = (ids: UUID[]): UUID[] => [...ids].sort((a, b) => a.localeCompare(b))

/** Дедупликация id программ: в localStorage могли остаться повторы — иначе в модалке рисуются две карточки на одну программу. */
function normalizeVehicleSupportState(sel: Partial<VehicleSupportState>): VehicleSupportState {
  const selectedUnique = [...new Set(
    (sel.selected_support_ids || [])
      .filter(isUuid)
  )].sort((a, b) => a.localeCompare(b))

  const excludedRaw = [...new Set(
    (sel.excluded_support_ids || [])
      .filter(isUuid)
  )].sort((a, b) => a.localeCompare(b))
  const selectedSet = new Set(selectedUnique)
  const excluded = excludedRaw.filter((id) => !selectedSet.has(id))
  return {
    selected_support_ids: selectedUnique,
    excluded_support_ids: excluded
  }
}

function vehicleSupportStateEqual(a: VehicleSupportState, b: VehicleSupportState): boolean {
  const sig = (x: UUID[]) => sortIds(x).join(',')
  return sig(a.selected_support_ids) === sig(b.selected_support_ids)
    && sig(a.excluded_support_ids) === sig(b.excluded_support_ids)
}

// Module-level singleton — all instances share the same reactive state,
// so changes made in the modal are immediately visible to the calculator.
// The ref is re-hydrated whenever the active user changes (login switch,
// logout) so account A's selections never leak into account B's session.
const state = ref<StorageState>(loadState())
let lastScopeKey = scopedKey()

function ensureCurrentUser() {
  if (typeof window === 'undefined') return
  const k = scopedKey()
  if (k !== lastScopeKey) {
    lastScopeKey = k
    state.value = loadState()
  }
}

export function useCartSupportSelection() {
  ensureCurrentUser()

  const persist = () => {
    ensureCurrentUser()
    saveState(state.value)
  }

  const getKey = (vehicleId: UUID) => vehicleId

  const getSelectionForVehicle = (vehicleId: UUID): VehicleSupportState => {
    const key = getKey(vehicleId)
    if (!state.value[key]) {
      state.value[key] = {
        selected_support_ids: [],
        excluded_support_ids: []
      }
    } else {
      const normalized = normalizeVehicleSupportState(state.value[key])
      if (!vehicleSupportStateEqual(normalized, state.value[key])) {
        state.value[key] = normalized
        persist()
      }
    }
    return state.value[key]
  }

  const compatibilityError = (
    vehicleId: UUID,
    programId: UUID,
    availablePrograms: readonly SupportBadgeProgram[],
  ): string | null => {
    const candidate = availablePrograms.find(program => program.id === programId)
    if (!candidate) return 'Программа больше не доступна для этого ТС'
    const selectedIds = new Set(getSelectionForVehicle(vehicleId).selected_support_ids)
    const selectedPrograms = availablePrograms.filter(program => selectedIds.has(program.id))
    return supportCandidateCompatibilityError(candidate, selectedPrograms)
  }

  /**
   * Синхронизация с актуальным списком программ с сервера (support-status / калькулятор):
   * - null/undefined означает, что список временно неизвестен, поэтому выбор не меняем;
   * - сначала убираем из selected/excluded всё, чего нет в availableProgramIds;
   * - если список доступных пуст — только очистка устаревших id;
   * - иначе: если нет записи по ТС — все available попадают в selected;
   * - иначе: новые id, которых нет ни в selected, ни в excluded, добавляем в selected.
   */
  const ensureProgramsApplied = (vehicleId: UUID, availableProgramIds: UUID[] | null | undefined) => {
    if (availableProgramIds == null) return

    const normalized = Array.from(
      new Set(
        availableProgramIds
          .filter(isUuid)
      )
    ).sort((a, b) => a.localeCompare(b))
    const eligible = new Set(normalized)

    const sel = getSelectionForVehicle(vehicleId)
    const selected = new Set(sel.selected_support_ids || [])
    const excluded = new Set(sel.excluded_support_ids || [])

    let pruned = false
    for (const id of [...selected]) {
      if (!eligible.has(id)) {
        selected.delete(id)
        pruned = true
      }
    }
    for (const id of [...excluded]) {
      if (!eligible.has(id)) {
        excluded.delete(id)
        pruned = true
      }
    }
    if (pruned) {
      sel.selected_support_ids = sortIds(Array.from(selected))
      sel.excluded_support_ids = sortIds(Array.from(excluded))
      persist()
    }

    if (normalized.length === 0) return

    const selected2 = new Set(sel.selected_support_ids || [])
    const excluded2 = new Set(sel.excluded_support_ids || [])

    // если нет ни одного записанного id — по умолчанию одна программа (минимальный id из доступных)
    // TODO(multi-support): sel.selected_support_ids = [...normalized]
    if (selected2.size === 0 && excluded2.size === 0) {
      sel.selected_support_ids = normalized.length ? [normalized[0]] : []
      sel.excluded_support_ids = []
      persist()
      return
    }

    // Новые программы не применяем автоматически: один безопасный default уже выбран,
    // остальные пользователь добавляет явно после проверки совместимости.
    let changed = false
    for (const id of normalized) {
      if (!selected2.has(id) && !excluded2.has(id)) {
        excluded2.add(id)
        changed = true
      }
    }

    if (changed) {
      sel.selected_support_ids = sortIds(Array.from(selected2))
      sel.excluded_support_ids = sortIds(Array.from(excluded2))
      persist()
    }

  }

  /**
   * Включить/выключить конкретную программу для ТС.
   * enabled = true  => id в selected, убираем из excluded
   * enabled = false => id в excluded, убираем из selected
   */
  const setProgramEnabled = (
    vehicleId: UUID,
    programId: UUID,
    enabled: boolean,
    availablePrograms?: readonly SupportBadgeProgram[],
  ): string | null => {
    const id = programId
    const sel = getSelectionForVehicle(vehicleId)
    const selected = new Set(sel.selected_support_ids || [])
    const excluded = new Set(sel.excluded_support_ids || [])

    if (enabled) {
      const error = availablePrograms
        ? compatibilityError(vehicleId, programId, availablePrograms)
        : null
      if (error) return error
      selected.add(id)
      excluded.delete(id)
    } else {
      excluded.add(id)
      selected.delete(id)
    }

    sel.selected_support_ids = sortIds(Array.from(selected))
    sel.excluded_support_ids = sortIds(Array.from(excluded))
    persist()
    return null
  }

  const replacePrograms = (
    vehicleId: UUID,
    selectedIds: readonly UUID[],
    availablePrograms: readonly SupportBadgeProgram[],
  ): string | null => {
    const availableById = new Map(
      availablePrograms.map(program => [program.id, program]),
    )
    const normalized = sortIds(
      [...new Set(selectedIds.filter(isUuid))],
    )
    const selectedPrograms: SupportBadgeProgram[] = []
    for (const programId of normalized) {
      const program = availableById.get(programId)
      if (!program) return 'Программа больше не доступна для этого ТС'
      selectedPrograms.push(program)
    }
    for (const program of selectedPrograms) {
      const error = supportCandidateCompatibilityError(program, selectedPrograms)
      if (error) return error
    }

    const selected = new Set(normalized)
    const selection = getSelectionForVehicle(vehicleId)
    selection.selected_support_ids = normalized
    selection.excluded_support_ids = sortIds(
      availablePrograms
        .map(program => program.id)
        .filter(programId => !selected.has(programId)),
    )
    persist()
    return null
  }

  return {
    getSelectionForVehicle,
    ensureProgramsApplied,
    compatibilityError,
    setProgramEnabled,
    replacePrograms,
  }
}
