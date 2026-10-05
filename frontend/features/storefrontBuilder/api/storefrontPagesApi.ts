import type { UUID } from '~/types/ids'
import type {
  CreateStorefrontPagePayload,
  ImportPresetPayload,
  PageLayout,
  PublishPagePayload,
  PublicStorefrontPageResponse,
  SaveDraftPayload,
  StorefrontMediaUploadResponse,
  StorefrontPage,
  StorefrontPageListResponse,
  StorefrontPageRevisionListResponse,
  StorefrontPreset,
  StorefrontPresetPreviewResponse,
  StorefrontTemplateListResponse,
} from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createStorefrontPagesApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    // Admin API
    listPages: (storefrontId: UUID) =>
      request<StorefrontPageListResponse>(
        `/api/v1/admin/storefronts/${storefrontId}/pages`,
      ),

    getPage: (storefrontId: UUID, pageId: UUID) =>
      request<StorefrontPage>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}`,
      ),

    createPage: (storefrontId: UUID, payload: CreateStorefrontPagePayload) =>
      request<StorefrontPage>(`/api/v1/admin/storefronts/${storefrontId}/pages`, {
        method: 'POST',
        body: payload,
      }),

    saveDraft: (storefrontId: UUID, pageId: UUID, payload: SaveDraftPayload) =>
      request<{ version: number; updated_at: string }>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/draft`,
        {
          method: 'PUT',
          body: payload,
        },
      ),

    publishPage: (storefrontId: UUID, pageId: UUID, payload: PublishPagePayload) =>
      request<{ status: string; published_at: string; version: number }>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/publish`,
        {
          method: 'POST',
          body: payload,
        },
      ),

    listRevisions: (storefrontId: UUID, pageId: UUID) =>
      request<StorefrontPageRevisionListResponse>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/revisions`,
      ),

    restoreRevision: (storefrontId: UUID, pageId: UUID, revisionId: UUID) =>
      request<{ draft_layout: PageLayout; version: number }>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/revisions/${revisionId}/restore`,
        {
          method: 'POST',
        },
      ),

    listTemplates: () =>
      request<StorefrontTemplateListResponse>('/api/v1/admin/storefront-templates'),

    uploadMedia: (storefrontId: UUID, file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<StorefrontMediaUploadResponse>(
        `/api/v1/admin/storefronts/${storefrontId}/builder/media`,
        {
          method: 'POST',
          body: formData,
        },
      )
    },

    exportPreset: (storefrontId: UUID, pageId: UUID) =>
      request<StorefrontPreset>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/export`,
      ),

    previewPreset: (storefrontId: UUID, fileOrData: File | StorefrontPreset) => {
      if (typeof File !== 'undefined' && fileOrData instanceof File) {
        const formData = new FormData()
        formData.append('file', fileOrData)
        return request<StorefrontPresetPreviewResponse>(
          `/api/v1/admin/storefronts/${storefrontId}/pages/import-preview`,
          {
            method: 'POST',
            body: formData,
          },
        )
      }
      return request<StorefrontPresetPreviewResponse>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/import-preview`,
        {
          method: 'POST',
          body: fileOrData,
        },
      )
    },

    importPreset: (
      storefrontId: UUID,
      pageId: UUID,
      payload: ImportPresetPayload,
    ) =>
      request<{ version: number; updated_at: string }>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/import`,
        {
          method: 'POST',
          body: payload,
        },
      ),

    // Public API
    getPublicPage: (slug: string, pageKey: string) => {
      const path = slug
        ? `/api/v1/storefronts/${slug}/pages/${pageKey}`
        : `/api/v1/storefront/pages/${pageKey}`
      // Revalidate published layouts so reloads after publication do not use a stale palette.
      return request<PublicStorefrontPageResponse>(path, { cache: 'no-cache' })
    },
  }
}

export const useStorefrontPagesApi = () => {
  const config = useRuntimeConfig()
  return createStorefrontPagesApi(config)
}
