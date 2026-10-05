export type IdentityVerificationProvider = 'mobile_id' | string

export type IdentityVerificationStatus =
  | 'pending'
  | 'sms_requested'
  | 'sms_verified'
  | 'verified'
  | 'failed'
  | 'expired'
  | string

export interface IdentityVerificationState {
  verified: boolean
  verified_at?: string | null
  provider?: IdentityVerificationProvider | null
  status?: IdentityVerificationStatus | null
  failure_message?: string | null
  verification_id?: string | null
  phone_masked?: string | null
  expires_at?: string | null
}

export interface StartIdentityVerificationRequest {
  birth_date?: string | null
}

export interface StartIdentityVerificationResponse {
  verification_id: string
  status: IdentityVerificationStatus
  phone_masked?: string | null
  expires_at?: string | null
  failure_message?: string | null
}

export interface SubmitIdentityVerificationSmsCodeRequest {
  code: string
}

export type SubmitIdentityVerificationSmsCodeResponse = IdentityVerificationState

export interface IdentityVerificationApiError {
  data?: {
    code?: string
    error?: string
    error_code?: string
    detail?: string | { code?: string; error?: string; message?: string; [key: string]: unknown }
    message?: string
  }
  response?: {
    status?: number
  }
  status?: number
  statusCode?: number
  message?: string
}
