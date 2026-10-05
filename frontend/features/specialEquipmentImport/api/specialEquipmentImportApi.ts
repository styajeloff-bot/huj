import { isUuid, type UUID } from '~/types/ids'
import type {
  SpecialEquipmentImportApplyRequest,
  SpecialEquipmentImportChangeSample,
  SpecialEquipmentImportCounter,
  SpecialEquipmentImportCreateRequest,
  SpecialEquipmentImportIssue,
  SpecialEquipmentImportIssuesResponse,
  SpecialEquipmentImportJob,
  SpecialEquipmentImportLinks,
  SpecialEquipmentImportListResponse,
  SpecialEquipmentImportMode,
  SpecialEquipmentImportOperationCounts,
  SpecialEquipmentImportPreview,
  SpecialEquipmentImportSource,
  SpecialEquipmentImportStatus,
  SpecialEquipmentImportWarehouse,
  SpecialEquipmentImportWarehouseAssignment,
} from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>
type UnknownRecord = Record<string, unknown>

export interface ConditionalImportResponse<T> {
  data: T
  etag: string | null
  retryAfterSeconds: number | null
  notModified: boolean
}

const record = (value: unknown): UnknownRecord => value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
const stringValue = (value: unknown, fallback = ''): string => typeof value === 'string' ? value : fallback
const nullableString = (value: unknown): string | null => typeof value === 'string' && value.length > 0 ? value : null
const nullableUuid = (value: unknown): UUID | null => typeof value === 'string' && isUuid(value) ? value : null
const numberValue = (value: unknown, fallback = 0): number => typeof value === 'number' && Number.isFinite(value) ? value : fallback
const nullableNumber = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null
const booleanValue = (value: unknown, fallback = false): boolean => typeof value === 'boolean' ? value : fallback
const arrayValue = (value: unknown): unknown[] => Array.isArray(value) ? value : []
const field = (value: UnknownRecord, camel: string, snake: string = camel): unknown => value[camel] ?? value[snake]

const IMPORT_STATUSES = new Set<SpecialEquipmentImportStatus>([
  'awaiting_upload', 'uploaded', 'validating_file', 'validating_data', 'transferring_images',
  'preview_ready', 'validation_failed', 'applying', 'preview_stale', 'completed',
  'completed_with_warnings', 'failed', 'failed_retryable', 'cancelled',
])

const importStatus = (value: unknown): SpecialEquipmentImportStatus => {
  const candidate = stringValue(value) as SpecialEquipmentImportStatus
  return IMPORT_STATUSES.has(candidate) ? candidate : 'failed'
}
const importMode = (value: unknown): SpecialEquipmentImportMode => {
  const candidate = stringValue(value)
  return candidate === 'APPEND' || candidate === 'FULL_SNAPSHOT' ? candidate : 'PATCH'
}
const normalizeCounter = (value: unknown): SpecialEquipmentImportCounter => {
  const data = record(value)
  return {
    unit: stringValue(data.unit),
    done: numberValue(data.done),
    total: data.total === null ? null : nullableNumber(data.total),
  }
}

const normalizeWarehouse = (value: unknown): SpecialEquipmentImportWarehouseAssignment | null => {
  const data = record(value)
  const id = nullableUuid(data.id)
  const address = nullableString(data.address)
  return id && address
    ? { id, address, city_name: nullableString(field(data, 'cityName', 'city_name')) }
    : null
}

const normalizeSource = (value: unknown): SpecialEquipmentImportSource | null => {
  const data = record(value)
  if (Object.keys(data).length === 0) return null
  return {
    url: stringValue(data.url),
    partsUrl: stringValue(field(data, 'partsUrl', 'parts_url')),
    contentUrl: nullableString(field(data, 'contentUrl', 'content_url')),
    completionUrl: stringValue(field(data, 'completionUrl', 'completion_url')),
    partSize: numberValue(field(data, 'partSize', 'part_size'), 16 * 1024 * 1024),
    maxParallelParts: numberValue(field(data, 'maxParallelParts', 'max_parallel_parts'), 3),
    bytesReceived: numberValue(field(data, 'bytesReceived', 'bytes_received')),
    bytesTotal: numberValue(field(data, 'bytesTotal', 'bytes_total')),
    receivedParts: arrayValue(field(data, 'receivedParts', 'received_parts')).filter((part): part is number => typeof part === 'number' && Number.isInteger(part) && part > 0),
    expiresAt: nullableString(field(data, 'expiresAt', 'expires_at')),
  }
}

