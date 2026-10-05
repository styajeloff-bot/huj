const ROOT_STOREFRONT_KEY = 'root'

function assertRootRelative(path: string): void {
  if (!path.startsWith('/')) {
    throw new TypeError(`Storefront route must start with "/": ${path}`)
  }
}

export function buildPublicRoute(slug: string | null, path: string): string {
  assertRootRelative(path)
  if (!slug) return path
  if (path === '/') return `/${encodeURIComponent(slug)}`
  if (path.startsWith('/?') || path.startsWith('/#')) {
    return `/${encodeURIComponent(slug)}${path.slice(1)}`
  }
  return `/${encodeURIComponent(slug)}${path}`
}

export function buildStorefrontApiPath(slug: string | null, path: string): string {
  assertRootRelative(path)
  const prefix = slug
    ? `/api/v1/storefronts/${encodeURIComponent(slug)}`
    : '/api/v1'
  return `${prefix}${path}`
}

export function buildStorefrontStorageKey(
  storefrontId: string | null,
  key: string,
): string {
  const namespace = storefrontId || ROOT_STOREFRONT_KEY
  return `storefront:${namespace}:${key}`
}

export function replaceStorefrontSlug(fullPath: string, normalizedSlug: string): string {
  assertRootRelative(fullPath)
  return fullPath.replace(/^\/[^/?#]+/, `/${encodeURIComponent(normalizedSlug)}`)
}
