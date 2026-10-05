import type {
  PageLayout,
  PresetPreview,
  StorefrontPageDetail,
  StorefrontPageListItem,
  StorefrontPageRevision,
  StorefrontTemplate,
} from '../types'
import type { UUID } from '~/types/ids'
import type { AdminStorefront } from '~/features/admin/storefronts/api/storefrontsAdminApi'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export const createStorefrontBuilderApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    getStorefront: (storefrontId: UUID) =>
      request<AdminStorefront>(`/api/v1/admin/storefronts/${storefrontId}`),

    listPages: (storefrontId: UUID) =>
      request<{ items: StorefrontPageListItem[] }>(`/api/v1/admin/storefronts/${storefrontId}/pages`),

    getPage: (storefrontId: UUID, pageId: UUID) =>
      request<StorefrontPageDetail>(`/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}`),

    createPage: (
      storefrontId: UUID,
      body: { title: string; page_key: string; slug?: string; template_code?: string },
    ) =>
      request<StorefrontPageDetail>(`/api/v1/admin/storefronts/${storefrontId}/pages`, {
        method: 'POST',
        body,
      }),

    updatePageMetadata: (
      storefrontId: UUID,
      pageId: UUID,
      body: { title?: string; slug?: string },
    ) =>
      request<StorefrontPageDetail>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}`,
        {
          method: 'PATCH',
          body,
        },
      ),

    saveDraft: (
      storefrontId: UUID,
      pageId: UUID,
      body: { title?: string; expected_version: number; summary?: string; draft_layout: PageLayout },
    ) =>
      request<{ id: string; version: number; updated_at: string }>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/draft`,
        {
          method: 'PUT',
          body,
        },
      ),

    publishPage: (storefrontId: UUID, pageId: UUID, body: { expected_version: number }) =>
      request<{ status: 'published'; published_at: string; version: number }>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/publish`,
        {
          method: 'POST',
          body,
        },
      ),

    getRevisions: (storefrontId: UUID, pageId: UUID) =>
      request<StorefrontPageRevision[]>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/revisions`,
      ),

    restoreRevision: (
      storefrontId: UUID,
      pageId: UUID,
      revisionId: UUID,
      body: { expected_version: number },
    ) =>
      request<{ id: string; version: number; draft_layout: PageLayout }>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/revisions/${revisionId}/restore`,
        {
          method: 'POST',
          body,
        },
      ),

    uploadMedia: (storefrontId: UUID, file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return request<{ url: string; storage_key: string }>(
        `/api/v1/admin/storefronts/${storefrontId}/builder/media`,
        {
          method: 'POST',
          body: formData,
        },
      )
    },

    exportPresetUrl: (storefrontId: UUID, pageId: UUID) =>
      `${config.public.apiBase || ''}/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/export`,

    exportPresetData: (storefrontId: UUID, pageId: UUID) =>
      request<any>(`/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/export`),

    previewImportPreset: (storefrontId: UUID, body: any) =>
      request<PresetPreview>(`/api/v1/admin/storefronts/${storefrontId}/pages/import-preview`, {
        method: 'POST',
        body,
      }),

    importPreset: (
      storefrontId: UUID,
      pageId: UUID,
      body: { preset_data: any; expected_version: number; summary?: string },
    ) =>
      request<StorefrontPageDetail>(
        `/api/v1/admin/storefronts/${storefrontId}/pages/${pageId}/import`,
        {
          method: 'POST',
          body,
        },
      ),

    getTemplates: () =>
      request<StorefrontTemplate[]>('/api/v1/admin/storefront-templates').catch(() => []),
  }
}
