import { STOREFRONT_VISIBILITY_SCOPES } from './config'
import type {
  SectionVisibilityMatrix,
  StorefrontVisibilityScope,
} from './types'
import type { UUID } from '~/types/ids'

export interface AdminStorefrontVisibilityLoadStatus {
  attempted: boolean
  pending: boolean
  error: string
}

export interface AdminStorefrontVisibilityLoadState {
  entries: Record<string, AdminStorefrontVisibilityLoadStatus>
}

export interface AdminStorefrontVisibilityBatchValidation {
  matrices: Partial<Record<StorefrontVisibilityScope, SectionVisibilityMatrix>>
  errors: Partial<Record<StorefrontVisibilityScope, string>>
}

export const adminStorefrontVisibilityTargetKey = (
  scope: StorefrontVisibilityScope,
  storefrontId: UUID,
): string => `${scope}:${storefrontId}`

const emptyStatus = (): AdminStorefrontVisibilityLoadStatus => ({
  attempted: false,
  pending: false,
  error: '',
})

const statusEntry = (
  state: AdminStorefrontVisibilityLoadState,
  scope: StorefrontVisibilityScope,
  storefrontId: UUID,
): AdminStorefrontVisibilityLoadStatus => {
  const key = adminStorefrontVisibilityTargetKey(scope, storefrontId)
  state.entries[key] ??= emptyStatus()
  return state.entries[key]
}

export const createAdminStorefrontVisibilityLoadState = (
): AdminStorefrontVisibilityLoadState => ({ entries: {} })

export const getAdminStorefrontVisibilityLoadStatus = (
  state: AdminStorefrontVisibilityLoadState,
  scope: StorefrontVisibilityScope,
  storefrontId: UUID,
): Readonly<AdminStorefrontVisibilityLoadStatus> => statusEntry(state, scope, storefrontId)

export const beginAdminStorefrontVisibilityBatch = (
  state: AdminStorefrontVisibilityLoadState,
  storefrontId: UUID,
): void => {
  for (const scope of STOREFRONT_VISIBILITY_SCOPES) {
    const status = statusEntry(state, scope, storefrontId)
    status.pending = true
    status.error = ''
  }
}

export const validateAdminStorefrontVisibilityBatch = (
  storefrontId: UUID,
  items: readonly SectionVisibilityMatrix[],
): AdminStorefrontVisibilityBatchValidation => {
  const result: AdminStorefrontVisibilityBatchValidation = {
    matrices: {},
    errors: {},
  }

  for (const scope of STOREFRONT_VISIBILITY_SCOPES) {
    const candidates = items.filter(item => item.scope === scope)
    if (candidates.length === 0) {
      result.errors[scope] = `Сервер не вернул настройки области «${scope}»`
      continue
    }
    if (candidates.length > 1) {
      result.errors[scope] = `Сервер вернул несколько матриц области «${scope}»`
      continue
    }
    const matrix = candidates[0]
    if (!matrix || matrix.storefront_id !== storefrontId) {
      result.errors[scope] = `Сервер вернул настройки области «${scope}» для другой витрины`
      continue
    }
    result.matrices[scope] = matrix
  }

  return result
}

export const completeAdminStorefrontVisibilityBatch = (
  state: AdminStorefrontVisibilityLoadState,
  storefrontId: UUID,
  result: AdminStorefrontVisibilityBatchValidation,
): void => {
  for (const scope of STOREFRONT_VISIBILITY_SCOPES) {
    const status = statusEntry(state, scope, storefrontId)
    status.attempted = true
    status.pending = false
    status.error = result.errors[scope] ?? ''
  }
}

export const failAdminStorefrontVisibilityBatch = (
  state: AdminStorefrontVisibilityLoadState,
  storefrontId: UUID,
  error: string,
): void => {
  for (const scope of STOREFRONT_VISIBILITY_SCOPES) {
    const status = statusEntry(state, scope, storefrontId)
    status.attempted = true
    status.pending = false
    status.error = error
  }
}
