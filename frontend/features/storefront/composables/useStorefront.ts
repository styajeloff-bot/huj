import { storeToRefs } from 'pinia'

import { useStorefrontStore } from '~/features/storefront/store/storefront'
import {
  buildPublicRoute,
  buildStorefrontApiPath,
  buildStorefrontStorageKey,
} from '~/features/storefront/publicRoute'
import type { StorefrontPublicPageKey } from '~/features/storefront/types'

export function useStorefront() {
  const store = useStorefrontStore()
  const context = storeToRefs(store)

  return {
    ...context,
    publicRoute: (path: string) => buildPublicRoute(store.slug, path),
    apiPath: (path: string) => buildStorefrontApiPath(store.slug, path),
    storageKey: (key: string) => buildStorefrontStorageKey(store.id, key),
    pageTitle: (key: StorefrontPublicPageKey) => store.public_ui.pages[key].title,
  }
}