const normalizeLinks = (value: unknown, importId: UUID): SpecialEquipmentImportLinks => {
  const data = record(value)
  const base = `/api/v1/special-equipment/imports/${encodeURIComponent(importId)}`
  return {
    self: stringValue(data.self, base),
    preview: stringValue(data.preview, `${base}/preview`),
    issues: stringValue(data.issues, `${base}/issues`),
    report: nullableString(data.report ?? data.validation_report),
    application: stringValue(data.application, `${base}/application`),
    cancellation: stringValue(data.cancellation, `${base}/cancellation`),
  }
}

export const normalizeImportJob = (value: unknown): SpecialEquipmentImportJob => {
  const data = record(value)
  const rawId = stringValue(data.id)
  if (!isUuid(rawId)) throw new Error('Import API returned an invalid UUID')
  const countersValue = arrayValue(data.counters)
  const progress = record(data.progress)
  const counters = countersValue.length > 0
    ? countersValue.map(normalizeCounter)
    : Object.entries(progress).map(([unit, raw]) => {
        const counter = record(raw)
        return { unit, done: numberValue(counter.done), total: counter.total === null ? null : nullableNumber(counter.total) }
      })
  const error = record(data.error)
  const normalizedCounters = counters.length > 0 ? counters : [
        { unit: 'bytes', done: numberValue(field(data, 'bytesReceived', 'actual_size_bytes')), total: nullableNumber(field(data, 'bytesTotal', 'expected_size_bytes')) },
        { unit: 'rows', done: numberValue(field(data, 'rowsDone', 'rows_done')), total: nullableNumber(field(data, 'rowsTotal', 'rows_total')) },
        { unit: 'entities', done: numberValue(field(data, 'entitiesDone', 'entities_done')), total: nullableNumber(field(data, 'entitiesTotal', 'entities_total')) },
        { unit: 'images', done: numberValue(field(data, 'imagesDone', 'images_done')), total: nullableNumber(field(data, 'imagesTotal', 'images_total')) },
        { unit: 'issues', done: numberValue(field(data, 'issuesTotal', 'issues_total')), total: numberValue(field(data, 'issuesTotal', 'issues_total')) },
      ]
  const status = importStatus(data.status)
  return {
    id: rawId,
    filename: stringValue(field(data, 'filename', 'original_filename')),
    mode: importMode(data.mode),
    templateVersion: numberValue(field(data, 'templateVersion', 'template_version'), 9),
    status,
    phase: stringValue(data.phase, status),
    counters: normalizedCounters,
    summary: record(data.summary),
    source: normalizeSource(data.source),
    links: normalizeLinks(data.links, rawId),
    previewHash: nullableString(field(data, 'previewHash', 'preview_hash')),
    catalogRevision: nullableNumber(field(data, 'catalogRevision', 'catalog_revision')),
    appliedRevision: nullableNumber(field(data, 'appliedRevision', 'applied_revision')),
    errorCode: nullableString(field(data, 'errorCode', 'error_code')) ?? nullableString(error.code),
    errorDetail: nullableString(field(data, 'errorDetail', 'error_detail')) ?? nullableString(error.detail),
    canApply: booleanValue(field(data, 'canApply', 'can_apply'), status === 'preview_ready'),
    canCancel: booleanValue(field(data, 'canCancel', 'can_cancel'), !['completed', 'completed_with_warnings', 'cancelled'].includes(status)),
    createdAt: stringValue(field(data, 'createdAt', 'created_at')),
    updatedAt: stringValue(field(data, 'updatedAt', 'updated_at')),
    uploadedAt: nullableString(field(data, 'uploadedAt', 'uploaded_at')),
    previewedAt: nullableString(field(data, 'previewedAt', 'previewed_at')),
    appliedAt: nullableString(field(data, 'appliedAt', 'applied_at')),
    targetWarehouseId: nullableUuid(field(data, 'targetWarehouseId', 'target_warehouse_id')),
    targetWarehouse: normalizeWarehouse(field(data, 'targetWarehouse', 'target_warehouse')),
  }
}

const normalizeCounts = (value: unknown): Record<string, SpecialEquipmentImportOperationCounts> => Object.fromEntries(
  Object.entries(record(value)).map(([key, raw]) => {
    const data = record(raw)
    return [key, {
      create: numberValue(data.create), update: numberValue(data.update), archive: numberValue(data.archive),
      remove: numberValue(data.remove), noop: numberValue(data.noop), rejected: numberValue(data.rejected),
    }]
  }),
)

const normalizeStringNumberRecord = (value: unknown): Record<string, number> => Object.fromEntries(
  Object.entries(record(value)).map(([key, raw]) => [key, numberValue(raw)]),
)

