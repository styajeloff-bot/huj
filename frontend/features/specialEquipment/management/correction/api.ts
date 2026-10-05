import type { UUID } from '~/types/ids'
import { resolveSpecialEquipmentApiBase } from '../../apiBase'
import type {
  CatalogActiveWarehouse,
  CatalogCategory,
  CatalogColor,
  CatalogColorApplicability,
  CatalogColorSelectItem,
  CatalogEntity,
  CatalogListResponse,
  CatalogModification,
  CatalogProduct,
  CatalogProductAttachmentInput,
  CatalogProductAttachmentLinksResponse,
  CatalogProductCreateRequest,
  CatalogResource,
  CatalogSellerCompany,
  CatalogSectionCountsResponse,
  CatalogTrimCreateResponse,
  CatalogTrimAttributeAssignment,
  CatalogTrimAttributeCreateResponse,
  CatalogTrimAttributeCandidatesResponse,
  CatalogTrimAttributesResponse,
  CatalogTrimListResponse,
  CatalogTrimAttributeValue,
  CatalogTrimAttributeValuesResponse,
  CatalogUnit,
  CatalogWarehouse,
  AttachmentSourceItem,
  CatalogSuperstructureAttributeCandidate,
  CascadePreviewResource,
  CascadeDeletePayload,
  CascadeDeleteResult,
} from './types'
import type { RegistryImage, RegistryMediaUploadResponse } from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

const API_ROOT = '/api/v1/admin/special-equipment'

export interface CatalogListQuery {
  search?: string
  page?: number
  page_size?: number
  mark_id?: UUID
  model_id?: UUID
  category_id?: UUID
  sale_status?: CatalogProduct['sale_status']
  attribute_group_id?: UUID
  level_1_id?: UUID
  level_2_id?: UUID
  level_3_id?: UUID
  level_4_id?: UUID
  level_5_id?: UUID
  sort?: 'updated_desc' | 'hierarchy'
  normalization_state?: 'normalized' | 'legacy' | 'conflict'
  role?: 'attachment' | 'component'
  modification_id?: UUID
  applicability?: CatalogColorApplicability
  is_active?: boolean
}

export interface CatalogColorSelectQuery {
  applicability: Exclude<CatalogColorApplicability, 'both'>
  search?: string
  limit?: number
}

