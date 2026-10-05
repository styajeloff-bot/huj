import { createDefaultStorefrontAppearance } from '~/features/storefront/appearance'
import { isStorefrontHexColor, normalizeStorefrontHex } from '~/features/storefront/color'
import { STOREFRONT_COLOR_REGISTRY, storefrontColorKey } from '~/features/storefront/colorRegistry'
import { buildStorefrontTheme, type StorefrontThemeVariables } from '~/features/storefront/theme'
import type { PublicStorefrontAppearance, StorefrontAppearanceColors } from '~/features/storefront/types'
import type { PageGlobalSettings } from '../types'

export type StorefrontPageAppearance = Pick<PublicStorefrontAppearance, 'colors' | 'color_overrides'>

export const normalizePageColor = (value: unknown): string | null => {
  if (typeof value !== 'string') return null
  const normalized = normalizeStorefrontHex(value)
  const expanded = /^#[0-9A-F]{3}$/.test(normalized)
    ? `#${normalized.slice(1).split('').map(character => character.repeat(2)).join('')}`
    : normalized
  return isStorefrontHexColor(expanded) ? expanded : null
}

// Registry recipes describe which base palette colors produce each global token.
// A page choice replaces that family, while unrelated storefront choices survive.
const dependsOnPageColor = (token: string, chosen: Set<string>): boolean => {
  const fallback = STOREFRONT_COLOR_REGISTRY.tokens[token]?.fallback
  if (!fallback?.startsWith('@')) return false
  if (fallback.startsWith('@base.')) return chosen.has(fallback.slice(6))
  if (fallback.startsWith('@mix.')) {
    const [, first, second] = fallback.split('.')
    return [first, second].some(dependency => dependency && dependsOnPageColor(dependency, chosen))
  }
  return dependsOnPageColor(fallback.replace(/^@(?:auto\.)?/, ''), chosen)
}

export const buildStorefrontPageTheme = (
  settings: PageGlobalSettings | undefined,
  appearance?: StorefrontPageAppearance | null,
): StorefrontThemeVariables => {
  const defaults = createDefaultStorefrontAppearance()
  const colors: StorefrontAppearanceColors = { ...(appearance?.colors ?? defaults.colors) }
  const chosen = new Set<string>()
  for (const key of ['primary', 'background', 'surface', 'text'] as const) {
    const value = normalizePageColor(settings?.[`${key}_color`])
    if (value) {
      colors[key] = value
      chosen.add(key)
    }
  }
  const replacedKeys = new Set(STOREFRONT_COLOR_REGISTRY.blocks.global!.tokens
    .filter(token => dependsOnPageColor(token, chosen))
    .map(token => storefrontColorKey('global', token)))
  const colorOverrides = Object.fromEntries(Object.entries(appearance?.color_overrides ?? {})
    .filter(([key]) => !replacedKeys.has(key)))
  return buildStorefrontTheme({ ...defaults, colors, color_overrides: colorOverrides }).blocks.global!
}
