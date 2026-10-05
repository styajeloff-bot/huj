import type { UUID } from './ids'

export type SupportType =
  | 'down_payment_compensation'
  | 'vehicle_discount_dealer_compensation'
  | 'vehicle_discount_dealer_invoice'
  | 'leasing_interest_compensation'
  | string

/**
 * Shared read model returned for an applicable or snapshotted support program.
 * Amounts and prices are authoritative server values; the frontend only formats them.
 */
export interface SupportBadgeProgram {
  id: UUID
  name: string
  support_type: SupportType
  support_params?: Record<string, unknown> | null
  comment?: string | null
  starts_at?: string | null
  ends_at?: string | null
  support_amount?: number | null
  base_price?: number | null
  display_price?: number | null
  is_compatible: boolean
  compatible_support_ids: readonly UUID[]
  bill_of_lading?: unknown | null
  vehicle_id?: UUID | null
}

export const VEHICLE_PRICE_SUPPORT_TYPES = new Set<SupportType>([
  'vehicle_discount_dealer_compensation',
  'vehicle_discount_dealer_invoice',
])

export const isVehiclePriceSupport = (support: Pick<SupportBadgeProgram, 'support_type'>): boolean =>
  VEHICLE_PRICE_SUPPORT_TYPES.has(support.support_type)

export const supportProgramsAreCompatible = (
  left: Pick<SupportBadgeProgram, 'id' | 'is_compatible' | 'compatible_support_ids'>,
  right: Pick<SupportBadgeProgram, 'id' | 'is_compatible' | 'compatible_support_ids'>,
): boolean => left.id === right.id || (
  left.is_compatible
  && right.is_compatible
  && left.compatible_support_ids.includes(right.id)
  && right.compatible_support_ids.includes(left.id)
)

export const supportCandidateCompatibilityError = (
  candidate: Pick<SupportBadgeProgram, 'id' | 'name' | 'is_compatible' | 'compatible_support_ids'>,
  selected: readonly Pick<SupportBadgeProgram, 'id' | 'name' | 'is_compatible' | 'compatible_support_ids'>[],
): string | null => {
  const conflicts = selected.filter(program => (
    program.id !== candidate.id && !supportProgramsAreCompatible(candidate, program)
  ))
  if (conflicts.length === 0) return null
  return `Несовместима с: ${conflicts.map(program => program.name).join(', ')}`
}

export const normalizeSupportPrograms = (value: unknown): SupportBadgeProgram[] => {
  if (!Array.isArray(value)) return []

  const programs = value.flatMap((entry) => {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return []
    const raw = entry as Record<string, unknown>
    if (typeof raw.id !== 'string' || typeof raw.name !== 'string') return []

    return [{
      id: raw.id as UUID,
      name: raw.name,
      support_type: typeof raw.support_type === 'string' ? raw.support_type : '',
      support_params: raw.support_params && typeof raw.support_params === 'object'
        ? raw.support_params as Record<string, unknown>
        : null,
      comment: typeof raw.comment === 'string' ? raw.comment : null,
      starts_at: typeof raw.starts_at === 'string' ? raw.starts_at : null,
      ends_at: typeof raw.ends_at === 'string' ? raw.ends_at : null,
      support_amount: typeof raw.support_amount === 'number' ? raw.support_amount : null,
      base_price: typeof raw.base_price === 'number' ? raw.base_price : null,
      display_price: typeof raw.display_price === 'number' ? raw.display_price : null,
      is_compatible: raw.is_compatible === true,
      compatible_support_ids: Array.isArray(raw.compatible_support_ids)
        ? raw.compatible_support_ids.filter((id): id is UUID => typeof id === 'string')
        : [],
      bill_of_lading: raw.bill_of_lading ?? null,
      vehicle_id: typeof raw.vehicle_id === 'string' ? raw.vehicle_id as UUID : null,
    } satisfies SupportBadgeProgram]
  })

  return Array.from(new Map(programs.map(program => [program.id, program])).values())
    .sort((left, right) => left.id.localeCompare(right.id))
}

export const supportProgramsFromSnapshot = (snapshot: Record<string, unknown> | null | undefined): SupportBadgeProgram[] => {
  if (!snapshot) return []
  return normalizeSupportPrograms(
    snapshot.selected_support_programs
    ?? snapshot.applied_support_programs
    ?? snapshot.support_programs,
  )
}
