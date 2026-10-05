import type { UUID } from '~/types/ids'
import type { Pagination, SupportProgram } from '~/types/admin'
import { formatSupportProgramPricing } from './supportProgramPresentation'

export interface SupportProgramPage {
  items: SupportProgram[]
  pagination: Pagination
}

export interface SupportDeepLinkTarget {
  id: UUID | null
  name: string | null
  pricing: string | null
}

const queryString = (value: unknown): string | null => {
  const candidate = Array.isArray(value) ? value[0] : value
  return typeof candidate === 'string' && candidate.trim() ? candidate : null
}

export const normalizeSupportLookupValue = (value: string | null | undefined): string => (
  (value || '').replace(/[\s\u00a0\u202f]+/g, ' ').trim().toLocaleLowerCase('ru-RU')
)

export const readSupportDeepLinkTarget = (
  query: Record<string, unknown>,
): SupportDeepLinkTarget | null => {
  const id = queryString(query.support_id) as UUID | null
  const name = queryString(query.support_name)
  const pricing = queryString(query.support_pricing)
  if (id) return { id, name: null, pricing: null }
  return name && pricing ? { id: null, name, pricing } : null
}

export const createSupportDeepLinkQuery = (
  target: SupportDeepLinkTarget,
): Record<string, string> | null => {
  if (target.id) return { support_id: target.id }
  if (!target.name || !target.pricing) return null
  return {
    support_name: target.name,
    support_pricing: target.pricing,
  }
}

export const supportProgramMatchesDeepLink = (
  program: SupportProgram,
  target: SupportDeepLinkTarget,
): boolean => {
  if (target.id) return program.id === target.id
  return normalizeSupportLookupValue(program.name) === normalizeSupportLookupValue(target.name)
    && normalizeSupportLookupValue(formatSupportProgramPricing(program))
      === normalizeSupportLookupValue(target.pricing)
}

export const resolveSupportProgramDeepLink = (
  programs: readonly SupportProgram[],
  target: SupportDeepLinkTarget,
): SupportProgram | null => {
  if (target.id) return programs.find(program => program.id === target.id) ?? null
  const matches = programs.filter(program => supportProgramMatchesDeepLink(program, target))
  return matches.length === 1 ? matches[0] ?? null : null
}

export const findSupportProgramAcrossPages = async (
  firstPage: SupportProgramPage,
  target: SupportDeepLinkTarget,
  fetchPage: (page: number) => Promise<SupportProgramPage>,
): Promise<SupportProgram | null> => {
  if (target.id) {
    const firstMatch = firstPage.items.find(program => supportProgramMatchesDeepLink(program, target))
    if (firstMatch) return firstMatch
  }

  const candidates = [...firstPage.items]
  for (let page = 1; page <= firstPage.pagination.pages; page += 1) {
    if (page === firstPage.pagination.page) continue
    const response = await fetchPage(page)
    if (target.id) {
      const match = response.items.find(program => supportProgramMatchesDeepLink(program, target))
      if (match) return match
    } else {
      candidates.push(...response.items)
    }
  }

  return target.id ? null : resolveSupportProgramDeepLink(candidates, target)
}
