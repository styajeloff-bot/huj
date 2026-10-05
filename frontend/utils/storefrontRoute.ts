export type PublicRouteBuilder = (path: string) => string

export const identityPublicRoute: PublicRouteBuilder = path => path

export const toStorefrontInternalRoute = (
  value: string | null | undefined,
  publicRoute: PublicRouteBuilder,
): string | null => value?.startsWith('/') && !value.startsWith('//')
  && !/[\\\u0000-\u0020]|%5c|%0[ad]|^\/%2f/i.test(value)
  ? publicRoute(value)
  : null
