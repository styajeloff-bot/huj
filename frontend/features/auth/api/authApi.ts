import type { UUID } from '~/types/ids'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Request interfaces
// ---------------------------------------------------------------------------

export interface LoginRequest {
  phone: string
}

export interface RegisterRequest {
  phone: string
  email?: string
  name?: string
  companies?: Array<{
    name: string
    inn: string
    kpp?: string | null
    ogrn?: string | null
    legal_address?: string | null
    actual_address?: string | null
    phone?: string | null
    email?: string | null
    manager_name?: string | null
    entity_type?: string | null
  }>
  code?: string
}

export interface VerifyPhoneRequest {
  phone: string
  code: string
}

export interface ResendCodeRequest {
  phone: string
}

export interface MfaVerifyRequest {
  mfaToken: string
  code: string
}

export interface MfaInitRequest {
  setupToken?: string
}

export interface MfaCompleteRequest {
  code: string
  setupToken?: string
}

export interface MfaDisableRequest {
  code: string
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: UUID
  phone: string
  email?: string
  name?: string
  role: string
  company_id?: UUID | null
  company_name?: string
  scopes?: string[]
  mfa_enabled?: boolean
  sub_role?: string | null
  can_view_applications?: boolean
  can_create_applications?: boolean
  canViewApplications?: boolean
  canCreateApplications?: boolean
  identity_verified?: boolean | null
  identity_verified_at?: string | null
  identity_verification_provider?: string | null
  [key: string]: unknown
}

export interface LoginResponse {
  user?: AuthUser
  requiresVerification?: boolean
  requiresRegistration?: boolean
  mfaRequired?: boolean
  mfaToken?: string
  mfaSetupRequired?: boolean
  setupToken?: string
  phone?: string
  message?: string
  codeAlreadySent?: boolean
  error?: string
}

export interface RegisterResponse {
  user?: AuthUser
  requiresVerification?: boolean
  phone?: string
  message?: string
  error?: string
  isAlreadyRegistered?: boolean
}

export interface VerifyPhoneResponse {
  user?: AuthUser
  mfaRequired?: boolean
  mfaToken?: string
  mfaSetupRequired?: boolean
  setupToken?: string
}

export interface MeResponse {
  user: AuthUser
}

// ---------------------------------------------------------------------------
// /users/me — unified profile surface (Phase 13 R13a)
// ---------------------------------------------------------------------------

export interface ClientRoleSpecific {
  profile_id?: UUID | null
  client_type?: string | null
  passport_series?: string | null
  passport_issued_date?: string | null
  passport_issued_by?: string | null
  company_name?: string | null
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  birth_date?: string | null
  notification_settings?: Record<string, unknown> | null
  two_factor_enabled?: boolean | null
  phone_verified?: boolean | null
  identity_verified?: boolean | null
  identity_verified_at?: string | null
  identity_verification_provider?: string | null
}

export interface DealerCompanyBlock {
  id?: UUID | null
  name?: string | null
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  actual_address?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
  company_type?: string | null
}

export interface DealerSalesStats {
  total_clients: number
  total_sales: number
  total_revenue: number
  total_applications: number
  conversion_rate: number
}

export interface DealerRoleSpecific {
  company?: DealerCompanyBlock | null
  stats: DealerSalesStats
}

export interface DistributorExtensionBlock {
  id?: UUID | null
  company_id?: UUID | null
  regions?: unknown
  brands?: unknown
  is_active?: boolean | null
}

export interface DistributorRoleSpecific {
  company?: DealerCompanyBlock | null
  distributor?: DistributorExtensionBlock | null
}

export type UserMeRoleSpecific =
  | ClientRoleSpecific
  | DealerRoleSpecific
  | DistributorRoleSpecific
  | null

export interface UserMeResponse {
  id: UUID
  phone?: string | null
  email?: string | null
  name?: string | null
  role?: string | null
  company_id?: UUID | null
  is_active?: boolean | null
  role_specific: UserMeRoleSpecific
}

export interface ClientRoleSpecificPatch {
  client_type?: string | null
  passport_series?: string | null
  passport_issued_date?: string | null
  passport_issued_by?: string | null
  company_name?: string | null
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  birth_date?: string | null
  notification_settings?: Record<string, unknown> | null
}

export interface DealerCompanyPatch {
  name?: string | null
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  actual_address?: string | null
  phone?: string | null
  email?: string | null
  website?: string | null
}

