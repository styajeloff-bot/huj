import type { UUID } from '~/types/ids'

export const WORKSPACE_RETURN_STOREFRONT_QUERY = 'return_storefront'
export const WORKSPACE_RETURN_VALIDATION_STATE = 'workspace-return-storefront-validation'

export interface ValidatedWorkspaceReturnStorefront {
  id: UUID
  slug: string
}

export type WorkspaceReturnValidationCache = Record<
  string,
  ValidatedWorkspaceReturnStorefront | null
>

export type WorkspaceQueryValue = string | null | undefined | Array<string | null>
export type WorkspaceQuery = Readonly<Record<string, WorkspaceQueryValue>>

export interface WorkspaceRouteLocation {
  path: string
  query: WorkspaceQuery
  hash: string
}

export interface WorkspaceReturnSource extends WorkspaceRouteLocation {
  storefrontSlug: unknown
}

export function toWorkspaceRouteLocation<Route extends {
  path: string
  query: WorkspaceRouteLocation['query']
  hash: string
}>(route: Route): WorkspaceRouteLocation {
  return {
    path: route.path,
    query: route.query,
    hash: route.hash,
  }
}

export function isWorkspacePath(path: string): boolean {
  return path === '/workspace' || path.startsWith('/workspace/')
}

export function readWorkspaceReturnStorefront(value: unknown): string | null {
  const candidate = Array.isArray(value) ? value[0] : value
  return typeof candidate === 'string' && candidate.length > 0 ? candidate : null
}

export function readValidatedWorkspaceReturnStorefront(
  value: unknown,
  cache: WorkspaceReturnValidationCache,
): ValidatedWorkspaceReturnStorefront | null {
  const requestedSlug = readWorkspaceReturnStorefront(value)
  if (!requestedSlug) return null
  const resolved = cache[requestedSlug]
  return resolved?.slug === requestedSlug ? resolved : null
}

export function resolveWorkspaceReturnRedirect(
  source: WorkspaceReturnSource,
  target: WorkspaceRouteLocation,
): WorkspaceRouteLocation | null {
  if (!isWorkspacePath(target.path)) return null

  const storefrontSlug = readWorkspaceReturnStorefront(source.storefrontSlug)
    ?? (isWorkspacePath(source.path)
      ? readWorkspaceReturnStorefront(source.query[WORKSPACE_RETURN_STOREFRONT_QUERY])
      : null)
  if (!storefrontSlug) return null
  if (target.query[WORKSPACE_RETURN_STOREFRONT_QUERY] === storefrontSlug) return null

  return {
    path: target.path,
    query: {
      ...target.query,
      [WORKSPACE_RETURN_STOREFRONT_QUERY]: storefrontSlug,
    },
    hash: target.hash,
  }
}

export function normalizeWorkspaceReturnLocation(
  target: WorkspaceRouteLocation,
  resolvedSlug: string | null,
): WorkspaceRouteLocation | null {
  const currentValue = target.query[WORKSPACE_RETURN_STOREFRONT_QUERY]
  const hasReturnContext = Object.hasOwn(
    target.query,
    WORKSPACE_RETURN_STOREFRONT_QUERY,
  )
  if (resolvedSlug === currentValue || (!resolvedSlug && !hasReturnContext)) return null

  const query = { ...target.query }
  if (resolvedSlug) {
    query[WORKSPACE_RETURN_STOREFRONT_QUERY] = resolvedSlug
  } else {
    delete query[WORKSPACE_RETURN_STOREFRONT_QUERY]
  }

  return {
    path: target.path,
    query,
    hash: target.hash,
  }
}

export function buildWorkspaceLocation(
  path: string,
  returnStorefront: string | null,
  query: WorkspaceQuery = {},
  hash = '',
): WorkspaceRouteLocation {
  if (!isWorkspacePath(path)) {
    throw new TypeError(`Workspace route must stay under "/workspace": ${path}`)
  }

  const nextQuery = { ...query }
  if (returnStorefront) {
    nextQuery[WORKSPACE_RETURN_STOREFRONT_QUERY] = returnStorefront
  } else {
    delete nextQuery[WORKSPACE_RETURN_STOREFRONT_QUERY]
  }
  return { path, query: nextQuery, hash }
}

export function buildWorkspaceSiteRoute(returnStorefront: string | null): string {
  return returnStorefront ? `/${encodeURIComponent(returnStorefront)}` : '/'
}
