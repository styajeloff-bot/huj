import type { ApplicationSourceType } from '~/features/applications/sourceType'
// Re-export from API module
export type {
  LeasingCompany,
  LeasingApplication,
  DocumentRequirement as LeasingDocumentRequirement,
} from './api/leasingApi'

// --------------------------------------------------------------------------
// Component-level interfaces
// --------------------------------------------------------------------------

/** Application as displayed in LeasingApplicationsPanel */
export interface LeasingApplicationDisplay {
  id: string
  display_number?: string | null
  source_type?: ApplicationSourceType | null
  status: string
  parent_status?: string
  created_at: string
  submitted_at?: string | null
  updated_at?: string | null
  name?: string
  email?: string
  vehicles_count?: number
  vehicles_summary?: string
  attached_documents_count?: number
  total_amount?: number
  monthly_payment?: number
  down_payment_percent?: number
  lease_term_months?: number
  client_visible_comment?: string
  [key: string]: unknown
}

/** Status codes for leasing applications */
export type LeasingAppStatus =
  | 'submitted'
  | 'under_review'
  | 'under_review_with_docs'
  | 'approved_scoring'
  | 'approved_scoring_another_cond'
  | 'rejected_prescoring'
  | 'documents_required'
  | 'approved_final'
  | 'approved_final_another_cond'
  | 'rejected_approved'
  | 'selected_lc'
  | 'deal'
  | 'closed'

/** Pagination info returned by the applications endpoint */
export interface PaginationInfo {
  page: number
  limit: number
  total: number
  pages: number
}

/** Document requirement as edited in LeasingDocumentRequirementsPanel */
export interface DocumentRequirementEditable {
  id: number
  display_name: string
  sort_order: number
  description: string
  is_required: boolean
  is_mandatory: boolean
  auto_approve: boolean
  [key: string]: unknown
}

/** Leasing company card data */
export interface LeasingCompanyCard {
  id: number
  name: string
  average_down_payment_percent: number
  average_lease_term_months: number
  average_markup_percent: number
  min_down_payment_percent?: number
  max_lease_term_months?: number
  special_offers?: Record<string, unknown>
  [key: string]: unknown
}
