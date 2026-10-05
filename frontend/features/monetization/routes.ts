import { isUuid } from '~/types/ids'
import type { RouteLocationRaw } from 'vue-router'
import { buildWorkspaceLocation, readWorkspaceReturnStorefront } from '~/features/workspace/returnContext'
import type { Deal, Role } from './types'
export type MonetizationTarget = { kind: 'deal' | 'application'; id: string } | { kind: 'requests' } | null
export function monetizationTarget(query: Readonly<Record<string, unknown>>): MonetizationTarget {
  if (query.deal !== undefined) return isUuid(query.deal) && query.application === undefined ? { kind: 'deal', id: query.deal } : null
  if (query.application !== undefined) return isUuid(query.application) ? { kind: 'application', id: query.application } : null
  return query.tab === 'requests' ? { kind: 'requests' } : null
}
export function monetizationQuery(query: Readonly<Record<string, unknown>>, target: MonetizationTarget): Record<string, unknown> {
  const next = { ...query }
  delete next.deal; delete next.application; delete next.tab
  if (target?.kind === 'requests') next.tab = 'requests'
  else if (target) next[target.kind] = target.id
  return next
}

/** Open the source object using its existing role-specific screen and context. */
export function dealApplicationLocation(deal: Deal, role: Role, context: Readonly<Record<string, unknown>>): RouteLocationRaw | null {
  const query: Record<string, string> = {}
  if (role !== 'carcraft_employee' && isUuid(context.notification_company_id)) query.notification_company_id = context.notification_company_id
  const storefront = readWorkspaceReturnStorefront(context.return_storefront)
  if (deal.source_type === 'exchange') {
    if (role === 'carcraft_employee' || !isUuid(deal.exchange_request_id)) return null
    return buildWorkspaceLocation('/workspace/exchange', storefront, { ...query, request: deal.exchange_request_id })
  }
  if (!isUuid(deal.application_id)) return null
  if (role === 'leasing_company') {
    if (deal.leasing_company) query.leasing_company_id = deal.leasing_company.id
    return buildWorkspaceLocation('/workspace/leasing-applications/' + deal.application_id, storefront, query)
  }
  return buildWorkspaceLocation('/workspace/applications', storefront, { ...query, application: deal.application_id })
}
