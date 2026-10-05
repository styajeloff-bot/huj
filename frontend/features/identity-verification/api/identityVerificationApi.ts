import type {
  IdentityVerificationState,
  StartIdentityVerificationRequest,
  StartIdentityVerificationResponse,
  SubmitIdentityVerificationSmsCodeRequest,
  SubmitIdentityVerificationSmsCodeResponse,
} from '~/features/identity-verification/types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createIdentityVerificationApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    getStatus: () =>
      request<IdentityVerificationState>('/api/v1/users/me/identity-verification'),

    start: (body: StartIdentityVerificationRequest = {}) =>
      request<StartIdentityVerificationResponse>(
        '/api/v1/users/me/identity-verifications',
        { method: 'POST', body },
      ),

    submitSmsCode: (
      verificationId: string,
      body: SubmitIdentityVerificationSmsCodeRequest,
    ) =>
      request<SubmitIdentityVerificationSmsCodeResponse>(
        `/api/v1/users/me/identity-verifications/${encodeURIComponent(verificationId)}/sms-code`,
        { method: 'POST', body },
      ),
  }
}

export type IdentityVerificationApi = ReturnType<typeof createIdentityVerificationApi>
