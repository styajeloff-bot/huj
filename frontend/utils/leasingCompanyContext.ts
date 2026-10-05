import { withApiCompanyContext } from '~/utils/apiCompanyContext'

/** Carry an explicit LC context only to our API, never an external download. */
export const withLeasingCompanyContext = (path: string, context: unknown): string =>
  withApiCompanyContext(path, 'leasing_company_id', context)
