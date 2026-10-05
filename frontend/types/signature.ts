import type { UUID } from '~/types/ids'

export type SignatureStatus =
  | 'pending'
  | 'signed_electronic'
  | 'signed_physical'
  | 'cancelled'
  | 'revoked'

export interface SignatureRequest {
  id: UUID
  user_id: UUID
  application_id?: UUID | null
  document_type: string
  status: SignatureStatus
  signature_method?: string | null
  subject_snapshot?: Record<string, unknown>
  signed_pdf_s3_key?: string | null
  sent_at?: string | null
  signed_at?: string | null
  revoked_at?: string | null
  revoke_requested_at?: string | null
  cancelled_at?: string | null
  created_at: string
  sopd_operators?: SopdOperatorStatus[]
  sopd_revoke_summary?: SopdRevokeSummary | null
}

export interface SignatureListResponse {
  items: SignatureRequest[]
}

export interface RevokeInitiateResponse {
  message: string
  revoke_request_id: UUID
  phone_masked: string
  code_ttl_seconds: number
  resend_delay_seconds: number
  revoke_requested_at: string
  revoked_leasing_companies: RevokeOperator[]
  revoked_contractors: RevokeOperator[]
  excluded_contractors: RevokeOperator[]
  is_full_revoke: boolean
}

export interface RevokeVerifyResponse {
  message: string
  status: string
  revoke_request_id: UUID
  confirmed_at: string
  revoke_requested_at?: string | null
  revoked_leasing_companies: RevokeOperator[]
  revoked_contractors: RevokeOperator[]
  excluded_contractors: RevokeOperator[]
  is_full_revoke: boolean
  document_s3_key: string
  revoke_document_download_url: string
}

export interface RevokeOperator {
  id: UUID
  name?: string | null
  inn?: string | null
  already_revoked?: boolean
  disabled?: boolean
  disabled_reason?: string | null
  leasing_company_ids?: UUID[]
  leasing_companies?: RevokeOperator[]
}

export interface RevokeOptionsResponse {
  leasing_companies: RevokeOperator[]
  contractors: RevokeOperator[]
}

export interface SopdOperatorStatus {
  operator_type: 'leasing_company' | 'contractor'
  id: UUID
  name?: string | null
  inn?: string | null
  status: 'active' | 'revoked'
  revoked_at?: string | null
  revoke_request_id?: UUID | null
  revoke_document_s3_key?: string | null
  revoke_document_download_url?: string | null
  leasing_company_ids?: UUID[]
  leasing_companies?: RevokeOperator[]
}

export interface SopdRevokeSummary {
  has_partial_revoke: boolean
  revoked_count: number
  active_count: number
  active_leasing_company_ids: UUID[]
}
