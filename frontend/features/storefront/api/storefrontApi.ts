import type { PublicStorefront } from '~/features/storefront/types'
import { resolveApiBase } from '~/utils/apiBase'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createPublicStorefrontApi = (config: RuntimeConfig) => {
  const baseURL = resolveApiBase(config, import.meta.server)
  const forwardedAuthHeaders = import.meta.server
    ? useRequestHeaders(['cookie', 'authorization'])
    : {}

  return {
    resolve: (slug: string | null, signal?: AbortSignal) =>
    $fetch<PublicStorefront>(
      slug ? `/api/v1/storefronts/${encodeURIComponent(slug)}` : '/api/v1/storefront',
      {
        baseURL,
        credentials: 'include',
        headers: forwardedAuthHeaders,
        signal,
      },
    ),
  }
}
