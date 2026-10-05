// Re-export types from the API module for convenience
import type { UUID } from '~/types/ids'

export type {
  Document,
  DocumentType,
  DocumentVersion,
  DocumentRequest,
  DocumentRequirement,
  DocumentRequestBatch,
  DocumentRequestHistoryItem,
  DocumentRequestHistoryResponse,
  DocumentRequestHistoryStatus,
  DocumentRequestLinkedDocument,
} from './api/documentsApi'

// --------------------------------------------------------------------------
// Component-level interfaces (not returned by the API but used by components)
// --------------------------------------------------------------------------

/** Shape of a document type entry used by DocumentUploader */
export interface UploaderDocType {
  id: UUID
  name: string
  required?: boolean
  description?: string
}

/** Existing document as exposed by DocumentUploader */
export interface ExistingDocument {
  id: UUID
  document_type: string
  original_name: string
  file_name?: string
  file_size: number
  status: string
  uploaded_at: string
  [key: string]: unknown
}

/** Application object referenced by DocumentUploadModal */
export interface ApplicationRef {
  id: UUID
  display_number?: string | null
  created_at: string
  [key: string]: unknown
}

/** Document version with optional comments (as used in DocumentVersionsModal) */
export interface DocVersion {
  id: UUID
  version: number
  file_name: string
  is_current_version: boolean
  status: string
  uploaded_at: string
  comments?: string
  [key: string]: unknown
}

/** Document object as used in DocumentReviewModal */
export interface ReviewableDocument {
  id: UUID
  document_type: string
  file_name: string
  file_size?: number
  uploaded_at?: string
  related_application_id?: UUID | null
  related_application_display_number?: string | null
  parent_document_id?: UUID | null
  version?: number
  [key: string]: unknown
}

/** Type codes used for the document-type display map */
export type DocumentTypeCode =
  | 'passport_general_director'
  | 'questionnaire'
  | 'consent_personal_data'
  | 'enterprise_card'
  | 'account_51_card'
  | 'income_declaration'
  | 'passport_founder'
  | 'company_charter'
  | 'lease_agreement_copy'
  | 'passport'
  | 'inn_certificate'
  | 'income_certificate'
  | 'bank_statement'
  | 'employment_certificate'
  | 'company_registration'
  | 'balance_sheet'
  | 'tax_return'
  | 'other'

/** Version status codes */
export type VersionStatus = 'uploaded' | 'under_review' | 'verified' | 'rejected'
