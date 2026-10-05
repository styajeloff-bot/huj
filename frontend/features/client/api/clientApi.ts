type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Request interfaces
// ---------------------------------------------------------------------------

export interface UpdateProfileRequest {
  name?: string | null
  email?: string | null
  birth_date?: string | null
  client_type?: string | null
  passport_series?: string | null
  passport_issued_date?: string | null
  passport_issued_by?: string | null
  company_name?: string | null
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  address?: string | null
  notification_settings?: NotificationSettings
}

export interface NotificationSettings {
  email_notifications: boolean
  sms_notifications: boolean
  marketing_emails: boolean
}

export interface PhoneChangeRequestBody {
  new_phone: string
}

export interface PhoneChangeVerifyBody {
  new_phone: string
  code: string
}

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface ClientProfile {
  id: number
  name?: string
  email?: string
  phone?: string
  birth_date?: string
  client_type?: string
  passport_series?: string
  passport_issued_date?: string
  passport_issued_by?: string
  company_name?: string
  inn?: string
  kpp?: string
  ogrn?: string
  legal_address?: string
  address?: string
  two_factor_enabled?: boolean
  notification_settings?: NotificationSettings
  created_at?: string
  last_activity?: string
}

export interface ClientStats {
  total_applications: number
  approved_applications: number
  total_amount: number
  favorites_count: number
  saved_calculations: number
  documents_count: number
}

export interface LoginHistoryEntry {
  id: number
  ip_address: string
  user_agent: string
  login_at: string
  location?: string
}

export interface ProfileResponse {
  profile: ClientProfile
  stats: ClientStats
  login_history?: LoginHistoryEntry[]
}


// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createClientApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    // Profile read/write moved to authApi.getMyProfile/patchMyProfile
    // (see Phase 13 R13a — /client/profile consolidated into /users/me).

    /** Request SMS code to verify a new phone number. */
    requestPhoneChange: (body: PhoneChangeRequestBody) =>
      request<void>('/api/v1/users/me/phone-change', { method: 'POST', body }),

    /** Verify the new phone number with the received SMS code. */
    verifyPhoneChange: (body: PhoneChangeVerifyBody) =>
      request<void>('/api/v1/users/me/phone-change/verify', { method: 'POST', body }),
  }
}
