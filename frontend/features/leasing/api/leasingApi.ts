import type { ApplicationSourceType } from '~/features/applications/sourceType'
import type { useRuntimeConfig } from '#app'
import type { UUID } from '~/types/ids'
import { withLeasingCompanyContext } from '~/utils/leasingCompanyContext'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

// --- Interfaces ---

export interface LeasingCompany {
  id: UUID
  name: string
  [key: string]: unknown
}

export interface LeasingCompaniesResponse {
  companies: LeasingCompany[]
}

export interface DocumentRequirement {
  id?: UUID
  name: string
  required: boolean
  [key: string]: unknown
}

export interface DocumentRequirementsResponse {
  requirements: DocumentRequirement[]
}

export interface LeasingApplication {
  id: UUID
  display_number?: string | null
  source_type?: ApplicationSourceType | null
  status: string
  [key: string]: unknown
}

export interface LeasingApplicationsListResponse {
  applications: LeasingApplication[]
  pagination: {
    page: number
    limit: number
    total: number
    [key: string]: unknown
  }
}

export interface SuccessResponse {
  success: boolean
  message?: string
  [key: string]: unknown
}

export interface RequestedDocumentInput {
  source: 'catalog' | 'custom'
  display_name: string
  document_type?: string
}

export interface CreatedDocumentRequest {
  id: UUID
  display_name: string
  slug: string
  status: string
  requested_at: string | null
}

export interface RequestDocumentsResponse {
  success: boolean
  message: string
  application_id: UUID
  leasing_company_id: UUID | null
  request_batch_id: UUID
  requested_documents: string[]
  items: CreatedDocumentRequest[]
}

export interface ApproveApplicationDocumentResponse {
  application_id: UUID
  document_id: UUID
  leasing_company_id: UUID
  status: 'approved'
  message: string
}

// --- Response workflow types ---

export interface LeasingProposal {
  id: UUID
  leasing_company_application_id: UUID
  kind: 'preliminary' | 'final'
  position: number
  total_amount?: number | null
  down_payment?: number | null
  down_payment_percent?: number | null
  lease_term_months?: number | null
  monthly_payment?: number | null
  total_cost?: number | null
  markup?: number | null
  rate?: number | null
  total_interest?: number | null
  buyout_amount?: number | null
  vat_refund?: number | null
  profit_tax_savings?: number | null
  total_savings?: number | null
  client_decision_action?: string | null
  client_decision_at?: string | null
  client_decision_comment?: string | null
  pdf_file_name?: string | null
  pdf_size?: number | null
  pdf_uploaded_at?: string | null
}

export type ProposalParams = Omit<
  LeasingProposal,
  'id' | 'leasing_company_application_id' | 'kind' | 'position'
>

export interface LcResponseLink {
  id: UUID
  application_id: UUID
  leasing_company_id: UUID
  status: string
  display_status?: string | null
  decision_comment?: string | null
  response_pdf_file_name?: string | null
  response_pdf_size?: number | null
  response_pdf_uploaded_at?: string | null
  submitted_at?: string | null
}

export interface LcResponseState {
  link: LcResponseLink
  application: (Record<string, unknown> & { display_number?: string | null; source_type?: ApplicationSourceType | null }) | null
  proposals: LeasingProposal[]
  can_review: boolean
  can_confirm_deal: boolean
  confirm_deal_disabled_reason: string | null
}

export interface FinancialBundleResponse {
  application_id: UUID
  questionnaire: Record<string, unknown>
  accounting_report: Record<string, unknown> | null
}

export interface SubmitDecisionResponse {
  leasing_company_application_id: UUID
  leasing_company_id?: UUID | null
  leasing_company_name?: string | null
  application_id?: UUID | null
  decision: string
}

export interface ProposalDiffField {
  field: string
  requested: number | string | null
  offered: number | string | null
  changed: boolean
}

export interface ApprovalOfferLcaContext {
  id: UUID
  application_id: UUID
  leasing_company_id: UUID
  status: string
  decision_comment?: string | null
  response_pdf_s3_key?: string | null
  response_pdf_file_name?: string | null
  response_pdf_size?: number | null
  response_pdf_uploaded_at?: string | null
  submitted_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  [key: string]: unknown
}

