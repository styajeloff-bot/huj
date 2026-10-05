import type { EmailPreferences, EmailStats } from '~/types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// ---------------------------------------------------------------------------
// Response interfaces
// ---------------------------------------------------------------------------

export interface GetPreferencesResponse {
  success: boolean
  preferences: EmailPreferences
}

export interface SavePreferencesResponse {
  success: boolean
  preferences: EmailPreferences
  message?: string
}

export interface SendTestEmailResponse {
  success: boolean
  message?: string
}

export interface GetEmailStatsResponse {
  success: boolean
  stats: EmailStats
}

// ---------------------------------------------------------------------------
// API factory
// ---------------------------------------------------------------------------

export const createEmailPreferencesApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    /** Load email notification preferences for the current user. */
    getPreferences: () =>
      request<GetPreferencesResponse>('/api/v1/email-preferences'),

    /** Update email notification preferences. */
    savePreferences: (body: EmailPreferences) =>
      request<SavePreferencesResponse>('/api/v1/email-preferences', {
        method: 'PUT',
        body: {
          application_status_emails: body.application_status_emails,
          document_request_emails: body.document_request_emails,
          document_status_emails: body.document_status_emails,
          leasing_approval_emails: body.leasing_approval_emails,
          exchange_emails: body.exchange_emails,
          system_emails: body.system_emails,
          weekly_digest: body.weekly_digest,
          marketing_emails: body.marketing_emails,
          email_frequency: body.email_frequency,
        },
      }),

    /** Send a test email to the current user's address. */
    sendTestEmail: () =>
      request<SendTestEmailResponse>('/api/v1/email-preferences/test', {
        method: 'POST',
      }),

    /** Load email delivery statistics (admin only). */
    getStats: () =>
      request<GetEmailStatsResponse>('/api/v1/email-preferences/stats'),
  }
}
