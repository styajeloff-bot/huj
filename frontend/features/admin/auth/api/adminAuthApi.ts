import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export interface AdminSessionInfo {
  id: UUID
  ipAddress?: string
  userAgent?: string
  countryCode?: string
  createdAt: string
  lastUsedAt?: string
  expiresAt?: string
  isCurrent?: boolean
}

export interface AdminSessionsResponse {
  sessions: AdminSessionInfo[]
}

export interface AdminUserDetail {
  id: UUID
  phone?: string
  email?: string
  name?: string
  role?: string
  is_active?: boolean
  mfa_enabled?: boolean
  created_at?: string
  [key: string]: unknown
}

export interface AdminUserResponse {
  user: AdminUserDetail
}

/**
 * API factory for the admin auth/session surface.
 *
 * All endpoints require the JWT to carry the `auth:admin` scope. The
 * `require-admin` route middleware enforces this on the frontend side
 * before the page even mounts.
 */
export const createAdminAuthApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options
    })

  return {
    /** Fetch user details. Uses the generic `/users/{id}` endpoint. */
    getUser: (id: UUID) =>
      request<AdminUserResponse>(
        `/api/v1/users/${encodeURIComponent(id)}`
      ),

    /** Active sessions for the target user. */
    getUserSessions: (id: UUID) =>
      request<AdminSessionsResponse>(
        `/api/v1/users/${encodeURIComponent(id)}/sessions`
      ),

    /** Force-revoke all sessions for the target user. */
    forceLogout: (id: UUID) =>
      request<void>(
        `/api/v1/users/${encodeURIComponent(id)}/sessions`,
        { method: 'DELETE' }
      ),

    /** Disable the user account (prevents future logins). */
    disableUser: (id: UUID) =>
      request<void>(
        `/api/v1/users/${encodeURIComponent(id)}`,
        { method: 'PATCH', body: { status: 'disabled' } }
      ),

    /** Re-enable a previously disabled user account. */
    enableUser: (id: UUID) =>
      request<void>(
        `/api/v1/users/${encodeURIComponent(id)}`,
        { method: 'PATCH', body: { status: 'active' } }
      )
  }
}
