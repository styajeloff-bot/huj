import { buildPublicRoute } from './publicRoute'

export interface StorefrontRouteAlias {
  root: string
  scoped: string
}

export const RESERVED_STOREFRONT_SLUGS = new Set([
  'workspace',
  'admin',
  'auth',
  'settings',
  'cabinet',
  'cart',
  'application',
  'questionnaire',
  'orders',
  'notifications',
  'privacy-policy',
  'terms-of-service',
  'special-equipment',
  'about',
  'api',
  '401',
  '404',
  '500',
  's',
  'custom-page',
])

export function isReservedRouteSlug(slug: string): boolean {
  if (!slug) return false
  return RESERVED_STOREFRONT_SLUGS.has(slug.toLowerCase())
}

export const STOREFRONT_ROUTE_ALIASES: readonly StorefrontRouteAlias[] = [
  { root: '/', scoped: '/:storefrontSlug' },
  { root: '/about', scoped: '/:storefrontSlug/about' },
  { root: '/special-equipment', scoped: '/:storefrontSlug/special-equipment' },
  {
    root: '/special-equipment/categories/:segments(.*)*',
    scoped: '/:storefrontSlug/special-equipment/categories/:segments(.*)*',
  },
  {
    root: '/special-equipment/products/:id/:slug',
    scoped: '/:storefrontSlug/special-equipment/products/:id/:slug',
  },
  { root: '/special-equipment/orders', scoped: '/:storefrontSlug/special-equipment/orders' },
  {
    root: '/special-equipment/orders/:id',
    scoped: '/:storefrontSlug/special-equipment/orders/:id',
  },
  { root: '/cart', scoped: '/:storefrontSlug/cart' },
  { root: '/cart/conditions', scoped: '/:storefrontSlug/cart/conditions' },
  { root: '/auth', scoped: '/:storefrontSlug/auth' },
  { root: '/auth/mfa-verify', scoped: '/:storefrontSlug/auth/mfa-verify' },
  { root: '/auth/mfa-setup-required', scoped: '/:storefrontSlug/auth/mfa-setup-required' },
  { root: '/cabinet', scoped: '/:storefrontSlug/cabinet' },
  { root: '/application/:id', scoped: '/:storefrontSlug/application/:id' },
  { root: '/questionnaire/:id', scoped: '/:storefrontSlug/questionnaire/:id' },
  { root: '/orders/:type/:id', scoped: '/:storefrontSlug/orders/:type/:id' },
  { root: '/notifications', scoped: '/:storefrontSlug/notifications' },
  { root: '/:pageSlug', scoped: '/:storefrontSlug/:pageSlug' },
] as const

export interface NuxtPageLike {
  name?: string
  path: string
  alias?: string | string[]
  children?: NuxtPageLike[]
}

function routeSegments(pathname: string): string[] {
  if (pathname === '/') return []
  const normalized = pathname.replace(/\/+$/, '')
  return normalized.split('/').filter(Boolean)
}

function matchesRootPattern(pattern: string, pathname: string): boolean {
  const patternSegments = routeSegments(pattern)
  const pathnameSegments = routeSegments(pathname)
  const catchAllIndex = patternSegments.findIndex(segment => segment.includes('(.*)*'))
  if (catchAllIndex === -1 && patternSegments.length !== pathnameSegments.length) return false
  if (catchAllIndex >= 0 && pathnameSegments.length < catchAllIndex) return false

  if (
    pattern === '/:pageSlug' &&
    pathnameSegments.length === 1 &&
    isReservedRouteSlug(pathnameSegments[0])
  ) {
    return false
  }

  return patternSegments.every((segment, index) => {
    if (segment.includes('(.*)*')) return true
    return segment.startsWith(':') || segment === pathnameSegments[index]
  })
}

export function isStorefrontOwnedRootPath(pathname: string): boolean {
  if (!pathname.startsWith('/')) return false
  return STOREFRONT_ROUTE_ALIASES.some(({ root }) => matchesRootPattern(root, pathname))
}

export function resolveStorefrontRootRedirect(
  sourceSlug: string | null,
  targetPath: string,
  targetFullPath: string,
): string | null {
  if (!sourceSlug || !isStorefrontOwnedRootPath(targetPath)) return null
  return buildPublicRoute(sourceSlug, targetFullPath)
}

function normalizeNuxtPath(routePath: string): string {
  return routePath.replace(/:([A-Za-z0-9_]+)\(\)/g, ':$1')
}

function cloneStorefrontPage(page: NuxtPageLike, scopedPath: string): NuxtPageLike {
  let name = page.name ? `${page.name}-storefront` : undefined
  if (page.name === 'default-custom-page') {
    name = 'storefront-custom-page'
  }
  const clone: NuxtPageLike = {
    ...page,
    path: scopedPath,
    name,
    children: page.children?.map(child => cloneStorefrontPage(child, child.path)),
  }
  delete clone.alias
  return clone
}

export function applyStorefrontRoutes(pages: NuxtPageLike[]): void {
  const customPageIndex = pages.findIndex(
    p => p.name === 'custom-page' || p.path === '/custom-page',
  )
  let customPage: NuxtPageLike | undefined
  if (customPageIndex !== -1) {
    customPage = pages.splice(customPageIndex, 1)[0]
    customPage.path = '/:pageSlug'
    customPage.name = 'default-custom-page'
  }

  const scopedPaths = new Map(STOREFRONT_ROUTE_ALIASES.map(item => [item.root, item.scoped]))
  const storefrontPages: NuxtPageLike[] = []

  function collect(
    sourcePages: NuxtPageLike[],
    parentPath = '',
    hasScopedAncestor = false,
  ): void {
    for (const page of sourcePages) {
      const effectivePath = page.path.startsWith('/')
        ? page.path
        : `${parentPath === '/' ? '' : parentPath}/${page.path}`
      const scopedPath = scopedPaths.get(normalizeNuxtPath(effectivePath))
      const isScopedRoot = Boolean(scopedPath) && !hasScopedAncestor

      if (scopedPath && isScopedRoot) {
        storefrontPages.push(cloneStorefrontPage(page, scopedPath))
      } else if (page.children) {
        collect(page.children, effectivePath, hasScopedAncestor || Boolean(scopedPath))
      }
    }
  }

  collect(pages)
  pages.push(...storefrontPages)

  if (customPage) {
    pages.push(customPage)
    pages.push(cloneStorefrontPage(customPage, '/:storefrontSlug/:pageSlug'))
  }
}
