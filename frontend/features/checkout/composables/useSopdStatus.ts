import { ref } from 'vue'
import type { UUID } from '~/types/ids'

export interface SignerSopdStatus {
  hasSignedSopd: boolean
  status: 'pending' | 'signed_electronic' | 'signed_physical' | 'cancelled'
  signedPdfUrl?: string
  signatureRequestId?: UUID
}

export interface SopdStatusApiItem {
  signer_key: string
  signer_name: string
  signer_inn: string | null
  status: string
  signature_request_id: UUID
}

export const useSopdStatus = (applicationId: UUID | null) => {
  const config = useRuntimeConfig()

  const statuses = ref<Record<string, SignerSopdStatus>>({})
  const loading = ref(false)

  const fetch = async () => {
    if (!applicationId) return
    loading.value = true
    try {
      const resp = await $fetch<{ items: SopdStatusApiItem[] }>(
        `/api/v1/applications/${applicationId}/sopd-status`,
        {
          baseURL: config.public.apiBase,
          credentials: 'include',
        }
      )
      const map: Record<string, SignerSopdStatus> = {}
      for (const item of resp.items || []) {
        const key = item.signer_key
        const isSigned = item.status?.startsWith('signed')
        map[key] = {
          hasSignedSopd: isSigned,
          status: item.status as SignerSopdStatus['status'],
          signedPdfUrl: isSigned
            ? `/api/v1/signatures/${item.signature_request_id}/preview`
            : undefined,
          signatureRequestId: item.signature_request_id,
        }
      }
      statuses.value = map
    } finally {
      loading.value = false
    }
  }

  return { statuses, loading, fetch }
}