export interface DealerRoleSpecificPatch {
  company?: DealerCompanyPatch | null
}

export interface UserMePatchBody {
  name?: string | null
  email?: string | null
  role_specific?: ClientRoleSpecificPatch | DealerRoleSpecificPatch | null
}

export interface MfaStatusResponse {
  enabled: boolean
  method?: string | null
  hasBackupCodes?: boolean
  backupCodesRemaining?: number | null
}

export interface MfaSetupResponse {
  secret: string
  otpauthUrl: string
  qrPngBase64: string
}

export interface MfaCompleteResponse {
  message?: string
  user?: AuthUser
  backupCodes: string[]
}

export interface MfaVerifyResponse {
  user: AuthUser
}

export interface MfaDisableResponse {
  message: string
}

export interface MfaBackupCodesResponse {
  backupCodes: string[]
}

export interface SessionInfo {
  id: UUID
  ipAddress?: string
  userAgent?: string
  countryCode?: string
  createdAt: string
  lastUsedAt?: string
  expiresAt?: string
  isCurrent?: boolean
}

export interface SessionsListResponse {
  sessions: SessionInfo[]
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

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createAuthApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    /** Login by phone number. May return requiresVerification / requiresRegistration / mfaRequired. */
    login: (body: LoginRequest) =>
      request<LoginResponse>('/api/v1/auth/login', { method: 'POST', body }),

    /** Register a new user (optionally with companies). */
    register: (body: RegisterRequest) =>
      request<RegisterResponse>('/api/v1/auth/register', { method: 'POST', body }),

    /** Verify phone with SMS code. May return mfaRequired / mfaSetupRequired. */
    verifyPhone: (body: VerifyPhoneRequest) =>
      request<VerifyPhoneResponse>('/api/v1/auth/verify-phone', { method: 'POST', body }),

    /** Resend SMS verification code. */
    resendCode: (body: ResendCodeRequest) =>
      request<void>('/api/v1/auth/resend-code', { method: 'POST', body }),

    /** Logout the current session. */
    logout: () =>
      request<void>('/api/v1/auth/logout', { method: 'POST' }),

    /** Refresh the access token using the refresh cookie. */
    refresh: () =>
      request<void>('/api/v1/auth/refresh', { method: 'POST' }),

    /** Get the currently authenticated user. */
    me: () =>
      request<MeResponse>('/api/v1/auth/me'),

    /** Get the unified profile for the current user (Phase 13 R13a).
     *
     * Returns base identity fields plus a ``role_specific`` block whose
     * shape depends on the caller's role:
     *  - client → `ClientRoleSpecific` (client_profiles projection)
     *  - dealer → `DealerRoleSpecific` (company + sales stats)
     *  - distributor → `DistributorRoleSpecific` (company + distributor row)
     *  - other roles → null
     *
     * Replaces the removed `/client/profile`, `/dealer/profile`,
     * `/distributor/profile` endpoints.
     */
    getMyProfile: () =>
      request<UserMeResponse>('/api/v1/users/me'),

    /** Partial update of the current user's profile. */
    patchMyProfile: (body: UserMePatchBody) =>
      request<UserMeResponse>('/api/v1/users/me', {
        method: 'PATCH',
        body,
      }),

    // --- MFA lifecycle (R8 consolidated surface) --------------------------
    // GET    /auth/mfa               — status
    // POST   /auth/mfa               — init setup (auth or setupToken body)
    // PUT    /auth/mfa               — complete setup (auth or setupToken)
    // DELETE /auth/mfa               — disable (body: {code})
    // POST   /auth/mfa/backup-codes  — regenerate backup codes
    // POST   /auth/mfa/verify        — runtime step-up during login

    /** Current MFA status for the authenticated user. */
    getMfaStatus: () =>
      request<MfaStatusResponse>('/api/v1/auth/mfa'),

    /** Start MFA setup — returns QR + secret to display.
     *
     * When the user is already fully authenticated, omit `setupToken`.
     * During the half-session mandatory-enrolment flow (verify-phone
     * returned `mfaSetupRequired: true, setupToken`), pass the token in
     * the body so the backend accepts the request without an access
     * cookie.
     */
    setupMfa: (body: MfaInitRequest = {}) =>
      request<MfaSetupResponse>('/api/v1/auth/mfa', { method: 'POST', body }),

