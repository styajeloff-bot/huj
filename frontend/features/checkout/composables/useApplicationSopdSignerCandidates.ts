import { ref } from 'vue'
import { useNotificationCompanyContext, useNotificationCompanyRequest } from '~/features/notifications'
import type { SopdSignerCandidate } from '~/features/checkout/types/sopdSigners'
import type { UUID } from '~/types/ids'

interface SopdSignerCandidatesResponse {
  candidates: SopdSignerCandidate[]
}

type CandidatesRequest = (applicationId: UUID) => Promise<SopdSignerCandidatesResponse>

export const createSopdSignerCandidatesLoader = (request: CandidatesRequest) => {
  const cache = new Map<UUID, SopdSignerCandidate[]>()
  const inFlight = new Map<UUID, Promise<SopdSignerCandidate[]>>()
  const versions = new Map<UUID, number>()

  const load = (applicationId: UUID): Promise<SopdSignerCandidate[]> => {
    const cached = cache.get(applicationId)
    if (cached) return Promise.resolve(cached)

    const pending = inFlight.get(applicationId)
    if (pending) return pending

    const version = versions.get(applicationId) ?? 0
    let next!: Promise<SopdSignerCandidate[]>
    next = request(applicationId)
      .then((response) => {
        if (!Array.isArray(response.candidates)) {
          throw new Error('Invalid SOPD signer candidates response')
        }
        const candidates = response.candidates
        if ((versions.get(applicationId) ?? 0) === version) {
          cache.set(applicationId, candidates)
        }
        return candidates
      })
      .finally(() => {
        if (inFlight.get(applicationId) === next) inFlight.delete(applicationId)
      })
    inFlight.set(applicationId, next)
    return next
  }

  const invalidate = (applicationId: UUID) => {
    versions.set(applicationId, (versions.get(applicationId) ?? 0) + 1)
    cache.delete(applicationId)
    inFlight.delete(applicationId)
  }

  return { load, invalidate }
}

export const useApplicationSopdSignerCandidates = (notificationCompanyContext = useNotificationCompanyContext()) => {
  const { request: notificationRequest } = useNotificationCompanyRequest(notificationCompanyContext)
  const config = useRuntimeConfig()
  const loader = createSopdSignerCandidatesLoader((applicationId) =>
    notificationRequest<SopdSignerCandidatesResponse>(
      `/api/v1/applications/${applicationId}/sopd-signer-candidates`,
      {
        baseURL: config.public.apiBase,
        credentials: 'include',
      },
    ),
  )
  const candidates = ref<SopdSignerCandidate[] | null>(null)
  const loading = ref(false)
  const error = ref('')
  const activeApplicationId = ref<UUID | null>(null)
  const stateVersion = ref(0)

  const reset = (applicationId: UUID | null) => {
    stateVersion.value += 1
    activeApplicationId.value = applicationId
    candidates.value = null
    loading.value = false
    error.value = ''
  }

  const load = async (applicationId: UUID) => {
    activeApplicationId.value = applicationId
    const requestVersion = stateVersion.value
    loading.value = true
    error.value = ''
    try {
      const resolved = await loader.load(applicationId)
      if (
        activeApplicationId.value === applicationId
        && stateVersion.value === requestVersion
      ) candidates.value = resolved
      return resolved
    } catch (cause) {
      if (
        activeApplicationId.value === applicationId
        && stateVersion.value === requestVersion
      ) {
        candidates.value = null
        error.value = 'Не удалось загрузить список подписантов СОПД'
      }
      throw cause
    } finally {
      if (
        activeApplicationId.value === applicationId
        && stateVersion.value === requestVersion
      ) loading.value = false
    }
  }

  const invalidate = (applicationId: UUID) => {
    loader.invalidate(applicationId)
    if (activeApplicationId.value === applicationId) {
      stateVersion.value += 1
      candidates.value = null
      loading.value = false
      error.value = ''
    }
  }

  return { candidates, loading, error, load, reset, invalidate }
}