export interface ApprovalOffer {
  lca: ApprovalOfferLcaContext
  leasing_company: { id: UUID | null; name: string | null; inn: string | null } | null
  proposal: LeasingProposal & { diff: ProposalDiffField[] }
}

export interface ClientLeasingResponse {
  leasing_company: { id: UUID; name: string | null; inn: string | null } | null
  decision: string | null
  decision_comment: string | null
  submitted_at: string | null
  response_pdf: {
    file_name: string | null
    file_size: number | null
    uploaded_at: string | null
  } | null
  proposals: (LeasingProposal & { diff: ProposalDiffField[] })[]
}

export interface ClientLeasingResponsesResponse {
  application_id: UUID
  requested: Record<string, number | string | null>
  responses: ClientLeasingResponse[]
  approval_offers: Record<'preliminary' | 'final', ApprovalOffer[]>
}

// --- Factory ---

export const createLeasingApi = (config: RuntimeConfig, leasingCompanyContext?: () => unknown) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) => {
    const target = withLeasingCompanyContext(url, leasingCompanyContext?.())
    return $fetch<T>(target, { baseURL: config.public.apiBase, credentials: 'include', ...options })
  }

  return {
    /** GET /api/v1/leasing/companies */
    getCompanies() {
      return request<LeasingCompaniesResponse>('/api/v1/leasing/companies')
    },

    /** GET /api/v1/leasing/document-requirements */
    getDocumentRequirements() {
      return request<DocumentRequirementsResponse>('/api/v1/leasing/document-requirements')
    },

    /** PUT /api/v1/leasing/document-requirements */
    updateDocumentRequirements(requirements: DocumentRequirement[]) {
      return request<SuccessResponse>('/api/v1/leasing/document-requirements', {
        method: 'PUT',
        body: { requirements },
      })
    },

    /** GET /api/v1/leasing/applications?page=&limit=&status= */
    getApplications(params: { page: number; limit: number; status?: string }) {
      const searchParams = new URLSearchParams({
        page: params.page.toString(),
        limit: params.limit.toString(),
      })
      if (params.status) searchParams.append('status', params.status)

      return request<LeasingApplicationsListResponse>(
        `/api/v1/leasing/applications?${searchParams.toString()}`,
      )
    },

    // --- Response workflow ---

    /** GET /api/v1/leasing/applications/:id/financial-bundle */
    getFinancialBundle(applicationId: UUID) {
      return request<FinancialBundleResponse>(
        `/api/v1/leasing/applications/${applicationId}/financial-bundle`,
      )
    },

    /** GET /api/v1/leasing/applications/:id/response */
    getResponseState(applicationId: UUID) {
      return request<LcResponseState>(
        `/api/v1/leasing/applications/${applicationId}/response`,
      )
    },

    /** PUT /api/v1/leasing/applications/:id/proposals/:kind — upsert by kind */
    upsertProposal(
      applicationId: UUID,
      kind: 'preliminary' | 'final',
      params: ProposalParams,
    ) {
      return request<LeasingProposal>(
        `/api/v1/leasing/applications/${applicationId}/proposals/${kind}`,
        { method: 'PUT', body: params },
      )
    },

    /** DELETE /api/v1/leasing/applications/:id/proposals/:kind */
    deleteProposal(applicationId: UUID, kind: 'preliminary' | 'final') {
      return request<void>(
        `/api/v1/leasing/applications/${applicationId}/proposals/${kind}`,
        { method: 'DELETE' },
      )
    },

    /** PUT /api/v1/leasing/applications/:id/request-documents */
    requestDocuments(
      applicationId: UUID,
      requestedDocuments: RequestedDocumentInput[],
      comments: string | null,
    ) {
      return request<RequestDocumentsResponse>(
        `/api/v1/leasing/applications/${applicationId}/request-documents`,
        {
          method: 'PUT',
          body: { requested_documents: requestedDocuments, comments },
        },
      )
    },

    /** PATCH /api/v1/leasing/applications/:id/documents/:documentId/status */
    approveApplicationDocument(applicationId: UUID, documentId: UUID) {
      return request<ApproveApplicationDocumentResponse>(
        `/api/v1/leasing/applications/${applicationId}/documents/${documentId}/status`,
        { method: 'PATCH', body: { status: 'approved' } },
      )
    },

    /** Direct download URL for the latest year's accounting PDF */
    accountingPdfUrl(applicationId: UUID): string {
      const base = config.public.apiBase ?? ''
      return `${base}${withLeasingCompanyContext(`/api/v1/leasing/applications/${applicationId}/accounting-pdf`, leasingCompanyContext?.())}`
    },

    /** POST /api/v1/leasing/applications/:id/proposals/:kind/pdf (multipart) */
    uploadProposalPdf(applicationId: UUID, kind: 'preliminary' | 'final', file: File) {
      const form = new FormData()
      form.append('file', file)
      return request<{ file_name: string; file_size: number; uploaded_at: string }>(
        `/api/v1/leasing/applications/${applicationId}/proposals/${kind}/pdf`,
        { method: 'POST', body: form },
      )
    },

    /** DELETE /api/v1/leasing/applications/:id/proposals/:kind/pdf */
    removeProposalPdf(applicationId: UUID, kind: 'preliminary' | 'final') {
      return request<void>(
        `/api/v1/leasing/applications/${applicationId}/proposals/${kind}/pdf`,
        { method: 'DELETE' },
      )
    },

    /** Secure inline PDF URL for a concrete proposal slot. */
    proposalPdfUrl(applicationId: UUID, kind: 'preliminary' | 'final'): string {
      const base = config.public.apiBase ?? ''
      return `${base}${withLeasingCompanyContext(`/api/v1/leasing/applications/${applicationId}/proposals/${kind}/pdf`, leasingCompanyContext?.())}`
    },

    /** PUT /api/v1/leasing/applications/:id/decision */
    submitDecision(
      applicationId: UUID,
      action: 'approve' | 'reject',
      decisionComment: string | null,
      kind: 'preliminary' | 'final' = 'final',
    ) {
      return request<SubmitDecisionResponse>(
        `/api/v1/leasing/applications/${applicationId}/decision`,
        {
          method: 'PUT',
          body: { action, decision_comment: decisionComment, kind },
        },
      )
    },

    /** POST /api/v1/leasing/applications/:id/take-in-work */
    takeInWork(applicationId: UUID) {
      return request<{
        application_id: UUID
        lca_id: UUID
        lca_status: string
        parent_status: string | null
        replayed: boolean
        message: string
      }>(
        `/api/v1/leasing/applications/${applicationId}/take-in-work`,
        { method: 'POST' },
      )
    },

    /** POST /api/v1/leasing/applications/:id/issue */
    issueApplication(applicationId: UUID) {
      return request<{ application_id: UUID; status: string; message: string }>(
        `/api/v1/leasing/applications/${applicationId}/issue`,
        { method: 'POST' },
      )
    },

    /** POST /api/v1/leasing/applications/:id/confirm-deal */
    confirmDeal(applicationId: UUID) {
      return request<{
        application_id: UUID
        leasing_company_application_id: UUID
        status: 'deal'
        message: string
        replayed: boolean
        special_equipment_orders: Array<Record<string, unknown>>
      }>(
        `/api/v1/leasing/applications/${applicationId}/confirm-deal`,
        { method: 'POST' },
      )
    },

    /** GET /api/v1/applications/:id/leasing-responses (client view) */
    getClientLeasingResponses(applicationId: UUID) {
      return request<ClientLeasingResponsesResponse>(
        `/api/v1/applications/${applicationId}/leasing-responses`,
      )
    },

    /** GET /api/v1/leasing/applications/:id/documents */
    getApplicationDocuments(applicationId: UUID) {
      return request<{ documents: Array<Record<string, unknown>> }>(
        `/api/v1/leasing/applications/${applicationId}/documents`,
      )
    },
  }
}