    /** Confirm MFA setup with a TOTP code. Returns backup codes (show once).
     *
     * Pass `setupToken` for mandatory-enrolment flow — response then
     * includes `user` and sets auth cookies. Without it, response has
     * `message` instead.
     */
    completeMfa: (body: MfaCompleteRequest) =>
      request<MfaCompleteResponse>('/api/v1/auth/mfa', {
        method: 'PUT',
        body,
      }),

    /** Disable MFA for the authenticated user. Requires a current TOTP. */
    disableMfa: (body: MfaDisableRequest) =>
      request<MfaDisableResponse>('/api/v1/auth/mfa', {
        method: 'DELETE',
        body,
      }),

    /** Regenerate backup codes (returns a fresh set once). */
    regenerateMfaBackupCodes: () =>
      request<MfaBackupCodesResponse>(
        '/api/v1/auth/mfa/backup-codes',
        { method: 'POST' },
      ),

    // --- MFA step-up during login (unauthenticated, uses mfaToken) --------

    /** Finalize login with a TOTP or backup code after primary auth. */
    verifyMfa: (body: MfaVerifyRequest) =>
      request<MfaVerifyResponse>('/api/v1/auth/mfa/verify', {
        method: 'POST',
        body,
      }),

    /** Consume a magic-link token (signature invitation flow). */
    consumeMagicLink: (token: string) =>
      request<{ message: string; user: { name?: string | null } }>('/api/v1/auth/magic/consume', {
        method: 'POST',
        body: { token },
      }),

    // --- Session management (current user) --------------------------------

    listSessions: () =>
      request<SessionsListResponse>('/api/v1/users/me/sessions'),

    revokeSession: (id: UUID) =>
      request<void>(`/api/v1/users/me/sessions/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      }),

    revokeAllSessions: () =>
      request<void>('/api/v1/users/me/sessions', { method: 'DELETE' }),

    // --- Employee management (company-scoped) -----------------------------

    inviteEmployee: (companyId: UUID, phone: string) =>
      request<{ message: string; user_id: UUID }>(
        `/api/v1/users/me/companies/${encodeURIComponent(companyId)}/invite`,
        { method: 'POST', body: { phone } },
      ),

    listCompanyMembers: (companyId: UUID) =>
      request<{ members: Array<{
        user_id: UUID
        name?: string | null
        phone?: string | null
        sub_role?: string | null
        can_view_applications: boolean
        can_create_applications: boolean
      }> }>(
        `/api/v1/users/me/companies/${encodeURIComponent(companyId)}/members`,
      ),

    updateMemberPermissions: (companyId: UUID, userId: UUID, permissions: {
      canViewApplications?: boolean
      canCreateApplications?: boolean
    }) =>
      request<{ message: string }>(
        `/api/v1/users/me/companies/${encodeURIComponent(companyId)}/members/${encodeURIComponent(userId)}/permissions`,
        { method: 'PATCH', body: permissions },
      ),

    updateMemberRole: (companyId: UUID, userId: UUID, subRole: string) =>
      request<{ message: string }>(
        `/api/v1/users/me/companies/${encodeURIComponent(companyId)}/members/${encodeURIComponent(userId)}/role`,
        { method: 'PATCH', body: { sub_role: subRole } },
      ),

    removeCompanyMember: (companyId: UUID, userId: UUID) =>
      request<void>(
        `/api/v1/users/me/companies/${encodeURIComponent(companyId)}/members/${encodeURIComponent(userId)}`,
        { method: 'DELETE' },
      ),
  }
}

// ---------------------------------------------------------------------------
// Admin API factory (scope: auth:admin)
// ---------------------------------------------------------------------------

export const createAuthAdminApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    getUser: (id: UUID) =>
      request<{ user: AdminUserDetail }>(`/api/v1/users/${encodeURIComponent(id)}`),

    getUserSessions: (id: UUID) =>
      request<SessionsListResponse>(
        `/api/v1/users/${encodeURIComponent(id)}/sessions`,
      ),

    forceLogout: (id: UUID) =>
      request<void>(
        `/api/v1/users/${encodeURIComponent(id)}/sessions`,
        { method: 'DELETE' },
      ),

    disableUser: (id: UUID) =>
      request<void>(
        `/api/v1/users/${encodeURIComponent(id)}`,
        { method: 'PATCH', body: { status: 'disabled' } },
      ),

    enableUser: (id: UUID) =>
      request<void>(
        `/api/v1/users/${encodeURIComponent(id)}`,
        { method: 'PATCH', body: { status: 'active' } },
      ),
  }
}
