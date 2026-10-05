import type { UUID } from '~/types/ids'
import { createDefaultStorefrontAppearance } from '~/features/storefront/appearance'
import { createDefaultStorefrontPublicUi } from '~/features/storefront/publicUi'

export type StorefrontApiPath = (path: string) => string

export type StorefrontPublicPageKey =
  | 'home'
  | 'about'
  | 'special_equipment_catalog'


export interface StorefrontPublicPage {
  title: string
}

export interface StorefrontPublicPages {
  home: StorefrontPublicPage
  about: StorefrontPublicPage
  special_equipment_catalog: StorefrontPublicPage
}


export interface StorefrontPublicUi {
  home_page_key: StorefrontPublicPageKey
  pages: StorefrontPublicPages
}

export type StorefrontBorderRadius = 'none' | 'small' | 'medium' | 'large'

export interface StorefrontAppearanceColors {
  primary: string
  background: string
  surface: string
  text: string
}

export interface StorefrontFontDescriptor {
  id: UUID | null
  family: string
  url: string | null
}

export interface PublicStorefrontAppearance {
  colors: StorefrontAppearanceColors
  color_overrides?: Record<string, string>
  border_radius: StorefrontBorderRadius
  font: StorefrontFontDescriptor
}

export interface StorefrontBranding {
  contact_email: string
  contact_phone: string
  contact_phone_href: string
  logo_url: string
}

export interface PublicStorefront extends StorefrontBranding {
  id: UUID
  slug: string | null
  is_default: boolean
  is_active: boolean
  version: number
  appearance: PublicStorefrontAppearance
  public_ui: StorefrontPublicUi
}

export interface StorefrontContext extends StorefrontBranding {
  id: UUID | null
  slug: string | null
  is_default: boolean
  is_active: boolean
  version: number
  is_resolved: boolean
  appearance: PublicStorefrontAppearance
  public_ui: StorefrontPublicUi
}

export const createDefaultStorefrontContext = (): StorefrontContext => ({
  id: null,
  slug: null,
  is_default: true,
  is_active: true,
  version: 0,
  is_resolved: false,
  contact_email: 'info@multileasing.ru',
  contact_phone: '+7 (930) 999-03-65',
  contact_phone_href: '+79309990365',
  logo_url: '/images/logo.png',
  appearance: createDefaultStorefrontAppearance(),
  public_ui: createDefaultStorefrontPublicUi(),
})

export const DEFAULT_STOREFRONT_CONTEXT: StorefrontContext = createDefaultStorefrontContext()
