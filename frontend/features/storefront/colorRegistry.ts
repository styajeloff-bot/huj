import registryJson from './colorRegistry.json'
import { isStorefrontHexColor, mixStorefrontColors, normalizeStorefrontHex, storefrontPrimaryForeground } from './color'
import type { StorefrontAppearanceColors } from './types'

export interface StorefrontColorToken {
  key: string
  label: string
  element: string
  state: string
  fallback: string
}
export interface StorefrontColorBlock {
  label: string
  parent?: string
  tokens: string[]
  defaults?: Record<string, string>
  previewContexts?: string[]
  teleport?: boolean
}
export const STOREFRONT_COLOR_REGISTRY: {
  tokens: Record<string, StorefrontColorToken>
  blocks: Record<string, StorefrontColorBlock>
} = registryJson

export interface ResolvedStorefrontColor {
  key: string
  block: string
  token: string
  value: string
  source: 'custom' | 'palette' | 'system'
  inheritedFrom: string | null
}

export interface StorefrontPreviewContext {
  block: string
  parent: string
}

export const storefrontColorKey = (block: string, token: string): string =>
  `${block}.${STOREFRONT_COLOR_REGISTRY.tokens[token]?.key ?? token}`

export const STOREFRONT_COLOR_KEYS = new Set(Object.entries(STOREFRONT_COLOR_REGISTRY.blocks)
  .flatMap(([block, definition]) => definition.tokens.map(token => storefrontColorKey(block, token))))

export const validateStorefrontColorOverrides = (overrides: Record<string, string>): Record<string, string> => {
  const errors: Record<string, string> = {}
  for (const [key, value] of Object.entries(overrides)) {
    if (!STOREFRONT_COLOR_KEYS.has(key)) errors[key] = 'Неизвестный параметр цвета'
    else if (!isStorefrontHexColor(value)) errors[key] = 'Введите цвет в формате #RRGGBB'
  }
  return errors
}

/** Pure resolver shared by SSR, public runtime and the admin draft sample. */
export const resolveStorefrontColors = (
  colors: StorefrontAppearanceColors,
  overrides: Record<string, string> = {},
  previewContext?: StorefrontPreviewContext,
): Record<string, ResolvedStorefrontColor> => {
  const resolved: Record<string, ResolvedStorefrontColor> = {}
  const safePreviewParent = (): string | null => {
    if (!previewContext) return null
    if (!STOREFRONT_COLOR_REGISTRY.blocks[previewContext.block]?.previewContexts?.includes(previewContext.parent)) return null
    let ancestor: string | undefined = previewContext.parent
    while (ancestor && ancestor !== 'global') {
      if (ancestor === previewContext.block) return null
      ancestor = STOREFRONT_COLOR_REGISTRY.blocks[ancestor]?.parent
    }
    return previewContext.parent
  }
  const previewParent = safePreviewParent()
  const resolve = (block: string, token: string): ResolvedStorefrontColor => {
    const key = storefrontColorKey(block, token)
    if (resolved[key]) return resolved[key]
    const definition = STOREFRONT_COLOR_REGISTRY.blocks[block]
    const tokenDefinition = STOREFRONT_COLOR_REGISTRY.tokens[token]
    const explicit = STOREFRONT_COLOR_KEYS.has(key) ? overrides[key] : undefined
    if (explicit && isStorefrontHexColor(explicit)) {
      return resolved[key] = { key, block, token, value: normalizeStorefrontHex(explicit), source: 'custom', inheritedFrom: null }
    }
    const system = definition?.defaults?.[token]
    if (system) return resolved[key] = { key, block, token, value: system, source: 'system', inheritedFrom: null }
    if (block !== 'global') {
      const parentBlock = block === previewContext?.block && previewParent ? previewParent : definition?.parent ?? 'global'
      const parent = resolve(parentBlock, token)
      return resolved[key] = { key, block, token, value: parent.value, source: parent.source === 'system' ? 'system' : 'palette', inheritedFrom: parent.key }
    }
    const fallback = tokenDefinition.fallback
    let value: string
    if (fallback.startsWith('@base.')) value = colors[fallback.slice(6) as keyof StorefrontAppearanceColors]
    else if (fallback.startsWith('@auto.')) value = storefrontPrimaryForeground(resolve('global', fallback.slice(6)).value)
    else if (fallback.startsWith('@mix.')) {
      const match = /^@mix\.([\w-]+)\.([\w-]+)\.([\d.]+)$/.exec(fallback)!
      const color = (name: string) => name === 'black' ? '#000000' : resolve('global', name).value
      value = mixStorefrontColors(color(match[1]!), color(match[2]!), Number(match[3]))
    } else value = fallback.startsWith('@') ? resolve('global', fallback.slice(1)).value : fallback
    return resolved[key] = { key, block, token, value, source: fallback.startsWith('#') ? 'system' : 'palette', inheritedFrom: null }
  }
  for (const [block, definition] of Object.entries(STOREFRONT_COLOR_REGISTRY.blocks)) {
    for (const token of definition.tokens) resolve(block, token)
  }
  return resolved
}

export const storefrontTokenVariables = (token: string, value: string): Record<string, string> => {
  const variables: Record<string, string> = {}
  if (Object.hasOwn(STOREFRONT_COLOR_REGISTRY.tokens, token) && isStorefrontHexColor(value)) {
    variables[`--storefront-${token}`] = value
    variables[`--storefront-${token}-rgb`] = [1, 3, 5].map(index => Number.parseInt(value.slice(index, index + 2), 16)).join(' ')
    if (/^input(?:-(?:hover|active|focus|disabled))?-icon$/.test(token)) {
      // The only data-URI interpolation is a validated six-digit color.
      variables[`--storefront-${token}-arrow`] = `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%23${value.slice(1)}' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='m6 8 4 4 4-4'/%3e%3c/svg%3e")`
    }
    if (token === 'selected-icon' || token === 'input-disabled-icon') {
      variables[`--storefront-${token}-check`] = `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3e%3cpath fill='none' stroke='%23${value.slice(1)}' stroke-width='2' d='m3 8 3 3 7-7'/%3e%3c/svg%3e")`
      variables[`--storefront-${token}-radio`] = `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3e%3ccircle fill='%23${value.slice(1)}' cx='8' cy='8' r='4'/%3e%3c/svg%3e")`
    }
  }
  return variables
}

export const storefrontColorVariables = (values: Record<string, ResolvedStorefrontColor>, block: string): Record<string, string> =>
  Object.assign({}, ...(STOREFRONT_COLOR_REGISTRY.blocks[block]?.tokens ?? [])
    .map(token => storefrontTokenVariables(token, values[storefrontColorKey(block, token)]!.value)))
