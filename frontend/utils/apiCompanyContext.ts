import { isUuid } from '~/types/ids'

/** A verified selector for our API only; never decorate arbitrary external URLs. */
export const withApiCompanyContext = (
  path: string,
  parameter: 'leasing_company_id' | 'notification_company_id',
  context: unknown,
  apiBase = '',
): string => {
  if (!isUuid(context) || /[\\\u0000-\u0020]/.test(path)) return path
  const base = apiBase.replace(/\/$/, '')
  const prefix = base && path.startsWith(`${base}/api/v1/`) ? base : ''
  const internal = prefix ? path.slice(prefix.length) : path
  if (!internal.startsWith('/api/v1/')) return path
  const target = new URL(internal, 'https://api.invalid')
  if (!target.pathname.startsWith('/api/v1/')) return path
  target.searchParams.set(parameter, context)
  return `${prefix}${target.pathname}${target.search}${target.hash}`
}

export const withNotificationCompanyContext = (path: string, context: unknown, apiBase = '') =>
  withApiCompanyContext(path, 'notification_company_id', context, apiBase)
