import type { PublicStorefrontAppearance } from '~/features/storefront/types'

export const DEFAULT_STOREFRONT_APPEARANCE: Readonly<PublicStorefrontAppearance> = {
  colors: {
    primary: '#3367BD',
    background: '#F9FAFB',
    surface: '#FFFFFF',
    text: '#111827',
  },
  color_overrides: {},
  border_radius: 'medium',
  font: {
    id: null,
    family: 'Mulish',
    url: null,
  },
}

export const createDefaultStorefrontAppearance = (): PublicStorefrontAppearance => ({
  colors: { ...DEFAULT_STOREFRONT_APPEARANCE.colors },
  color_overrides: {},
  border_radius: DEFAULT_STOREFRONT_APPEARANCE.border_radius,
  font: { ...DEFAULT_STOREFRONT_APPEARANCE.font },
})