const normalizeChange = (value: unknown): SpecialEquipmentImportChangeSample => {
  const data = record(value)
  const scalar = (raw: unknown): string | number | boolean | null => typeof raw === 'string' || typeof raw === 'number' || typeof raw === 'boolean' ? raw : null
  return {
    entityType: stringValue(field(data, 'entityType', 'entity_type')),
    entityCode: stringValue(field(data, 'entityCode', 'entity_code')),
    operation: stringValue(data.operation),
    field: nullableString(data.field),
    before: scalar(data.before),
    after: scalar(data.after),
  }
}

const normalizePreview = (value: unknown, fallbackId: UUID): SpecialEquipmentImportPreview => {
  const data = record(value)
  const summary = record(data.summary)
  const actions = record(summary.actions)
  const explicitCounts = record(data.counts ?? field(summary, 'operationCounts', 'operation_counts'))
  const rawId = stringValue(field(data, 'importId', 'import_id'), fallbackId)
  return {
    importId: isUuid(rawId) ? rawId : fallbackId,
    previewHash: stringValue(field(data, 'previewHash', 'preview_hash')),
    catalogRevision: numberValue(field(data, 'catalogRevision', 'catalog_revision')),
    counts: Object.keys(explicitCounts).length > 0 ? normalizeCounts(explicitCounts) : Object.keys(actions).length > 0 ? { catalog: {
      create: numberValue(actions.add) + numberValue(actions.upsert),
      update: numberValue(actions.update) + numberValue(actions.set), archive: numberValue(actions.archive),
      remove: numberValue(actions.delete) + numberValue(actions.clear), noop: numberValue(actions.noop), rejected: numberValue(summary.rejectedRows),
    } } : normalizeCounts(data.counts ?? data.operations),
    sheetRows: normalizeStringNumberRecord(summary.rows ?? field(data, 'sheetRows', 'sheet_rows')),
    changes: arrayValue(data.changes ?? data.samples).map(normalizeChange),
    changesTotal: numberValue(field(data, 'changesTotal', 'changes_total'), numberValue(summary.changesTotal)),
    changesStored: numberValue(field(data, 'changesStored', 'changes_stored'), numberValue(summary.changesStored)),
    changesTruncated: booleanValue(field(data, 'changesTruncated', 'changes_truncated'), booleanValue(summary.changesTruncated)),
    commerceImpact: normalizeStringNumberRecord(field(data, 'commerceImpact', 'commerce_impact')),
    imageSummary: normalizeStringNumberRecord(field(data, 'imageSummary', 'image_summary')),
    destructiveCount: numberValue(summary.destructiveCount, numberValue(field(data, 'destructiveCount', 'destructive_count'))),
    requiresDestructiveConfirmation: booleanValue(
      summary.requiresDestructiveConfirmation,
      booleanValue(field(data, 'requiresDestructiveConfirmation', 'requires_destructive_confirmation')),
    ),
    destructivePercent: numberValue(field(data, 'destructivePercent', 'destructive_percent'), numberValue(summary.destructivePercent)),
    blockingIssues: numberValue(field(data, 'blockingIssues', 'blocking_issues'), numberValue(summary.errors)),
    warnings: numberValue(data.warnings, numberValue(summary.warnings)),
    targetWarehouseId: nullableUuid(field(data, 'targetWarehouseId', 'target_warehouse_id')),
    targetWarehouse: normalizeWarehouse(field(data, 'targetWarehouse', 'target_warehouse')),
  }
}

const normalizeIssue = (value: unknown): SpecialEquipmentImportIssue => {
  const data = record(value)
  return {
    sequence: numberValue(data.sequence),
    sheetCode: stringValue(field(data, 'sheetCode', 'sheet_code')),
    rowNumber: nullableNumber(field(data, 'rowNumber', 'row_number')),
    columnName: nullableString(field(data, 'columnName', 'column_name')),
    severity: data.severity === 'warning' ? 'warning' : 'error',
    code: stringValue(data.code),
    message: stringValue(data.message),
    rawValuePreview: nullableString(field(data, 'rawValuePreview', 'raw_value_preview')),
    entityType: nullableString(field(data, 'entityType', 'entity_type')),
    entityCode: nullableString(field(data, 'entityCode', 'entity_code')),
  }
}

export const createSpecialEquipmentImportApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) => $fetch<T>(url, {
    baseURL: config.public.apiBase,
    credentials: 'include',
    ...options,
  })

  return {
    templateContentUrl: '/api/v1/special-equipment/import-templates/v9/content',

    createImport: async (body: SpecialEquipmentImportCreateRequest, idempotencyKey: string) => normalizeImportJob(await request<unknown>(
      '/api/v1/special-equipment/imports',
      { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: { ...body, target_warehouse_id: body.target_warehouse_id } },
    )),

    listActiveWarehouses: async (): Promise<SpecialEquipmentImportWarehouse[]> => {
      const unique = new Map<UUID, SpecialEquipmentImportWarehouse>()
      let page = 1
      let pages = 1
      while (page <= pages) {
        const response = record(await request<unknown>('/api/v1/admin/warehouses', {
          query: { status: 'active', page, limit: 200 },
        }))
        const pagination = record(response.pagination)
        for (const warehouse of arrayValue(response.warehouses)) {
          const data = record(warehouse)
          const id = nullableUuid(data.id)
          if (id && data.status === 'active') unique.set(id, {
            id,
            address: stringValue(data.address),
            city_name: nullableString(data.city_name),
            status: 'active',
          })
        }
        pages = numberValue(pagination.pages, page)
        page += 1
      }
      return [...unique.values()]
    },

    listImports: async (params: { cursor?: string; limit?: number } = {}): Promise<SpecialEquipmentImportListResponse> => {
      const raw = record(await request<unknown>('/api/v1/special-equipment/imports', { query: params }))
      const pagination = record(raw.pagination)
      return {
        items: arrayValue(raw.items).map(normalizeImportJob),
        nextCursor: nullableString(field(pagination, 'nextCursor', 'next_cursor')),
      }
    },

    getImport: async (importId: UUID, etag?: string): Promise<ConditionalImportResponse<SpecialEquipmentImportJob>> => {
      const response = await $fetch.raw<unknown>(`/api/v1/special-equipment/imports/${encodeURIComponent(importId)}`, {
        baseURL: config.public.apiBase,
        credentials: 'include',
        headers: etag ? { 'If-None-Match': etag } : undefined,
        ignoreResponseError: true,
      })
      const responseEtag = response.headers.get('etag')
      const retryRaw = response.headers.get('retry-after')
      const retryAfterSeconds = retryRaw && /^\d+$/.test(retryRaw) ? Number(retryRaw) : null
      if (response.status === 304) {
        return { data: {} as SpecialEquipmentImportJob, etag: responseEtag ?? etag ?? null, retryAfterSeconds, notModified: true }
      }
      if (response.status >= 400) throw response._data
      return { data: normalizeImportJob(response._data), etag: responseEtag, retryAfterSeconds, notModified: false }
    },

    getSource: async (importId: UUID): Promise<SpecialEquipmentImportSource> => {
      const raw = await request<unknown>(`/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/source`)
      const source = normalizeSource(record(raw).source ?? raw)
      if (!source) throw new Error('Import source is unavailable')
      return source
    },

    putPart: (importId: UUID, partNumber: number, body: Blob, headers: Record<string, string>, signal: AbortSignal) => request<unknown>(
      `/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/source/parts/${partNumber}`,
      { method: 'PUT', headers, body, signal },
    ),

    completeSource: (importId: UUID) => request<unknown>(
      `/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/source/completion`,
      { method: 'PUT', body: {} },
    ),

    getPreview: async (importId: UUID): Promise<SpecialEquipmentImportPreview> => normalizePreview(
      await request<unknown>(`/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/preview`),
      importId,
    ),

    getIssues: async (importId: UUID, params: { severity?: 'error' | 'warning'; sheet?: string; cursor?: number; limit?: number }): Promise<SpecialEquipmentImportIssuesResponse> => {
      const raw = record(await request<unknown>(`/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/issues`, { query: { severity: params.severity, sheet_code: params.sheet, afterSequence: params.cursor, limit: params.limit } }))
      const pagination = record(raw.pagination)
      return {
        items: arrayValue(raw.items).map(normalizeIssue),
        total: numberValue(raw.total, arrayValue(raw.items).length),
        stored: numberValue(raw.stored, arrayValue(raw.items).length),
        truncated: booleanValue(raw.truncated),
        nextCursor: nullableNumber(field(pagination, 'nextSequence', 'next_sequence')),
      }
    },

    applyImport: async (importId: UUID, previewHash: string, body: SpecialEquipmentImportApplyRequest) => normalizeImportJob(await request<unknown>(
      `/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/application`,
      { method: 'PUT', headers: { 'If-Match': `"${previewHash}"` }, body },
    )),

    cancelImport: async (importId: UUID) => normalizeImportJob(await request<unknown>(
      `/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/cancellation`,
      { method: 'PUT', body: {} },
    )),

    sourceContentUrl: (importId: UUID) => `/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/source/content`,
    reportContentUrl: (importId: UUID) => `/api/v1/special-equipment/imports/${encodeURIComponent(importId)}/validation-report/content`,
  }
}
