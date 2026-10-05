import type {
  CatalogTrimAttributeCandidate,
  CatalogTrimAttributeCandidateGroup,
} from './types'

/** Project the server-ordered flat candidates into display groups without reordering them. */
export const groupTrimAttributeCandidates = (
  candidates: readonly CatalogTrimAttributeCandidate[],
): CatalogTrimAttributeCandidateGroup[] => {
  const groups = new Map<string, CatalogTrimAttributeCandidateGroup>()
  for (const candidate of candidates) {
    const key = candidate.group_id ?? 'ungrouped'
    const group = groups.get(key) ?? {
      group_id: candidate.group_id,
      group_name: candidate.group_name ?? 'Без группы',
      sort_order: candidate.sort_order,
      attributes: [],
    }
    group.attributes.push(candidate)
    groups.set(key, group)
  }
  return [...groups.values()]
}
