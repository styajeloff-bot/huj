import { DEFAULT_STOREFRONT_APPEARANCE } from '~/features/storefront/appearance'
import {
  isStorefrontHexColor,
  normalizeStorefrontHex,
} from '~/features/storefront/color'
import type {
  PublicStorefrontAppearance,
  StorefrontAppearanceColors,
  StorefrontBorderRadius,
  StorefrontFontDescriptor,
} from '~/features/storefront/types'
import { isUuid } from '~/types/ids'
import { resolveStorefrontColors, storefrontColorVariables, STOREFRONT_COLOR_REGISTRY, type ResolvedStorefrontColor, type StorefrontPreviewContext } from './colorRegistry'

const DEFAULT_FONT_STACK = 'Mulish, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'

const RADIUS_TOKENS: Record<StorefrontBorderRadius, {
  control: string
  surface: string
  inner: string
}> = {
  none: { control: '0px', surface: '0px', inner: '0px' },
  small: { control: '4px', surface: '8px', inner: '4px' },
  medium: { control: '8px', surface: '12px', inner: '8px' },
  large: { control: '12px', surface: '16px', inner: '12px' },
}

export type StorefrontThemeVariables = Record<string, string>

export interface StorefrontTheme {
  variables: StorefrontThemeVariables
  fontFaceCss: string | null
  fontPreloadHref: string | null
  scopeCss: string
  resolvedColors: Record<string, ResolvedStorefrontColor>
  blocks: Record<string, StorefrontThemeVariables>
}

const normalizeColor = (value: string, fallback: string): string => {
  const normalized = normalizeStorefrontHex(value)
  return isStorefrontHexColor(normalized) ? normalized : fallback
}

const safeColors = (colors: StorefrontAppearanceColors): StorefrontAppearanceColors => ({
  primary: normalizeColor(colors.primary, DEFAULT_STOREFRONT_APPEARANCE.colors.primary),
  background: normalizeColor(colors.background, DEFAULT_STOREFRONT_APPEARANCE.colors.background),
  surface: normalizeColor(colors.surface, DEFAULT_STOREFRONT_APPEARANCE.colors.surface),
  text: normalizeColor(colors.text, DEFAULT_STOREFRONT_APPEARANCE.colors.text),
})

const safeRadius = (value: StorefrontBorderRadius): StorefrontBorderRadius => (
  Object.hasOwn(RADIUS_TOKENS, value) ? value : DEFAULT_STOREFRONT_APPEARANCE.border_radius
)

const customFont = (font: StorefrontFontDescriptor): { family: string; url: string } | null => {
  if (!font.id || !font.url || !isUuid(font.id)) return null
  const normalizedId = font.id.toLowerCase()
  const expectedFamily = `storefront-font-${normalizedId.replaceAll('-', '')}`
  const expectedUrl = `/api/v1/storefront-fonts/${normalizedId}/content`
  return font.family === expectedFamily && font.url === expectedUrl
    ? { family: expectedFamily, url: expectedUrl }
    : null
}

export const buildStorefrontTheme = (appearance: PublicStorefrontAppearance, previewContext?: StorefrontPreviewContext): StorefrontTheme => {
  const colors = safeColors(appearance.colors)
  const radius = RADIUS_TOKENS[safeRadius(appearance.border_radius)]
  const font = customFont(appearance.font)
  const fontFamily = font ? `"${font.family}", ${DEFAULT_FONT_STACK}` : DEFAULT_FONT_STACK
  const resolvedColors = resolveStorefrontColors(colors, appearance.color_overrides, previewContext)
  const blocks = Object.fromEntries(Object.keys(STOREFRONT_COLOR_REGISTRY.blocks)
    .map(block => [block, storefrontColorVariables(resolvedColors, block)]))
  const localTokensByBlock = new Map<string, Set<string>>()
  const inheritsLocalChoice = (color: ResolvedStorefrontColor): boolean => {
    let ancestor = color.inheritedFrom ? resolvedColors[color.inheritedFrom] : undefined
    while (ancestor && ancestor.block !== 'global') {
      if (ancestor.inheritedFrom === null) return true
      ancestor = resolvedColors[ancestor.inheritedFrom]
    }
    return false
  }
  for (const color of Object.values(resolvedColors)) {
    if (color.inheritedFrom !== null && (!STOREFRONT_COLOR_REGISTRY.blocks[color.block]?.teleport || !inheritsLocalChoice(color))) continue
    const tokens = localTokensByBlock.get(color.block) ?? new Set<string>()
    tokens.add(color.token)
    localTokensByBlock.set(color.block, tokens)
  }
  const scopeCss = Object.entries(blocks).filter(([block]) => block !== 'global')
    .map(([block, variables]) => {
      // Local choices and Teleport's explicit registry ancestors survive. Other
      // missing choices inherit the real DOM ancestor, including shared forms.
      const localTokens = localTokensByBlock.get(block) ?? new Set<string>()
      const localVariables = Object.fromEntries(Object.entries(variables)
        .filter(([name]) => localTokens.has(name.replace('--storefront-', '').replace(/-(rgb|arrow|check|radio)$/, ''))))
      if (Object.keys(localVariables).length === 0) return ''
      return `.storefront-theme [data-storefront-block="${block}"],.storefront-theme[data-storefront-block="${block}"]{${serializeStorefrontThemeVariables(localVariables)}}`
    }).filter(Boolean).join('\n')

  return {
    variables: {
      '--storefront-radius-control': radius.control,
      '--storefront-radius-surface': radius.surface,
      '--storefront-radius-inner': radius.inner,
      '--storefront-font-family': fontFamily,
      ...blocks.global,
    },
    fontFaceCss: font
      ? `@font-face{font-family:"${font.family}";src:url("${font.url}") format("woff2");font-display:swap;font-style:normal;font-weight:normal;}`
      : null,
    fontPreloadHref: font?.url ?? null,
    scopeCss,
    resolvedColors,
    blocks,
  }
}

export const serializeStorefrontThemeVariables = (
  variables: StorefrontThemeVariables,
): string => Object.entries(variables)
  .map(([name, value]) => `${name}:${value}`)
  .join(';')
