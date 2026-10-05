import { createSectionVisibilityApi } from '../api/sectionVisibilityApi'
import { DEFAULT_SECTION_VISIBILITY } from '../config'
import {
  SectionVisibilityTargetMismatchError,
  sectionVisibilityTargetKey,
  type SectionVisibilityMatrix,
  type SectionVisibilityStatus,
  type SectionVisibilityTarget,
  type VisibilityMatrix,
  type VisibilityScope,
} from '../types'
import type { UUID } from '~/types/ids'

interface VisibilityEntry {
  matrix: VisibilityMatrix
  attempted: boolean
  loading: boolean
  error: string
  statusCode: number | null
}

const sectionsToMatrix = (
  sections: readonly SectionVisibilityMatrix['sections'][number][],
): VisibilityMatrix => Object.fromEntries(
  sections.map(section => [section.key, section.is_visible]),
)

const defaultMatrix = (scope: VisibilityScope): VisibilityMatrix => ({
  ...DEFAULT_SECTION_VISIBILITY[scope],
})

const failClosedMatrix = (scope: VisibilityScope): VisibilityMatrix => Object.fromEntries(
  Object.keys(DEFAULT_SECTION_VISIBILITY[scope]).map(key => [key, false]),
)

const errorMessage = (error: unknown): string => {
  if (error instanceof SectionVisibilityTargetMismatchError) return error.message
  const data = (error as { data?: { detail?: unknown; error?: unknown } }).data
  if (typeof data?.detail === 'string') return data.detail
  if (typeof data?.error === 'string') return data.error
  return 'Не удалось загрузить настройки видимости разделов'
}

const errorStatusCode = (error: unknown): number | null => {
  const candidate = error as {
    status?: unknown
    statusCode?: unknown
    response?: { status?: unknown }
  }
  if (typeof candidate.statusCode === 'number') return candidate.statusCode
  if (typeof candidate.status === 'number') return candidate.status
  return typeof candidate.response?.status === 'number' ? candidate.response.status : null
}

const responseMatchesTarget = (
  matrix: SectionVisibilityMatrix,
  target: SectionVisibilityTarget,
): boolean => matrix.scope === target.scope
  && matrix.storefront_id === (target.storefront?.id ?? null)

export const useSectionVisibilityStore = defineStore('section-visibility', () => {
  const api = createSectionVisibilityApi(useRuntimeConfig())
  const entries = reactive<Record<string, VisibilityEntry>>({})
  const pendingByTarget: Partial<Record<string, Promise<void>>> = {}
  const pendingTokenByTarget: Partial<Record<string, symbol>> = {}
  const activePublicTarget = ref<SectionVisibilityTarget | null>(null)
  let runtimeGeneration = 0
  let authenticatedGeneration = 0

  const entryFor = (target: SectionVisibilityTarget): VisibilityEntry => {
    const key = sectionVisibilityTargetKey(target)
    if (!entries[key]) {
      entries[key] = {
        matrix: defaultMatrix(target.scope),
        attempted: false,
        loading: false,
        error: '',
        statusCode: null,
      }
    }
    return entries[key]
  }

  const visibilityFor = (target: SectionVisibilityTarget): Readonly<VisibilityMatrix> => (
    entryFor(target).matrix
  )

  const statusFor = (target: SectionVisibilityTarget): SectionVisibilityStatus => {
    const entry = entryFor(target)
    return {
      attempted: entry.attempted,
      loading: entry.loading,
      error: entry.error,
      statusCode: entry.statusCode,
    }
  }

  const cache = (
    target: SectionVisibilityTarget,
    matrix: SectionVisibilityMatrix,
  ): void => {
    if (!responseMatchesTarget(matrix, target)) {
      throw new SectionVisibilityTargetMismatchError()
    }
    const entry = entryFor(target)
    entry.matrix = {
      ...defaultMatrix(target.scope),
      ...sectionsToMatrix(matrix.sections),
    }
    entry.attempted = true
    entry.error = ''
    entry.statusCode = null
  }

  const load = (
    target: SectionVisibilityTarget,
    force = false,
  ): Promise<void> => {
    const key = sectionVisibilityTargetKey(target)
    const entry = entryFor(target)
    if (!force && entry.attempted) return Promise.resolve()
    if (pendingByTarget[key]) return pendingByTarget[key]

    const startedRuntimeGeneration = runtimeGeneration
    const startedAuthenticatedGeneration = authenticatedGeneration
    const pendingToken = Symbol(key)
    pendingTokenByTarget[key] = pendingToken
    const isObsolete = (): boolean => startedRuntimeGeneration !== runtimeGeneration
      || (target.scope !== 'public'
        && startedAuthenticatedGeneration !== authenticatedGeneration)
    const pending = (async () => {
      entry.loading = true
      entry.error = ''
      entry.statusCode = null
      await Promise.resolve()
      try {
        const matrix = await api.getRuntime(target)
        if (isObsolete()) return
        cache(target, matrix)
      } catch (error: unknown) {
        if (isObsolete()) return
        entry.matrix = error instanceof SectionVisibilityTargetMismatchError
          ? failClosedMatrix(target.scope)
          : defaultMatrix(target.scope)
        entry.attempted = true
        entry.error = errorMessage(error)
        entry.statusCode = errorStatusCode(error)
      } finally {
        entry.loading = false
        if (pendingTokenByTarget[key] === pendingToken) {
          delete pendingByTarget[key]
          delete pendingTokenByTarget[key]
        }
      }
    })()

    pendingByTarget[key] = pending
    return pending
  }

  // Public navigation callers use the storefront resolved by the global layout.
  const loadPublic = (storefrontId: UUID, slug: string | null, force = false): Promise<void> => {
    const target: SectionVisibilityTarget = {
      scope: 'public',
      storefront: { id: storefrontId, slug },
    }
    activePublicTarget.value = target
    return load(target, force)
  }

  const visibilityForScope = (scope: VisibilityScope): Readonly<VisibilityMatrix> => {
    if (scope === 'public' && activePublicTarget.value) {
      return visibilityFor(activePublicTarget.value)
    }
    if (scope === 'carcraft_employee') {
      return visibilityFor({ scope, storefront: null })
    }
    return DEFAULT_SECTION_VISIBILITY[scope]
  }

  const isSectionVisible = (scope: VisibilityScope, key: string): boolean => (
    visibilityForScope(scope)[key] ?? DEFAULT_SECTION_VISIBILITY[scope][key] ?? false
  )

  const resetAuthenticated = (): void => {
    authenticatedGeneration += 1
    for (const key of Object.keys(entries)) {
      if (!key.startsWith('public:')) delete entries[key]
    }
    for (const key of Object.keys(pendingByTarget)) {
      if (!key.startsWith('public:')) delete pendingByTarget[key]
    }
    for (const key of Object.keys(pendingTokenByTarget)) {
      if (!key.startsWith('public:')) delete pendingTokenByTarget[key]
    }
  }

  const reset = (): void => {
    runtimeGeneration += 1
    authenticatedGeneration += 1
    for (const key of Object.keys(entries)) delete entries[key]
    for (const key of Object.keys(pendingByTarget)) delete pendingByTarget[key]
    for (const key of Object.keys(pendingTokenByTarget)) delete pendingTokenByTarget[key]
    activePublicTarget.value = null
  }

  return {
    entries,
    activePublicTarget,
    load,
    visibilityFor,
    statusFor,
    cache,
    loadPublic,
    visibilityForScope,
    isSectionVisible,
    resetAuthenticated,
    reset,
  }
})
