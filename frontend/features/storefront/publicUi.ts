import type {
  StorefrontPublicPageKey,
  StorefrontPublicUi,
} from '~/features/storefront/types'
import { buildPublicRoute } from '~/features/storefront/publicRoute'

export const HOME_PAGE_KEYS: readonly StorefrontPublicPageKey[] = [
  'home',
  'about',
  'special_equipment_catalog',
] as const

export const PUBLIC_PAGE_TITLES: Record<StorefrontPublicPageKey, string> = {
  home: 'Главная',
  about: 'О нас',
  special_equipment_catalog: 'Спецтехника',
}

export const DEFAULT_STOREFRONT_PUBLIC_UI: Readonly<StorefrontPublicUi> = {
  home_page_key: 'home',
  pages: {
    home: { title: PUBLIC_PAGE_TITLES.home },
    about: { title: PUBLIC_PAGE_TITLES.about },
    special_equipment_catalog: { title: PUBLIC_PAGE_TITLES.special_equipment_catalog },
  },
}

export const PUBLIC_PAGE_PATHS: Record<StorefrontPublicPageKey, string> = {
  home: '/',
  about: '/about',
  special_equipment_catalog: '/special-equipment',
}

export const createDefaultStorefrontPublicUi = (): StorefrontPublicUi => ({
  home_page_key: DEFAULT_STOREFRONT_PUBLIC_UI.home_page_key,
  pages: {
    home: { ...DEFAULT_STOREFRONT_PUBLIC_UI.pages.home },
    about: { ...DEFAULT_STOREFRONT_PUBLIC_UI.pages.about },
    special_equipment_catalog: {
      ...DEFAULT_STOREFRONT_PUBLIC_UI.pages.special_equipment_catalog,
    },
  },
})

const locationSuffix = (fullPath: string): string => {
  const queryIndex = fullPath.indexOf('?')
  const hashIndex = fullPath.indexOf('#')
  const candidates = [queryIndex, hashIndex].filter(index => index >= 0)
  if (candidates.length === 0) return ''
  return fullPath.slice(Math.min(...candidates))
}

const withoutTrailingSlash = (path: string): string => (
  path.length > 1 && path.endsWith('/') ? path.slice(0, -1) : path
)

export const resolveConfiguredHomeRedirect = (
  slug: string | null,
  homePageKey: StorefrontPublicPageKey,
  currentPath: string,
  currentFullPath: string,
): string | null => {
  const storefrontRoot = buildPublicRoute(slug, '/')
  if (
    homePageKey === 'home'
    || withoutTrailingSlash(currentPath) !== withoutTrailingSlash(storefrontRoot)
  ) return null

  const target = buildPublicRoute(
    slug,
    `${PUBLIC_PAGE_PATHS[homePageKey]}${locationSuffix(currentFullPath)}`,
  )
  return target === currentFullPath ? null : target
}

