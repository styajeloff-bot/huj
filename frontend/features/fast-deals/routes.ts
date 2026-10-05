import type { UUID } from '~/types/ids'

export const FAST_DEALS_ROUTE = '/workspace/fast-deals'

/** Card of one deal; the id is an opaque UUID string. */
export const fastDealRoute = (id: UUID): string => `${FAST_DEALS_ROUTE}/${id}`
