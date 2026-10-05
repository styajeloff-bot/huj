import { storeToRefs } from 'pinia'

import { useStorefrontStore } from '~/features/storefront/store/storefront'
import {
  buildStorefrontTheme,
  serializeStorefrontThemeVariables,
} from '~/features/storefront/theme'

export function useStorefrontTheme() {
  const storefront = useStorefrontStore()
  const { appearance } = storeToRefs(storefront)
  const theme = computed(() => buildStorefrontTheme(appearance.value))
  const rootStyle = computed(() => theme.value.variables)

  useHead(() => ({
    bodyAttrs: {
      class: 'storefront-theme',
      style: serializeStorefrontThemeVariables(theme.value.variables),
    },
    link: theme.value.fontPreloadHref
      ? [{
          key: 'storefront-font-preload',
          rel: 'preload',
          href: theme.value.fontPreloadHref,
          as: 'font',
          type: 'font/woff2',
          crossorigin: '',
        }]
      : [],
    style: [
      { key: 'storefront-color-scopes', type: 'text/css', innerHTML: theme.value.scopeCss },
      ...(theme.value.fontFaceCss ? [{
          key: 'storefront-font-face',
          type: 'text/css',
          innerHTML: theme.value.fontFaceCss,
        }] : []),
    ],
  }))

  return { rootStyle }
}
