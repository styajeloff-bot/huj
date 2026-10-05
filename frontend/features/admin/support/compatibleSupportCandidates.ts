import type { CatalogId, UUID } from '~/types/ids'

export interface SupportCompatibilityScope {
  mark_ids: readonly CatalogId[]
  model_ids: readonly CatalogId[]
  dealer_group_ids: readonly UUID[]
  distributor_id: UUID | null
  leasing_company_ids: readonly UUID[]
}

export interface SupportCompatibilityCandidate {
  id: UUID
  name: string
  mark_ids?: readonly CatalogId[]
  model_ids?: readonly CatalogId[]
  dealer_group_ids?: readonly UUID[]
  distributor_ids?: readonly UUID[]
  leasing_company_ids?: readonly UUID[]
}

interface CandidateFilterOptions {
  excludeProgramId?: UUID | null
}

const intersects = <T extends string>(left: readonly T[], right: readonly T[]): boolean => {
  const rightIds = new Set(right)
  return left.some(id => rightIds.has(id))
}

const matchesDimension = <T extends string>(
  currentIds: readonly T[],
  candidateIds: readonly T[] | undefined,
  candidateEmptyIsWildcard: boolean,
): boolean => {
  if (currentIds.length === 0) return true
  if (!candidateIds?.length) return candidateEmptyIsWildcard
  return intersects(currentIds, candidateIds)
}

export const hasSupportCompatibilityScope = (scope: SupportCompatibilityScope): boolean => (
  scope.mark_ids.length > 0
  || scope.model_ids.length > 0
  || scope.dealer_group_ids.length > 0
  || scope.distributor_id !== null
  || scope.leasing_company_ids.length > 0
)

export const filterCompatibleSupportCandidates = <T extends SupportCompatibilityCandidate>(
  scope: SupportCompatibilityScope,
  candidates: readonly T[],
  options: CandidateFilterOptions = {},
): T[] => {
  const currentDistributorIds = scope.distributor_id ? [scope.distributor_id] : []

  return candidates.filter(candidate => (
    candidate.id !== options.excludeProgramId
    && matchesDimension(scope.mark_ids, candidate.mark_ids, false)
    && matchesDimension(scope.model_ids, candidate.model_ids, true)
    && matchesDimension(scope.dealer_group_ids, candidate.dealer_group_ids, true)
    && matchesDimension(currentDistributorIds, candidate.distributor_ids, false)
    && matchesDimension(scope.leasing_company_ids, candidate.leasing_company_ids, true)
  ))
}

export const pruneCompatibleSupportIds = (
  selectedIds: readonly UUID[],
  candidates: readonly Pick<SupportCompatibilityCandidate, 'id'>[],
): UUID[] => {
  const candidateIds = new Set(candidates.map(candidate => candidate.id))
  return selectedIds.filter(id => candidateIds.has(id))
}
