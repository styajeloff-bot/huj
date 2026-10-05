import type { $Fetch } from 'ofetch'
import type { UUID } from '~/types/ids'
import { withLeasingCompanyContext } from '~/utils/leasingCompanyContext'
import { withNotificationCompanyContext } from '~/utils/apiCompanyContext'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Document {
  id: UUID
  document_type: string
  file_name: string
  file_size?: number
  status: string
  leasing_company_status?: string
  related_application_id?: UUID | null
  parent_document_id?: UUID | null
  uploaded_at: string
  [key: string]: unknown
}

export interface DocumentRequestFormSchema {
  schema_version: number
  kind: 'main_counterparties' | 'snils' | 'open_bank_accounts' | 'beneficial_owner'
  /** Optional presentation metadata. It is consumed only by the fixed form-kind allowlist. */
  labels?: Record<string, string>
  min_items?: number
  max_items?: number
  fields?: Record<string, { label?: string; placeholder?: string }>
  [key: string]: unknown
}

export interface DocumentType {
  id?: UUID
  type_code: string
  display_name: string
  has_form: boolean
  form_schema: DocumentRequestFormSchema | null
  [key: string]: unknown
}

export interface DocumentVersion {
  id: UUID
  version: number
  file_name: string
  is_current_version: boolean
  status: string
  uploaded_at: string
  [key: string]: unknown
}

export interface DocumentRequest {
  id: UUID
  document_type: string
  status: string
  max_file_size_mb?: number
  uploaded_file_name?: string
  uploaded_document_id?: UUID
  [key: string]: unknown
}

export interface DocumentRequirement {
  document_type: string
  [key: string]: unknown
}

export type DocumentRequestHistoryStatus =
  | 'requested'
  | 'provided'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'superseded'

export interface DocumentRequestLinkedDocument {
  /** ID of the application_documents association. */
  id: UUID
  /** ID of the underlying document used by the download URL. */
  document_id: UUID
  file_name: string | null
  file_size: number | null
  uploaded_at: string | null
  status: string | null
  download_url: string | null
}

export interface DocumentRequestHistoryItem {
  id: UUID
  display_name: string
  slug: string
  status: DocumentRequestHistoryStatus
  provided_at: string | null
  /** Legacy field retained for historical responses. */
  document: DocumentRequestLinkedDocument | null
  document_type: string
  has_form: boolean
  form_schema: DocumentRequestFormSchema | null
  /** Returned only when the server authorizes the current role to see it. */
  form_data: Record<string, unknown> | null
  /** Canonical complete response package; absent in historical responses. */
  attachments?: DocumentRequestLinkedDocument[]
  /** Legacy first attachment, retained only for historical API responses. */
  attachment: DocumentRequestLinkedDocument | null
}

export interface DocumentRequestBatch {
  request_batch_id: UUID
  leasing_company: {
    id: UUID
    name: string
  }
  comments: string | null
  requested_by: {
    id: UUID
    name: string
  } | null
  requested_at: string | null
  items: DocumentRequestHistoryItem[]
}

// -- Responses --------------------------------------------------------------

export interface DocumentTypesResponse {
  types: DocumentType[]
  total: number
}

export interface DocumentsListResponse {
  documents: Document[]
  total: number
}

export interface UserEnhancedDocumentsResponse {
  documents: Document[]
  requirements: DocumentRequirement[]
  total: number
}

export interface ApplicationDocumentsResponse {
  application_id: UUID
  documents: Document[]
  total: number
}

export interface RequestedDocumentsResponse {
  application_id: UUID
  requirements: DocumentRequirement[]
  total: number
}

export interface DocumentRequirementsResponse {
  requirements: DocumentRequirement[]
  total: number
}

export interface DocumentRequestHistoryResponse {
  application_id: UUID
  batches: DocumentRequestBatch[]
  total: number
}

// Unified POST /documents response (Phase 10 R4).
export interface UploadDocumentsResponse {
  documents: Document[]
  total: number
  application_id?: UUID | null
}

export interface VersionsResponse {
  versions: DocumentVersion[]
  total: number
}

export interface ReviewBody {
  status: 'approved' | 'rejected' | 'revision_required'
  comments?: string
}

