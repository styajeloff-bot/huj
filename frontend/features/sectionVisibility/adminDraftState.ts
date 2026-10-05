import {
  DEFAULT_SECTION_VISIBILITY,
  SECTION_VISIBILITY_CATALOG,
  STOREFRONT_VISIBILITY_SCOPES,
} from './config'
import {
  isStorefrontVisibilityScope,
  type GlobalVisibilityScope,
  type SectionVisibilityItem,
  type SectionVisibilityMatrix,
  type StorefrontVisibilityScope,
  type VisibilityMatrix,
  type VisibilityScope,
} from './types'
import type { UUID } from '~/types/ids'

export interface AdminVisibilityStorefrontTarget {
  id: UUID
  is_default: boolean
}

type StorefrontDrafts = Record<StorefrontVisibilityScope, Record<UUID, VisibilityMatrix>>

export interface AdminVisibilityDraftState {
  globalDrafts: Record<GlobalVisibilityScope, VisibilityMatrix>
  globalSaved: Record<GlobalVisibilityScope, VisibilityMatrix>
  storefrontDrafts: StorefrontDrafts
  storefrontSaved: StorefrontDrafts
}

const configurableKeys = (scope: VisibilityScope, extraKeys: string[] = []): string[] => {
  const base = SECTION_VISIBILITY_CATALOG[scope].map(item => item.key)
  if (scope === 'public' && extraKeys.length > 0) {
    return Array.from(new Set([...base, ...extraKeys]))
  }
  return base
}

const createGlobalMatrices = (): Record<GlobalVisibilityScope, VisibilityMatrix> => ({
  carcraft_employee: { ...DEFAULT_SECTION_VISIBILITY.carcraft_employee },
})

const createStorefrontMatrices = (): StorefrontDrafts => Object.fromEntries(
  STOREFRONT_VISIBILITY_SCOPES.map(scope => [scope, {}]),
) as StorefrontDrafts

const matrixValues = (
  scope: VisibilityScope,
  matrix?: SectionVisibilityMatrix,
  extraKeys: string[] = [],
): VisibilityMatrix => {
  const responseValues = Object.fromEntries(
    (matrix?.sections ?? []).map(section => [section.key, section.is_visible]),
  )
  const dynamicKeys = scope === 'public'
    ? [...extraKeys, ...(matrix?.sections ?? []).map(s => s.key)]
    : extraKeys
  return Object.fromEntries(
    configurableKeys(scope, dynamicKeys).map(key => [
      key,
      responseValues[key] ?? DEFAULT_SECTION_VISIBILITY[scope]?.[key] ?? true,
    ]),
  )
}

export const createAdminVisibilityDraftState = (): AdminVisibilityDraftState => ({
  globalDrafts: createGlobalMatrices(),
  globalSaved: createGlobalMatrices(),
  storefrontDrafts: createStorefrontMatrices(),
  storefrontSaved: createStorefrontMatrices(),
})

export const replaceAdminGlobalVisibilityDraft = (
  state: AdminVisibilityDraftState,
  matrix: SectionVisibilityMatrix,
): void => {
  if (matrix.scope !== 'carcraft_employee' || matrix.storefront_id !== null) {
    throw new Error('Backend returned storefront settings for the global employee scope')
  }
  const next = matrixValues('carcraft_employee', matrix)
  state.globalDrafts.carcraft_employee = { ...next }
  state.globalSaved.carcraft_employee = { ...next }
}

export const replaceAdminStorefrontVisibilityDraft = (
  state: AdminVisibilityDraftState,
  storefront: AdminVisibilityStorefrontTarget,
  matrix: SectionVisibilityMatrix,
  extraKeys: string[] = [],
): void => {
  if (!isStorefrontVisibilityScope(matrix.scope) || matrix.storefront_id !== storefront.id) {
    throw new Error('Backend returned visibility settings for another storefront target')
  }
  const scope = matrix.scope
  const next = matrixValues(scope, matrix, extraKeys)
  state.storefrontDrafts[scope][storefront.id] = { ...next }
  state.storefrontSaved[scope][storefront.id] = { ...next }
}

