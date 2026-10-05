import { toStorefrontInternalRoute, type PublicRouteBuilder } from '~/utils/storefrontRoute'
import { isUuid } from '~/types/ids'

/** Workspace routes are global; only the canonical client route belongs to a storefront. */
export const notificationActionRoute = (
  value: string | null | undefined,
  publicRoute: PublicRouteBuilder,
  notificationId?: string,
): string | null => {
  const target = toStorefrontInternalRoute(value, path => path.startsWith('/application/') ? publicRoute(path) : path)
  if (!target || !isUuid(notificationId)) return target
  const url = new URL(target, 'https://notification.invalid')
  const application = target.split(/[?#]/, 1)[0]?.match(/^(?:\/[a-z0-9][a-z0-9-]*)?\/application\/([^/]+)$/)
  if (!application || !isUuid(application[1]) || !['3', '4', '5', '6', '7', '8'].includes(url.searchParams.get('step') || '')) return target
  // Two inbox events may target the same section. Route metadata activates the
  // new notification without reloading the app or changing global company state.
  url.searchParams.set('notification_id', notificationId)
  return `${url.pathname}${url.search}${url.hash}`
}