export interface UploadOptions {
  /** Attach the upload to a leasing application (document_applications M2M). */
  applicationId?: UUID
  /** Link this upload to one exact application document request. */
  documentRequestId?: UUID
  /** Upload a new version of this document (version-flow). */
  parentDocumentId?: UUID
  /** Trigger DBRAIN recognition fire-and-forget. */
  ocr?: boolean
  /** type_code for all files when a single type applies to every file. */
  documentType?: string
  /**
   * type_code per file — must match the order of files. JSON-array or
   * comma-separated both accepted by the backend.
   */
  documentTypes?: string[]
  /** Serialized server-validated form data for a document request. */
  formData?: Record<string, unknown>
  /** UUID used to make a document-request response idempotent. */
  idempotencyKey?: string
  userTitles?: string[]
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

const buildUploadForm = (files: File[], options: UploadOptions = {}): FormData => {
  const form = new FormData()
  for (const file of files) {
    form.append('files', file)
  }
  if (options.documentType) {
    form.append('document_type', options.documentType)
  }
  if (options.documentTypes && options.documentTypes.length > 0) {
    form.append('document_types', JSON.stringify(options.documentTypes))
  }
  if (options.applicationId !== undefined && options.applicationId !== null) {
    form.append('application_id', options.applicationId)
  }
  if (options.documentRequestId !== undefined && options.documentRequestId !== null) {
    form.append('document_request_id', options.documentRequestId)
  }
  if (options.userTitles !== undefined) form.append('user_titles', JSON.stringify(options.userTitles))
  if (options.formData !== undefined) {
    form.append('form_data', JSON.stringify(options.formData))
  }
  if (options.parentDocumentId !== undefined && options.parentDocumentId !== null) {
    form.append('parent_document_id', options.parentDocumentId)
  }
  if (options.ocr) {
    form.append('ocr', 'true')
  }
  return form
}

export const createDocumentsApi = (config: RuntimeConfig, leasingCompanyContext?: () => unknown, notificationCompanyContext?: () => unknown) => {
  const contextualUrl = (url: string) => withNotificationCompanyContext(
    withLeasingCompanyContext(url, leasingCompanyContext?.()), notificationCompanyContext?.(), String(config.public.apiBase || ''),
  )
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(contextualUrl(url), {
      baseURL: config.public.apiBase, credentials: 'include', ...options,
    })

  return {
    downloadUrl(path: string): string {
      if (/^https?:\/\//.test(path)) return contextualUrl(path)
      const base = String(config.public.apiBase || '').replace(/\/$/, '')
      const internalPath = path.startsWith('/') ? path : `/${path}`
      return `${base}${contextualUrl(internalPath)}`
    },
    // ---- Document types ---------------------------------------------------

    /** GET /api/v1/documents/types — list available document types */
    getDocumentTypes() {
      return request<DocumentTypesResponse>('/api/v1/documents/types')
    },

    // ---- Fetching documents (unified /documents?scope=...) ----------------

    /** GET /api/v1/documents?scope=user — current user's documents */
    getUserDocuments() {
      return request<DocumentsListResponse>('/api/v1/documents?scope=user')
    },

    /** GET /api/v1/documents?scope=user&enhanced=true — with requirements */
    getUserEnhancedDocuments() {
      return request<UserEnhancedDocumentsResponse>(
        '/api/v1/documents?scope=user&enhanced=true',
      )
    },

    /** GET /api/v1/documents?scope=company — company documents */
    getCompanyDocuments() {
      return request<DocumentsListResponse>('/api/v1/documents?scope=company')
    },

    /** GET /api/v1/applications/:id/documents — documents of an application */
    getApplicationDocuments(applicationId: UUID) {
      return request<ApplicationDocumentsResponse>(
        `/api/v1/applications/${applicationId}/documents`,
      )
    },

    /** GET /api/v1/applications/:id/documents?requested=true — LC-requested */
    getRequestedDocuments(applicationId: UUID) {
      return request<RequestedDocumentsResponse>(
        `/api/v1/applications/${applicationId}/documents?requested=true`,
      )
    },

    /** GET /api/v1/applications/:id/document-requests — grouped request history */
    getDocumentRequestHistory(applicationId: UUID) {
      return request<DocumentRequestHistoryResponse>(
        `/api/v1/applications/${applicationId}/document-requests`,
      )
    },

    // ---- Requirements -----------------------------------------------------

    /** POST /api/v1/documents/requirements — requirements for a set of LCs */
    getDocumentRequirements(leasingCompanyIds: UUID[]) {
      return request<DocumentRequirementsResponse>('/api/v1/documents/requirements', {
        method: 'POST',
        body: { leasing_company_ids: leasingCompanyIds },
      })
    },

    // ---- Upload (unified) -------------------------------------------------

    /**
     * POST /api/v1/documents — unified multipart upload.
     *
     * Handles single, multi, version (parentDocumentId), application-scope
     * (applicationId) and forced OCR (ocr=true) flows with a single endpoint.
     */
    uploadDocuments(files: File[] | FormData, options: UploadOptions = {}) {
      const body = files instanceof FormData ? files : buildUploadForm(files, options)
      return request<UploadDocumentsResponse>('/api/v1/documents', {
        method: 'POST',
        body,
        headers: options.idempotencyKey ? { 'Idempotency-Key': options.idempotencyKey } : undefined,
      })
    },

    /** Convenience: upload a single document with a document_type. */
    uploadDocument(file: File, documentType: string, applicationId?: UUID) {
      return this.uploadDocuments([file], { documentType, applicationId })
    },

    /** Submit a response; the server controls whether files are required for its type. */
    uploadRequestedDocument(
      files: File[],
      applicationId: UUID,
      documentRequestId: UUID,
      formData?: Record<string, unknown>,
      idempotencyKey?: string,
      userTitles?: string[],
    ) {
      return this.uploadDocuments(files, { applicationId, documentRequestId, formData, idempotencyKey, userTitles })
    },

    /** Convenience: upload a new version of an existing document. */
    uploadVersion(file: File, parentDocumentId: UUID) {
      return this.uploadDocuments([file], { parentDocumentId })
    },

    /** Convenience: multi-file upload with one shared document_type. */
    uploadMultiple(files: File[], documentType: string) {
      return this.uploadDocuments(files, { documentType })
    },

    /** Convenience: upload with forced DBRAIN OCR recognition. */
    processWithRecognition(files: File[], documentType: string, applicationId?: UUID) {
      return this.uploadDocuments(files, { documentType, applicationId, ocr: true })
    },

    // ---- Content (unified download / preview) ------------------------------

    /** GET /api/v1/documents/:id/content?disposition=inline — inline preview */
    previewDocument(documentId: UUID) {
      return request<Blob>(
        `/api/v1/documents/${documentId}/content?disposition=inline`,
        { responseType: 'blob' },
      )
    },

    /** GET /api/v1/documents/:id/content — attachment download (default) */
    downloadDocument(documentId: UUID) {
      return request<Blob>(
        `/api/v1/documents/${documentId}/content`,
        { responseType: 'blob' },
      )
    },

    /** Alias — some components call this via the old :id/download shape. */
    downloadDocumentAlt(documentId: UUID) {
      return this.downloadDocument(documentId)
    },

    /** GET /api/v1/applications/:id/documents/archive — ZIP of all docs */
    downloadApplicationArchive(applicationId: UUID) {
      return request<Blob>(
        `/api/v1/applications/${applicationId}/documents/archive`,
        { responseType: 'blob' },
      )
    },

    // ---- Versions ---------------------------------------------------------

    /** GET /api/v1/documents/:id/versions */
    getVersions(documentId: UUID) {
      return request<VersionsResponse>(`/api/v1/documents/${documentId}/versions`)
    },

    /** POST /api/v1/documents/:versionId/restore */
    restoreVersion(versionId: UUID) {
      return request<void>(`/api/v1/documents/${versionId}/restore`, {
        method: 'POST',
      })
    },

    // ---- Review -----------------------------------------------------------

    /** POST /api/v1/documents/:id/reviews — submit review (was leasing-review) */
    submitReview(documentId: UUID, body: ReviewBody) {
      return request<void>(`/api/v1/documents/${documentId}/reviews`, {
        method: 'POST',
        body,
      })
    },

    /** Backwards-compatible alias — kept so existing imports still resolve. */
    submitLeasingReview(documentId: UUID, body: ReviewBody) {
      return this.submitReview(documentId, body)
    },

    // ---- Status (PATCH) ---------------------------------------------------

    /** PATCH /api/v1/documents/:id/status */
    changeStatus(documentId: UUID, status: string, comments?: string) {
      return request<void>(`/api/v1/documents/${documentId}/status`, {
        method: 'PATCH',
        body: { status, comments },
      })
    },

    // ---- Delete -----------------------------------------------------------

    /** DELETE /api/v1/documents/:id — soft-delete */
    deleteDocument(documentId: UUID) {
      return request<void>(`/api/v1/documents/${documentId}`, {
        method: 'DELETE',
      })
    },
  }
}
