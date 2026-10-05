export interface ApiRuntimeConfig {
  apiInternalBase?: unknown
  public: {
    apiBase?: unknown
  }
}

const LOCAL_BROWSER_API_BASE = /^https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?\/?$/i
const DOCKER_API_BASE = 'http://backend:3002'

export const resolveApiBase = (
  config: ApiRuntimeConfig,
  isServer: boolean | undefined,
): string => {
  const publicApiBase = String(config.public.apiBase || '').trim()
  if (!isServer) return publicApiBase

  const internalApiBase = String(config.apiInternalBase || '').trim()
  if (internalApiBase) return internalApiBase

  if (!publicApiBase || LOCAL_BROWSER_API_BASE.test(publicApiBase)) {
    return DOCKER_API_BASE
  }
  return publicApiBase
}
