import type { StorefrontAppearanceColors } from './api/storefrontsAdminApi'
import {
  isStorefrontHexColor,
  normalizeStorefrontHex,
} from '~/features/storefront/color'

export type StorefrontColorKey = keyof StorefrontAppearanceColors
export type StorefrontColorErrors = Partial<Record<StorefrontColorKey, string>>

export const normalizeStorefrontColor = normalizeStorefrontHex

export const validateStorefrontColors = (colors: StorefrontAppearanceColors): StorefrontColorErrors => {
  const errors: StorefrontColorErrors = {}
  for (const [key, value] of Object.entries(colors) as Array<[StorefrontColorKey, string]>) {
    if (!isStorefrontHexColor(value)) {
      errors[key] = 'Введите цвет в формате #RRGGBB'
    }
  }
  return errors
}