export const createCatalogCorrectionApi = (config: RuntimeConfig) => {
  const baseURL = resolveSpecialEquipmentApiBase(config, import.meta.server)
  const forwardedAuthHeaders = import.meta.server
    ? useRequestHeaders(['cookie', 'authorization'])
    : {}
  const request = <T>(url: string, options: Record<string, unknown> = {}) => {
    const endpointHeaders = (options.headers ?? {}) as Record<string, string>
    return $fetch<T>(url, {
      baseURL,
      credentials: 'include',
      ...options,
      headers: { ...forwardedAuthHeaders, ...endpointHeaders },
    })
  }
  const conditionalRequest = async <T>(
    url: string,
    options: Record<string, unknown> = {},
  ): Promise<{ data: T; etag: string }> => {
    const endpointHeaders = (options.headers ?? {}) as Record<string, string>
    const response = await $fetch.raw<T>(url, {
      baseURL,
      credentials: 'include',
      ...options,
      headers: { ...forwardedAuthHeaders, ...endpointHeaders },
    })
    if (!response._data) throw new Error('Сервер вернул пустой ответ')
    return {
      data: response._data,
      etag: response.headers.get('etag') ?? '',
    }
  }
  const conditionalEmptyRequest = async (
    url: string,
    options: Record<string, unknown>,
  ): Promise<{ etag: string }> => {
    const endpointHeaders = (options.headers ?? {}) as Record<string, string>
    const response = await $fetch.raw<void>(url, {
      baseURL,
      credentials: 'include',
      ...options,
      headers: { ...forwardedAuthHeaders, ...endpointHeaders },
    })
    return { etag: response.headers.get('etag') ?? '' }
  }
  const collectionPath = (entity: CatalogEntity): string => `${API_ROOT}/${entity}`
  const itemPath = (entity: CatalogEntity, id: UUID): string =>
    `${collectionPath(entity)}/${encodeURIComponent(id)}`
  const listQuery = (entity: CatalogEntity, { search, ...query }: CatalogListQuery): Record<string, unknown> => ({
    ...query,
    ...(search ? { [entity === 'colors' ? 'search' : 'q']: search } : {}),
  })
  const list = <T extends CatalogResource>(
    entity: CatalogEntity,
    query: CatalogListQuery = {},
    signal?: AbortSignal,
  ) => request<CatalogListResponse<T>>(collectionPath(entity), {
    query: listQuery(entity, query),
    signal,
  })
  const listAll = async <T extends CatalogResource>(
    entity: CatalogEntity,
    query: Omit<CatalogListQuery, 'page' | 'page_size'> = {},
    signal?: AbortSignal,
  ): Promise<T[]> => {
    const items: T[] = []
    let page = 1
    let pages = 1
    while (page <= pages) {
      const response = await list<T>(entity, { ...query, page, page_size: 200 }, signal)
      items.push(...response.items)
      pages = response.pagination.pages
      page += 1
    }
    return items
  }
  const listWarehouses = async (signal?: AbortSignal): Promise<CatalogWarehouse[]> => {
    const items: CatalogWarehouse[] = []
    let page = 1
    let pages = 1
    while (page <= pages) {
      const response = await request<{
        warehouses: CatalogWarehouse[]
        pagination: { page: number; limit: number; total: number; pages: number }
      }>('/api/v1/admin/warehouses', { query: { page, limit: 200 }, signal })
      items.push(...response.warehouses)
      pages = response.pagination.pages
      page += 1
    }
    return items
  }

  return {
    getSectionCounts: (signal?: AbortSignal) =>
      request<CatalogSectionCountsResponse>(`${API_ROOT}/section-counts`, { signal }),

    listSellerCompanies: () =>
      request<{ items: CatalogSellerCompany[] }>(`${API_ROOT}/seller-companies`),

    listActiveWarehouses: async () => {
      const unique = new Map<UUID, CatalogActiveWarehouse>()
      let page = 1
      let pages = 1
      while (page <= pages) {
        const response = await request<{
          warehouses: CatalogActiveWarehouse[]
          pagination: { pages: number }
        }>('/api/v1/admin/warehouses', {
          query: { status: 'active', page, limit: 200 },
        })
        for (const warehouse of response.warehouses) {
          if (warehouse.status === 'active') unique.set(warehouse.id, warehouse)
        }
        pages = response.pagination.pages
        page += 1
      }
      return [...unique.values()]
    },

    list,
    listAll,
    listWarehouses,

    listColorOptions: (
      { applicability, search, limit = 50 }: CatalogColorSelectQuery,
      signal?: AbortSignal,
    ) => {
      const normalizedSearch = search?.trim()
      return request<{ items: CatalogColorSelectItem[] }>(`${API_ROOT}/colors/select`, {
        query: {
          applicability,
          ...(normalizedSearch ? { search: normalizedSearch } : {}),
          limit: Math.min(100, Math.max(1, Math.trunc(limit))),
        },
        signal,
      })
    },

    getColor: (id: UUID) => conditionalRequest<CatalogColor>(itemPath('colors', id)),

    createColor: (body: Record<string, unknown>, idempotencyKey: string) =>
      conditionalRequest<CatalogColor>(collectionPath('colors'), {
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': idempotencyKey },
      }),

    updateColor: (id: UUID, body: Record<string, unknown>, etag: string) =>
      conditionalRequest<CatalogColor>(itemPath('colors', id), {
        method: 'PATCH',
        body,
        headers: { 'If-Match': etag },
      }),

    deleteColor: (id: UUID, etag: string) =>
      request<void>(itemPath('colors', id), {
        method: 'DELETE',
        headers: { 'If-Match': etag },
      }),

    mergeUnit: (id: UUID, targetUnitId: UUID, etag: string, signal?: AbortSignal) =>
      request<CatalogUnit>(`${API_ROOT}/units/${encodeURIComponent(id)}/merge`, {
        method: 'POST',
        body: { target_unit_id: targetUnitId },
        headers: { 'If-Match': etag },
        signal,
      }),

    listAttachmentSources: (
      params: {
        model_id: UUID
        modification_id?: UUID | null
        search?: string
        exclude_product_id?: UUID | null
        limit?: number
      },
      signal?: AbortSignal,
    ) =>
      request<{ items: AttachmentSourceItem[] }>(`${API_ROOT}/products/attachment-sources`, {
        query: {
          model_id: params.model_id,
          ...(params.modification_id ? { modification_id: params.modification_id } : {}),
          ...(params.exclude_product_id ? { exclude_product_id: params.exclude_product_id } : {}),
          ...(params.search?.trim() ? { search: params.search.trim() } : {}),
          limit: Math.min(100, Math.max(1, Math.trunc(params.limit ?? 50))),
        },
        signal,
      }),

    listSuperstructureAttributeCandidates: (groupId: UUID, signal?: AbortSignal) =>
      request<{ items: CatalogSuperstructureAttributeCandidate[] }>(
        `${API_ROOT}/superstructures/attribute-candidates`,
        {
          query: { group_id: groupId },
          signal,
        },
      ),

    get: <T extends CatalogResource>(entity: CatalogEntity, id: UUID) =>
      conditionalRequest<T>(itemPath(entity, id)),

    create: <T extends CatalogResource>(
      entity: CatalogEntity,
      body: Record<string, unknown>,
      idempotencyKey: string,
    ) => conditionalRequest<T>(collectionPath(entity), {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    }),

    createTrim: (
      body: { modification_id: UUID; name: string },
      idempotencyKey: string,
    ) => request<CatalogTrimCreateResponse>(collectionPath('trims'), {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    }),

    createProduct: (
      body: CatalogProductCreateRequest,
      idempotencyKey: string,
    ) => conditionalRequest<CatalogProduct>(collectionPath('products'), {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
    }),


    update: <T extends CatalogResource>(
      entity: CatalogEntity,
      id: UUID,
      body: Record<string, unknown>,
      etag: string,
    ) => conditionalRequest<T>(itemPath(entity, id), {
      method: 'PATCH',
      body,
      // Preserve the exact raw strong ETag from the response; do not quote,
      // trim, parse, or synthesize it before sending If-Match.
      headers: { 'If-Match': etag },
    }),

    remove: (entity: CatalogEntity, id: UUID, etag: string) =>
      request<void>(itemPath(entity, id), {
        method: 'DELETE',
        headers: { 'If-Match': etag },
      }),

    replaceCategoryParents: (categoryId: UUID, parentIds: UUID[], etag: string) =>
      conditionalRequest<CatalogCategory>(`${itemPath('categories', categoryId)}/parents`, {
        method: 'PUT',
        body: { parent_ids: parentIds },
        headers: { 'If-Match': etag },
      }),

    getModification: (modificationId: UUID) =>
      conditionalRequest<CatalogModification>(itemPath('modifications', modificationId)),

    getTrimsByModification: async (modificationId: UUID, signal?: AbortSignal) => {
      const response = await request<CatalogTrimListResponse>(
        collectionPath('trims'),
        { query: { modification_id: modificationId }, signal },
      )
      const items = response.items.filter(item => item.is_active)
      return {
        items,
        allItems: response.items,
        required: items.length > 0,
      }
    },

    getTrimAttributeCandidatesByModification: (
      modificationId: UUID,
      signal?: AbortSignal,
    ) => request<CatalogTrimAttributeCandidatesResponse>(
      `${itemPath('modifications', modificationId)}/trim-attribute-candidates`,
      { signal },
    ),

    getTrimAttributeCandidates: (trimId: UUID, signal?: AbortSignal) =>
      request<CatalogTrimAttributeCandidatesResponse>(
        `${itemPath('trims', trimId)}/attribute-candidates`,
        { signal },
      ),

    getTrimAttributes: (trimId: UUID) =>
      conditionalRequest<CatalogTrimAttributesResponse>(`${itemPath('trims', trimId)}/attributes`),

    addTrimAttribute: (
      trimId: UUID,
      item: CatalogTrimAttributeAssignment,
      etag: string,
    ) => conditionalRequest<CatalogTrimAttributeCreateResponse>(`${itemPath('trims', trimId)}/attributes`, {
      method: 'POST',
      body: {
        attribute_id: item.attribute_id,
        group_id: item.group_id,
        is_required: item.is_required,
        is_filterable: item.is_filterable,
        sort_order: item.sort_order,
      },
      headers: { 'If-Match': etag },
    }),

    deleteTrimAttribute: (trimId: UUID, attributeId: UUID, etag: string) =>
      conditionalEmptyRequest(
        `${itemPath('trims', trimId)}/attributes/${encodeURIComponent(attributeId)}`,
        { method: 'DELETE', headers: { 'If-Match': etag } },
      ),

    patchTrimAttributeValues: (
      trimId: UUID,
      values: CatalogTrimAttributeValue[],
      etag: string,
    ) => conditionalRequest<CatalogTrimAttributeValuesResponse>(`${itemPath('trims', trimId)}/attribute-values`, {
      method: 'PUT',
      body: { values },
      headers: { 'If-Match': etag },
    }),

    uploadCategoryImage: (categoryId: UUID, file: File, etag: string) => {
      const body = new FormData()
      body.append('file', file)
      return conditionalRequest<RegistryMediaUploadResponse>(
        `${itemPath('categories', categoryId)}/image`,
        { method: 'PUT', body, headers: { 'If-Match': etag } },
      )
    },
    deleteCategoryImage: (categoryId: UUID, etag: string) =>
      conditionalEmptyRequest(`${itemPath('categories', categoryId)}/image`, {
        method: 'DELETE',
        headers: { 'If-Match': etag },
      }),

    uploadProductImage: (productId: UUID, file: File, etag: string) => {
      const body = new FormData()
      body.append('file', file)
      return conditionalRequest<RegistryMediaUploadResponse>(
        `${itemPath('products', productId)}/images`,
        { method: 'POST', body, headers: { 'If-Match': etag } },
      )
    },

    updateProductImage: (
      productId: UUID,
      imageId: UUID,
      body: { alt_text?: string | null; is_primary?: boolean; sort_order?: number },
      etag: string,
    ) => conditionalRequest<RegistryImage>(
      `${itemPath('products', productId)}/images/${encodeURIComponent(imageId)}`,
      { method: 'PATCH', body, headers: { 'If-Match': etag } },
    ),

    deleteProductImage: (productId: UUID, imageId: UUID, etag: string) =>
      conditionalEmptyRequest(
        `${itemPath('products', productId)}/images/${encodeURIComponent(imageId)}`,
        { method: 'DELETE', headers: { 'If-Match': etag } },
      ),

    getProductAttachments: (productId: UUID) =>
      conditionalRequest<CatalogProductAttachmentLinksResponse>(
        `${itemPath('products', productId)}/compatible-attachments`,
      ),

    replaceProductAttachments: (
      productId: UUID,
      items: CatalogProductAttachmentInput[],
      etag: string,
    ) => conditionalRequest<CatalogProductAttachmentLinksResponse>(
      `${itemPath('products', productId)}/compatible-attachments`,
      {
        method: 'PUT',
        body: { items },
        headers: { 'If-Match': etag },
      },
    ),



    getDeletePreview: async (resource: string, id: string, signal?: AbortSignal): Promise<CascadePreviewResource> => {
      const primaryUrl = `/api/v1/special-equipment/management/${encodeURIComponent(resource)}/${encodeURIComponent(id)}/delete-preview`
      try {
        return await request<CascadePreviewResource>(primaryUrl, { signal })
      } catch (err: unknown) {
        if (
          (err as { status?: number; response?: { status?: number } })?.status === 404 ||
          (err as { status?: number; response?: { status?: number } })?.response?.status === 404
        ) {
          const fallbackUrl = `${itemPath(resource as CatalogEntity, id)}/delete-preview`
          return await request<CascadePreviewResource>(fallbackUrl, { signal })
        }
        throw err
      }
    },

    cascadeDelete: async (
      resource: string,
      id: string,
      payload: CascadeDeletePayload,
      etag?: string,
      signal?: AbortSignal,
    ): Promise<CascadeDeleteResult> => {
      const primaryUrl = `/api/v1/special-equipment/management/${encodeURIComponent(resource)}/${encodeURIComponent(id)}/cascade-delete`
      const headers = etag ? { 'If-Match': etag } : undefined
      try {
        return await request<CascadeDeleteResult>(primaryUrl, {
          method: 'POST',
          body: payload,
          headers,
          signal,
        })
      } catch (err: unknown) {
        if (
          (err as { status?: number; response?: { status?: number } })?.status === 404 ||
          (err as { status?: number; response?: { status?: number } })?.response?.status === 404
        ) {
          const fallbackUrl = `${itemPath(resource as CatalogEntity, id)}/cascade-delete`
          return await request<CascadeDeleteResult>(fallbackUrl, {
            method: 'POST',
            body: payload,
            headers,
            signal,
          })
        }
        throw err
      }
    },
  }
}

