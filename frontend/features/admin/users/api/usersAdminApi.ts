import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export interface UsersPagination {
  page: number
  limit: number
  total: number
  pages: number
}

export interface User {
  id: UUID
  name: string
  is_active: boolean
  role?: string
  [key: string]: unknown
}

export interface UsersListParams {
  page?: string
  limit?: string
  search?: string
  role?: string
  is_active?: string
}

export interface UpdateUserPayload {
  is_active?: boolean
  [key: string]: unknown
}

export const createUsersAdminApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  return {
    getUsers: (params?: UsersListParams) => {
      const query = params ? new URLSearchParams(params as Record<string, string>).toString() : ''
      return request<{ users: User[]; pagination: UsersPagination }>(
        `/api/v1/users${query ? `?${query}` : ''}`
      )
    },
    updateUser: (id: UUID, payload: UpdateUserPayload) =>
      request(`/api/v1/users/${id}`, { method: 'PATCH', body: payload }),
    deleteUser: (id: UUID) =>
      request(`/api/v1/users/${id}`, { method: 'DELETE' }),
    /**
     * Admin-initiated MFA reset for a target user.
     *
     * ``reason`` is required and captured verbatim on the audit event
     * (usually a support ticket identifier). Disables MFA and kills all
     * refresh sessions of the target — equivalent to the legacy
     * ``POST /admin/auth/users/:id/reset-mfa`` endpoint (moved to
     * ``DELETE /users/:id/mfa`` in Phase 11 R8).
     */
    resetMfa: (id: UUID, reason: string) =>
      request<{ message: string; sessionsKilled: number }>(
        `/api/v1/users/${encodeURIComponent(id)}/mfa`,
        { method: 'DELETE', body: { reason } }
      )
  }
}
