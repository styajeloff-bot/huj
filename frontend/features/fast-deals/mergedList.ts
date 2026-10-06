import type { FastDealListItem } from './types'

/**
 * «Мои заявки» (dealer, distributor, administrator, leasing company) return ordinary applications
 * and fast deals in ONE ordered list. The server tells them apart with `kind` and filters with
 * the `kind` query parameter; the status filter of ordinary applications excludes fast deals.
 */
export type ApplicationListKind = 'application' | 'fast_deal'

export const FAST_DEAL_KIND_LABEL = 'Быстрая регистрация'

export const APPLICATION_KIND_OPTIONS: ReadonlyArray<{ value: ApplicationListKind; label: string }> = [
  { value: 'application', label: 'Обычные заявки' },
  { value: 'fast_deal', label: FAST_DEAL_KIND_LABEL },
]

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

/** A flat list row of a fast deal (`kind: 'fast_deal'`); anything else is an ordinary application. */
export const isFastDealRow = (row: unknown): row is FastDealListItem =>
  isRecord(row) && row.kind === 'fast_deal' && typeof row.id === 'string'

/**
 * Fast deal of a list entry whose ordinary shape is wrapped (`{ link, application }` of the leasing
 * company list): either the entry itself carries `kind: 'fast_deal'` or it holds the row in `fast_deal`.
 */
export const asFastDealRow = (entry: unknown): FastDealListItem | null => {
  if (isFastDealRow(entry)) return entry
  if (isRecord(entry) && isRecord(entry.fast_deal) && typeof entry.fast_deal.id === 'string') {
    return { ...(entry.fast_deal as unknown as FastDealListItem), kind: 'fast_deal' }
  }
  return null
}

/** Ordinary rows only, e.g. for code that works with applications and must never see fast deals. */
export const ordinaryRows = <T extends object>(rows: ReadonlyArray<T | FastDealListItem>): T[] =>
  rows.filter((row): row is T => !isFastDealRow(row))

/** `kind` is sent only when the user narrowed the list; without it the server returns the union. */
export const kindQueryValue = (kind: ApplicationListKind | ''): ApplicationListKind | undefined =>
  kind === '' ? undefined : kind
