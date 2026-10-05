import type { UUID } from '~/types/ids'

export type SpecialEquipmentImportMode = 'APPEND' | 'PATCH' | 'FULL_SNAPSHOT'
export type SpecialEquipmentImportStatus =
  | 'awaiting_upload'
  | 'uploaded'
  | 'validating_file'
  | 'validating_data'
  | 'transferring_images'
  | 'preview_ready'
  | 'validation_failed'
  | 'applying'
  | 'preview_stale'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'failed_retryable'
  | 'cancelled'

export interface SpecialEquipmentImportCounter {
  unit: 'bytes' | 'rows' | 'entities' | 'images' | 'issues' | string
  done: number
  total: number | null
}

export interface SpecialEquipmentImportSource {
  url: string
  partsUrl: string
  contentUrl: string | null
  completionUrl: string
  partSize: number
  maxParallelParts: number
  bytesReceived: number
  bytesTotal: number
  receivedParts: readonly number[]
  expiresAt: string | null
}

export interface SpecialEquipmentImportLinks {
  self: string
  preview: string
  issues: string
  report: string | null
  application: string
  cancellation: string
}

export interface SpecialEquipmentImportJob {
  id: UUID
  filename: string
  mode: SpecialEquipmentImportMode
  templateVersion: number
  status: SpecialEquipmentImportStatus
  phase: string
  counters: readonly SpecialEquipmentImportCounter[]
  summary: Record<string, unknown>
  source: SpecialEquipmentImportSource | null
  links: SpecialEquipmentImportLinks
  previewHash: string | null
  catalogRevision: number | null
  appliedRevision: number | null
  errorCode: string | null
  errorDetail: string | null
  canApply: boolean
  canCancel: boolean
  createdAt: string
  updatedAt: string
  uploadedAt: string | null
  previewedAt: string | null
  appliedAt: string | null
  targetWarehouseId: UUID | null
  targetWarehouse: SpecialEquipmentImportWarehouseAssignment | null
}

export interface SpecialEquipmentImportListResponse {
  items: SpecialEquipmentImportJob[]
  nextCursor: string | null
}

export interface SpecialEquipmentImportIssue {
  sequence: number
  sheetCode: string
  rowNumber: number | null
  columnName: string | null
  severity: 'error' | 'warning'
  code: string
  message: string
  rawValuePreview: string | null
  entityType: string | null
  entityCode: string | null
}

export interface SpecialEquipmentImportIssuesResponse {
  items: SpecialEquipmentImportIssue[]
  total: number
  stored: number
  truncated: boolean
  nextCursor: number | null
}

export interface SpecialEquipmentImportOperationCounts {
  create: number
  update: number
  archive: number
  remove: number
  noop: number
  rejected: number
}

export interface SpecialEquipmentImportChangeSample {
  entityType: string
  entityCode: string
  operation: string
  field: string | null
  before: string | number | boolean | null
  after: string | number | boolean | null
}

export interface SpecialEquipmentImportPreview {
  importId: UUID
  previewHash: string
  catalogRevision: number
  counts: Record<string, SpecialEquipmentImportOperationCounts>
  sheetRows: Record<string, number>
  changes: SpecialEquipmentImportChangeSample[]
  changesTotal: number
  changesStored: number
  changesTruncated: boolean
  commerceImpact: Record<string, number>
  imageSummary: Record<string, number>
  destructiveCount: number
  requiresDestructiveConfirmation: boolean
  destructivePercent: number
  blockingIssues: number
  warnings: number
  targetWarehouseId: UUID | null
  targetWarehouse: SpecialEquipmentImportWarehouseAssignment | null
}

export interface SpecialEquipmentImportCreateRequest {
  filename: string
  size: number
  mode: SpecialEquipmentImportMode
  templateVersion: 9
  target_warehouse_id?: UUID
}

export interface SpecialEquipmentImportWarehouse {
  id: UUID
  address: string
  city_name: string | null
  status: 'active' | 'inactive'
}

export interface SpecialEquipmentImportWarehouseAssignment {
  id: UUID
  address: string
  city_name: string | null
}

export interface SpecialEquipmentImportApplyRequest {
  confirmDestructiveChanges: boolean
}

export interface SpecialEquipmentImportProblem {
  type?: string
  title?: string
  status?: number
  detail?: string
  code?: string
}
