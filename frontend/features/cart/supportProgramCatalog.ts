import type { UUID } from '~/types/ids'
import {
  normalizeSupportPrograms,
  type SupportBadgeProgram,
} from '~/types/support'

export const selectedSupportProgramsForVehicle = (
  vehicleId: UUID,
  selectedIds: readonly UUID[],
  ...sources: ReadonlyArray<readonly SupportBadgeProgram[]>
): SupportBadgeProgram[] => {
  const selected = new Set(selectedIds)
  return normalizeSupportPrograms(sources.flat()).filter(program => (
    selected.has(program.id)
    && (program.vehicle_id == null || program.vehicle_id === vehicleId)
  ))
}
