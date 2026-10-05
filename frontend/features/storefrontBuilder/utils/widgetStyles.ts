import type { WidgetStyles } from '../types'
import { normalizePageColor } from './pageTheme'

// Explicit widget colors override the inherited page palette, including nested
// surfaces and text. Invalid values continue to inherit the ancestor palette.
export const widgetColorStyles = (styles?: Pick<WidgetStyles, 'background_color' | 'text_color'>): Record<string, string> => {
  const result: Record<string, string> = {}
  const background = normalizePageColor(styles?.background_color)
  if (background) {
    result.backgroundColor = background
    result['--storefront-widget-surface'] = background
    result['--storefront-widget-surface-muted'] = background
  }
  const text = normalizePageColor(styles?.text_color)
  if (text) {
    result.color = text
    result['--storefront-widget-text'] = text
    result['--storefront-widget-text-muted'] = text
    result['--storefront-widget-foreground'] = text
  }
  return result
}
