import type { UUID } from '~/types/ids'

export const VISIBILITY_SCOPES = [
  'public',
  'carcraft_employee',
  'leasing_company',
  'dealer',
  'distributor',
] as const

export type VisibilityScope = typeof VISIBILITY_SCOPES[number]
export type WorkspaceVisibilityScope = Exclude<VisibilityScope, 'public'>
export type StorefrontVisibilityScope = Exclude<VisibilityScope, 'carcraft_employee'>
export type GlobalVisibilityScope = Extract<VisibilityScope, 'carcraft_employee'>

export interface VisibilityStorefrontTarget {
  id: UUID
  slug: string | null
}

export type SectionVisibilityTarget =
  | {
    scope: StorefrontVisibilityScope
    storefront: VisibilityStorefrontTarget
  }
  | {
    scope: GlobalVisibilityScope
    storefront: null
  }

export interface SectionVisibilityStatus {
  attempted: boolean
  loading: boolean
  error: string
  statusCode: number | null
}

export interface SectionVisibilityItem {
  key: string
  is_visible: boolean
}

export interface SectionVisibilityMatrix {
  scope: VisibilityScope
  storefront_id: UUID | null
  sections: SectionVisibilityItem[]
}

export interface UpdateSectionVisibilityPayload {
  sections: SectionVisibilityItem[]
}

export interface AdminSectionVisibilityMatrices {
  items: SectionVisibilityMatrix[]
}

export type VisibilityMatrix = Record<string, boolean>

export class SectionVisibilityTargetMismatchError extends Error {
  constructor() {
    super('Backend returned visibility settings for another target')
    this.name = 'SectionVisibilityTargetMismatchError'
  }
}

export const isVisibilityScope = (
  scope: string | null | undefined,
): scope is VisibilityScope => VISIBILITY_SCOPES.some(candidate => candidate === scope)

export const isWorkspaceVisibilityScope = (
  scope: string | null | undefined,
): scope is WorkspaceVisibilityScope => isVisibilityScope(scope) && scope !== 'public'

export const isStorefrontVisibilityScope = (
  scope: string | null | undefined,
): scope is StorefrontVisibilityScope => isVisibilityScope(scope) && scope !== 'carcraft_employee'

export const sectionVisibilityTargetKey = (target: SectionVisibilityTarget): string => (
  target.storefront ? `${target.scope}:${target.storefront.id}` : target.scope
)