export const refreshAdminStorefrontVisibilityDraft = (
  state: AdminVisibilityDraftState,
  storefront: AdminVisibilityStorefrontTarget,
  matrix: SectionVisibilityMatrix,
  forcedVisibleKey?: string,
  extraKeys: string[] = [],
): void => {
  if (!isStorefrontVisibilityScope(matrix.scope) || matrix.storefront_id !== storefront.id) {
    throw new Error('Backend returned visibility settings for another storefront target')
  }
  const scope = matrix.scope
  const nextSaved = matrixValues(scope, matrix, extraKeys)
  const previousDraft = state.storefrontDrafts[scope][storefront.id]
  const previousSaved = state.storefrontSaved[scope][storefront.id]
  const nextDraft = { ...nextSaved }

  if (previousDraft && previousSaved) {
    const allKeys = Array.from(new Set([
      ...configurableKeys(scope, extraKeys),
      ...Object.keys(previousDraft),
      ...Object.keys(nextSaved),
    ]))
    for (const key of allKeys) {
      if (key !== forcedVisibleKey && previousDraft[key] !== previousSaved[key]) {
        nextDraft[key] = previousDraft[key] !== false
      }
    }
  }

  state.storefrontDrafts[scope][storefront.id] = nextDraft
  state.storefrontSaved[scope][storefront.id] = { ...nextSaved }
}

export const getAdminVisibilityDraft = (
  state: AdminVisibilityDraftState,
  scope: VisibilityScope,
  storefrontId: UUID | null,
): VisibilityMatrix | null => {
  if (scope === 'carcraft_employee') return state.globalDrafts.carcraft_employee
  return storefrontId ? state.storefrontDrafts[scope][storefrontId] ?? null : null
}

export const isAdminVisibilityTargetDirty = (
  state: AdminVisibilityDraftState,
  scope: VisibilityScope,
  storefrontId: UUID | null,
  extraKeys: string[] = [],
): boolean => {
  const draft = getAdminVisibilityDraft(state, scope, storefrontId)
  const saved = scope === 'carcraft_employee'
    ? state.globalSaved.carcraft_employee
    : storefrontId ? state.storefrontSaved[scope][storefrontId] : null
  if (!draft || !saved) return false
  const keys = Array.from(new Set([
    ...configurableKeys(scope, extraKeys),
    ...Object.keys(draft),
    ...Object.keys(saved),
  ]))
  return keys.some(key => draft[key] !== saved[key])
}

export const isAdminVisibilityScopeDirty = (
  state: AdminVisibilityDraftState,
  scope: VisibilityScope,
  extraKeys: string[] = [],
): boolean => {
  if (scope === 'carcraft_employee') {
    return isAdminVisibilityTargetDirty(state, scope, null, extraKeys)
  }
  return Object.keys(state.storefrontDrafts[scope]).some(
    storefrontId => isAdminVisibilityTargetDirty(state, scope, storefrontId, extraKeys),
  )
}

export const setAdminVisibilityDraftValue = (
  state: AdminVisibilityDraftState,
  scope: VisibilityScope,
  storefront: AdminVisibilityStorefrontTarget | null,
  key: string,
  isVisible: boolean,
  extraKeys: string[] = [],
): boolean => {
  const draft = getAdminVisibilityDraft(state, scope, storefront?.id ?? null)
  if (!draft) return false
  if (!configurableKeys(scope, extraKeys).includes(key) && !(key in draft)) return false

  draft[key] = isVisible
  return true
}

export const buildAdminVisibilityUpdates = (
  state: AdminVisibilityDraftState,
  scope: VisibilityScope,
  storefrontId: UUID | null,
  extraKeys: string[] = [],
): SectionVisibilityItem[] => {
  const draft = getAdminVisibilityDraft(state, scope, storefrontId)
  const saved = scope === 'carcraft_employee'
    ? state.globalSaved.carcraft_employee
    : storefrontId ? state.storefrontSaved[scope][storefrontId] : null
  if (!draft || !saved) return []
  const keys = Array.from(new Set([
    ...configurableKeys(scope, extraKeys),
    ...Object.keys(draft),
    ...Object.keys(saved),
  ]))
  return keys
    .filter(key => draft[key] !== saved[key])
    .map(key => ({ key, is_visible: draft[key] !== false }))
}
