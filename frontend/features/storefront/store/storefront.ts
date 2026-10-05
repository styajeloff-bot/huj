import { defineStore } from 'pinia'

import {
  createDefaultStorefrontContext,
  type PublicStorefront,
  type StorefrontContext,
} from '~/features/storefront/types'

export const useStorefrontStore = defineStore('storefront-context', {
  state: (): StorefrontContext => createDefaultStorefrontContext(),
  actions: {
    useDefault(): void {
      Object.assign(this, createDefaultStorefrontContext())
    },
    resolve(storefront: PublicStorefront): void {
      Object.assign(this, storefront, { is_resolved: true })
    },
  },
})