export type CatalogCorrectionApi = ReturnType<typeof createCatalogCorrectionApi>

export const getDeletePreview = async (
  resource: string,
  id: string,
  signal?: AbortSignal,
): Promise<CascadePreviewResource> => {
  const primaryUrl = `/api/v1/special-equipment/management/${encodeURIComponent(resource)}/${encodeURIComponent(id)}/delete-preview`
  try {
    return await $fetch<CascadePreviewResource>(primaryUrl, { credentials: 'include', signal })
  } catch (err: unknown) {
    if (
      (err as { status?: number; response?: { status?: number } })?.status === 404 ||
      (err as { status?: number; response?: { status?: number } })?.response?.status === 404
    ) {
      return await $fetch<CascadePreviewResource>(
        `/api/v1/admin/special-equipment/${encodeURIComponent(resource)}/${encodeURIComponent(id)}/delete-preview`,
        { credentials: 'include', signal },
      )
    }
    throw err
  }
}

export const cascadeDelete = async (
  resource: string,
  id: string,
  payload: CascadeDeletePayload,
  etag?: string,
  signal?: AbortSignal,
): Promise<CascadeDeleteResult> => {
  const primaryUrl = `/api/v1/special-equipment/management/${encodeURIComponent(resource)}/${encodeURIComponent(id)}/cascade-delete`
  const headers = etag ? { 'If-Match': etag } : undefined
  try {
    return await $fetch<CascadeDeleteResult>(primaryUrl, {
      method: 'POST',
      credentials: 'include',
      body: payload,
      headers,
      signal,
    })
  } catch (err: unknown) {
    if (
      (err as { status?: number; response?: { status?: number } })?.status === 404 ||
      (err as { status?: number; response?: { status?: number } })?.response?.status === 404
    ) {
      return await $fetch<CascadeDeleteResult>(
        `/api/v1/admin/special-equipment/${encodeURIComponent(resource)}/${encodeURIComponent(id)}/cascade-delete`,
        {
          method: 'POST',
          credentials: 'include',
          body: payload,
          headers,
          signal,
        },
      )
    }
    throw err
  }
}

export const specialEquipmentCorrectionApi = {
  getDeletePreview,
  cascadeDelete,
}

