import type { UUID } from '~/types/ids'
import type {
  StorefrontAppearanceColors,
  StorefrontBorderRadius,
  StorefrontPublicPages,
  StorefrontPublicUi,
} from '~/features/storefront/types'

export type {
  StorefrontAppearanceColors,
  StorefrontBorderRadius,
  StorefrontPublicPageKey,
} from '~/features/storefront/types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export type AdminStorefrontPublicPages = StorefrontPublicPages
export type AdminStorefrontPublicUi = StorefrontPublicUi
export type StorefrontPublicUiWriteRequest = StorefrontPublicUi

export interface AdminStorefrontAppearance {
  colors: StorefrontAppearanceColors
  color_overrides?: Record<string, string>
  border_radius: StorefrontBorderRadius
  font_id: UUID | null
}

export interface StorefrontWarehouseOption {
  id: UUID
  address: string
  brand?: string | null
  city_name?: string | null
  is_active?: boolean
}

export interface AdminStorefront {
  id: UUID
  slug: string | null
  is_default: boolean
  is_active: boolean
  version: number
  contact_email: string | null
  contact_phone: string | null
  contact_phone_href?: string | null
  logo_url: string | null
  warehouse_ids: UUID[]
  warehouses?: StorefrontWarehouseOption[]
  effective_contact_email?: string | null
  effective_contact_phone?: string | null
  effective_contact_phone_href?: string | null
  effective_logo_url: string
  public_ui: AdminStorefrontPublicUi
  appearance: AdminStorefrontAppearance
  created_at?: string
  updated_at?: string
}

export interface AdminStorefrontList {
  items: AdminStorefront[]
}

export interface StorefrontSettingsPreview {
  items: { slug: string; action: 'create' | 'update'; warnings: string[] }[]
  preview_token: string
}

export interface StorefrontSettingsImportResult {
  created: string[]
  updated: string[]
}

export interface AdminStorefrontFont {
  id: UUID
  name: string
  description: string | null
  original_filename: string
  content_type: 'font/woff2'
  size_bytes: number
  checksum_sha256: string
  storefront_usage_count: number
  created_at: string
  updated_at: string
}

export interface AdminStorefrontFontList {
  items: AdminStorefrontFont[]
}

export interface StorefrontFontMetadataWriteRequest {
  name: string
  description: string | null
}

export interface StorefrontWriteRequest {
  slug?: string
  is_active?: boolean
  contact_email?: string | null
  contact_phone?: string | null
  warehouse_ids?: UUID[]
  public_ui?: StorefrontPublicUiWriteRequest
  appearance?: AdminStorefrontAppearance
}

export const createStorefrontsAdminApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    exportSettings: () => request<Blob>('/api/v1/admin/storefronts/settings/export', { responseType: 'blob' }),
    previewSettings: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return request<StorefrontSettingsPreview>('/api/v1/admin/storefronts/settings/preview', { method: 'POST', body })
    },
    importSettings: (file: File, previewToken: string) => {
      const body = new FormData()
      body.append('file', file)
      body.append('preview_token', previewToken)
      body.append('confirmed', 'true')
      return request<StorefrontSettingsImportResult>('/api/v1/admin/storefronts/settings/import', { method: 'POST', body })
    },
    list: () => request<AdminStorefrontList>('/api/v1/admin/storefronts'),
    listFonts: () => request<AdminStorefrontFontList>('/api/v1/admin/storefront-fonts'),
    create: (body: StorefrontWriteRequest) =>
      request<AdminStorefront>('/api/v1/admin/storefronts', { method: 'POST', body }),
    update: (id: UUID, body: StorefrontWriteRequest) =>
      request<AdminStorefront>(`/api/v1/admin/storefronts/${id}`, {
        method: 'PATCH',
        body,
      }),
    uploadLogo: (id: UUID, file: File) => {
      const body = new FormData()
      body.append('file', file)
      return request<AdminStorefront>(`/api/v1/admin/storefronts/${id}/logo`, {
        method: 'PUT',
        body,
      })
    },
    deleteLogo: (id: UUID) =>
      request<AdminStorefront>(`/api/v1/admin/storefronts/${id}/logo`, {
        method: 'DELETE',
      }),
    uploadFont: (file: File, metadata: StorefrontFontMetadataWriteRequest) => {
      const body = new FormData()
      body.append('file', file)
      body.append('name', metadata.name)
      if (metadata.description !== null) body.append('description', metadata.description)
      return request<AdminStorefrontFont>('/api/v1/admin/storefront-fonts', {
        method: 'POST',
        body,
      })
    },
    updateFont: (fontId: UUID, body: StorefrontFontMetadataWriteRequest) =>
      request<AdminStorefrontFont>(`/api/v1/admin/storefront-fonts/${fontId}`, {
        method: 'PATCH',
        body,
      }),
    removeFont: (fontId: UUID) =>
      request<void>(`/api/v1/admin/storefront-fonts/${fontId}`, {
        method: 'DELETE',
      }),
    listWarehouseOptions: () =>
      request<{ warehouses: StorefrontWarehouseOption[] }>(
        '/api/v1/admin/warehouses?status=active&limit=200',
      ),
  }
}
