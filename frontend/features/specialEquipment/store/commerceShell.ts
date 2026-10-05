import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { useStorefront } from '~/features/storefront'
import type { UUID } from '~/types/ids'
import { createSpecialEquipmentApi } from '../api/specialEquipmentApi'
import {
  createSpecialEquipmentCartApi,
  type SpecialEquipmentCartItemPatch,
} from '../api/specialEquipmentCartApi'
import { toSpecialEquipmentCommerceProduct } from '../adapters/specialEquipmentCommerceProduct'
import { reconcileSpecialEquipmentServerCartGroup } from '../cartGroup'
import { runAuthoritativeSpecialEquipmentCartMutation } from '../cartMutations'
import {
  createSpecialEquipmentGuestCart,
  readSpecialEquipmentGuestCart,
  readSpecialEquipmentIds,
  reconcileSpecialEquipmentGuestCartGroup,
  replaceSpecialEquipmentGuestCartItems,
  specialEquipmentGuestTransferBody,
  SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY,
  writeSpecialEquipmentGuestCart,
  writeSpecialEquipmentIds,
  type SpecialEquipmentGuestCartSnapshot,
  type StoredSpecialEquipmentCartState,
} from '../composables/commerceStorage'
import type {
  SpecialEquipmentCartResponse,
  SpecialEquipmentCartItem,
  SpecialEquipmentCommerceProduct,
  SpecialEquipmentFavoritesResponse,
  SpecialEquipmentProblemDetails,
} from '../types'

interface FetchFailure {
  data?: SpecialEquipmentProblemDetails
  message?: string
}

interface LoadOptions {
  force?: boolean
  resolveGuestProducts?: boolean
}

export interface SpecialEquipmentCartGroupChild {
  product: SpecialEquipmentCommerceProduct
  quantity: number
}

const uniqueIds = (ids: Iterable<UUID>): UUID[] => [...new Set(ids)]

const failureMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== 'object') return fallback
  const failure = error as FetchFailure
  return failure.data?.detail ?? failure.data?.title ?? failure.message ?? fallback
}

const SPECIAL_EQUIPMENT_MAX_CART_QUANTITY = 1000

const safeQuantity = (quantity: number): number => {
  if (!Number.isSafeInteger(quantity) || quantity <= 0) return 1
  return Math.min(quantity, SPECIAL_EQUIPMENT_MAX_CART_QUANTITY)
}

export const useSpecialEquipmentCommerceShellStore = defineStore(
  'specialEquipmentCommerceShell',
  () => {
    const authStore = useAuthStore()
    const { apiPath } = useStorefront()
    const api = createSpecialEquipmentApi(useRuntimeConfig(), apiPath)
    const cartApi = createSpecialEquipmentCartApi(useRuntimeConfig(), apiPath)

    const favoriteIds = ref<UUID[]>([])
    const cartIds = ref<UUID[]>([])
    const favoriteProductsState = ref<SpecialEquipmentCommerceProduct[]>([])
    const cartProductsState = ref<SpecialEquipmentCommerceProduct[]>([])
    const cartItemsState = ref<SpecialEquipmentCartItem[]>([])
    const favoriteLoading = ref(false)
    const cartLoading = ref(false)
    const favoriteInitialized = ref(false)
    const cartInitialized = ref(false)
    const favoriteError = ref('')
    const cartError = ref('')

    let favoriteRequest: Promise<void> | null = null
    let cartRequest: Promise<boolean> | null = null
    let mergeGuestRequest: Promise<boolean> | null = null
    let favoriteRequestAuthState: boolean | null = null
    let cartRequestAuthState: boolean | null = null

    const favoriteCount = computed(() => favoriteIds.value.length)
    const cartCount = computed(() => cartItemsState.value.reduce(
      (total, item) => total + safeQuantity(item.quantity),
      0,
    ))
    const favoriteProducts = computed(() => favoriteProductsState.value)
    const cartProducts = computed(() => cartProductsState.value)
    const cartItems = computed(() => cartItemsState.value)
    const favoriteResolvedIds = computed(() => new Set(
      favoriteProductsState.value.map(product => product.id),
    ))
    const cartResolvedIds = computed(() => new Set(
      cartProductsState.value.map(product => product.id),
    ))
    const unresolvedFavoriteIds = computed(() => favoriteIds.value.filter(
      productId => !favoriteResolvedIds.value.has(productId),
    ))
    const unresolvedCartIds = computed(() => cartIds.value.filter(
      productId => !cartResolvedIds.value.has(productId),
    ))

    const resolveProducts = async (ids: UUID[]): Promise<SpecialEquipmentCommerceProduct[]> => {
      const settled = await Promise.allSettled(ids.map(productId => api.getProduct(productId)))
      const resolved = settled.flatMap(result => result.status === 'fulfilled'
        ? [toSpecialEquipmentCommerceProduct(result.value)]
        : [])
      const byId = new Map(resolved.map(product => [product.id, product]))
      return ids.flatMap((productId) => {
        const product = byId.get(productId)
        return product ? [product] : []
      })
    }

    const syncCartIndexes = () => {
      cartIds.value = uniqueIds(cartItemsState.value.map(item => item.product_id))
      const productsById = new Map<UUID, SpecialEquipmentCommerceProduct>()
      for (const item of cartItemsState.value) productsById.set(item.product_id, item.product)
      cartProductsState.value = [...productsById.values()]
    }

    const storedLineFromItem = (item: SpecialEquipmentCartItem): StoredSpecialEquipmentCartState => ({
      local_id: item.id,
      product_id: item.product_id,
      quantity: safeQuantity(item.quantity),
      allow_overstock: item.allow_overstock === true,
      parent_local_id: item.parent_item_id,
      is_selected: item.is_selected,
      comment: item.comment,
      equipments: item.equipments,
      services: item.services,
    })

    const persistGuestItems = () => {
      if (authStore.isAuthenticated) return
      const current = readSpecialEquipmentGuestCart()
      writeSpecialEquipmentGuestCart(replaceSpecialEquipmentGuestCartItems(
        current,
        cartItemsState.value.map(storedLineFromItem),
      ))
    }

    const guestItem = (
      stored: StoredSpecialEquipmentCartState,
      product: SpecialEquipmentCommerceProduct,
      snapshot: SpecialEquipmentGuestCartSnapshot,
    ): SpecialEquipmentCartItem => {
      const timestamp = new Date().toISOString()
      return {
        id: stored.local_id,
        product_id: stored.product_id,
        quantity: stored.quantity,
        allow_overstock: stored.allow_overstock === true,
        parent_item_id: stored.parent_local_id,
        transfer_id: snapshot.transfer_id,
        is_selected: stored.is_selected,
        custom_price: null,
        comment: stored.comment,
        equipments: stored.equipments,
        services: stored.services,
        added_at: timestamp,
        updated_at: timestamp,
        product,
      }
    }

    const upsertCartItem = (item: SpecialEquipmentCartItem) => {
      const index = cartItemsState.value.findIndex(existing => existing.id === item.id)
      if (index === -1) cartItemsState.value = [...cartItemsState.value, item]
      else cartItemsState.value[index] = item
      syncCartIndexes()
      cartInitialized.value = true
      cartError.value = ''
      persistGuestItems()
    }

    const hydrateAuthenticated = (
      favorites: SpecialEquipmentFavoritesResponse,
      cart: SpecialEquipmentCartResponse,
    ) => {
      favoriteIds.value = uniqueIds(favorites.items.map(item => item.product_id))
      favoriteProductsState.value = favorites.items.map(item => item.product)
      cartItemsState.value = cart.items
      syncCartIndexes()
      favoriteInitialized.value = true
      cartInitialized.value = true
      favoriteError.value = ''
      cartError.value = ''
    }

    const hydrateGuestIds = () => {
      favoriteIds.value = readSpecialEquipmentIds(SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY)
      const snapshot = readSpecialEquipmentGuestCart()
      const storedItems = snapshot?.items ?? []
      cartIds.value = uniqueIds(storedItems.map(item => item.product_id))
      favoriteProductsState.value = favoriteProductsState.value.filter(product =>
        favoriteIds.value.includes(product.id))
      cartProductsState.value = cartProductsState.value.filter(product =>
        cartIds.value.includes(product.id))
      if (snapshot) {
        const currentByLocalId = new Map(cartItemsState.value.map(item => [item.id, item]))
        const productsById = new Map(cartProductsState.value.map(product => [product.id, product]))
        cartItemsState.value = storedItems.flatMap((stored) => {
          const product = currentByLocalId.get(stored.local_id)?.product
            ?? productsById.get(stored.product_id)
          return product ? [guestItem(stored, product, snapshot)] : []
        })
      } else {
        cartItemsState.value = []
      }
      favoriteInitialized.value = true
      cartInitialized.value = true
      favoriteError.value = ''
      cartError.value = ''
    }

    const loadFavorites = async (options: LoadOptions = {}) => {
      if (favoriteRequest) {
        const requestAuthState = favoriteRequestAuthState
        await favoriteRequest
        const authStateChanged = requestAuthState !== authStore.isAuthenticated
        const needsGuestProducts = !authStore.isAuthenticated
          && options.resolveGuestProducts === true
          && favoriteProductsState.value.length < favoriteIds.value.length
        if (authStateChanged || needsGuestProducts) return loadFavorites(options)
        return
      }
      const needsGuestProducts = !authStore.isAuthenticated
        && options.resolveGuestProducts === true
        && favoriteProductsState.value.length < favoriteIds.value.length
      if (!options.force && favoriteInitialized.value && !needsGuestProducts) return

      favoriteRequestAuthState = authStore.isAuthenticated
      favoriteRequest = (async () => {
        favoriteLoading.value = true
        favoriteError.value = ''
        try {
          if (authStore.isAuthenticated) {
            const response = await api.getFavorites()
            favoriteIds.value = uniqueIds(response.items.map(item => item.product_id))
            favoriteProductsState.value = response.items.map(item => item.product)
          } else {
            favoriteIds.value = readSpecialEquipmentIds(SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY)
            if (options.resolveGuestProducts) {
              favoriteProductsState.value = await resolveProducts(favoriteIds.value)
              if (favoriteProductsState.value.length < favoriteIds.value.length) {
                favoriteError.value = 'Часть избранной техники временно недоступна'
              }
            }
          }
          favoriteInitialized.value = true
        } catch (error: unknown) {
          favoriteError.value = failureMessage(error, 'Не удалось загрузить избранную спецтехнику')
        } finally {
          favoriteLoading.value = false
        }
      })()
      try {
        await favoriteRequest
      } finally {
        favoriteRequest = null
        favoriteRequestAuthState = null
      }
    }

    const loadCart = async (options: LoadOptions = {}): Promise<boolean> => {
      if (cartRequest) {
        const request = cartRequest
        const requestAuthState = cartRequestAuthState
        const loaded = await request
        if (requestAuthState !== authStore.isAuthenticated || options.force) {
          if (cartRequest === request) {
            cartRequest = null
            cartRequestAuthState = null
          }
          return loadCart(options)
        }
        return loaded
      }
      if (!options.force && cartInitialized.value
        && (authStore.isAuthenticated || !options.resolveGuestProducts || cartItemsState.value.length > 0)) {
        return true
      }

      cartRequestAuthState = authStore.isAuthenticated
      const request = (async (): Promise<boolean> => {
        cartLoading.value = true
        cartError.value = ''
        try {
          if (authStore.isAuthenticated) {
            const response = await api.getCartItems()
            const products = await resolveProducts(uniqueIds(
              response.items.map(item => item.product_id),
            ))
            const productsById = new Map(products.map(product => [product.id, product]))
            cartItemsState.value = response.items.map(item => ({
              ...item,
              product: productsById.get(item.product_id) ?? {
                ...item.product,
                available_count: null,
              },
            }))
            if (products.length < new Set(response.items.map(item => item.product_id)).size) {
              cartError.value = 'Не удалось подтвердить актуальный остаток части техники'
            }
            syncCartIndexes()
          } else {
            const snapshot = readSpecialEquipmentGuestCart()
            const storedItems = snapshot?.items ?? []
            cartIds.value = uniqueIds(storedItems.map(item => item.product_id))
            if (options.resolveGuestProducts && snapshot) {
              const products = await resolveProducts(cartIds.value)
              const byId = new Map(products.map(product => [product.id, product]))
              cartItemsState.value = storedItems.flatMap((stored) => {
                const product = byId.get(stored.product_id)
                return product ? [guestItem(stored, product, snapshot)] : []
              })
              cartProductsState.value = products
              if (cartItemsState.value.length < storedItems.length) {
                cartError.value = 'Часть техники в корзине временно недоступна'
              }
            } else {
              cartItemsState.value = []
              cartProductsState.value = []
            }
          }
          cartInitialized.value = true
          return true
        } catch (error: unknown) {
          cartError.value = failureMessage(error, 'Не удалось загрузить корзину спецтехники')
          return false
        } finally {
          cartLoading.value = false
        }
      })()
      cartRequest = request
      try {
        return await request
      } finally {
        if (cartRequest === request) {
          cartRequest = null
          cartRequestAuthState = null
        }
      }
    }

    const reloadAuthoritativeCart = async (): Promise<void> => {
      const loaded = await loadCart({ force: true, resolveGuestProducts: true })
      if (!loaded) {
        throw new Error(cartError.value || 'Не удалось обновить корзину спецтехники')
      }
    }

    const loadAll = async (options: LoadOptions = {}) => {
      await Promise.all([loadFavorites(options), loadCart(options)])
    }

    const addGuestCartProduct = (
      product: SpecialEquipmentCommerceProduct,
      quantity = 1,
      parentLocalId: UUID | null = null,
    ): SpecialEquipmentCartItem => {
      const current = readSpecialEquipmentGuestCart() ?? createSpecialEquipmentGuestCart()
      const existing = parentLocalId === null
        ? current.items.find(item => item.product_id === product.id && item.parent_local_id === null)
        : undefined
      const stored: StoredSpecialEquipmentCartState = existing
        ? { ...existing, quantity: safeQuantity(quantity) }
        : {
            local_id: crypto.randomUUID(),
            product_id: product.id,
            quantity: safeQuantity(quantity),
            parent_local_id: parentLocalId,
            is_selected: true,
            comment: null,
            equipments: [],
            services: [],
          }
      const items = existing
        ? current.items.map(item => item.local_id === existing.local_id ? stored : item)
        : [...current.items, stored]
      const snapshot = replaceSpecialEquipmentGuestCartItems(current, items)
      writeSpecialEquipmentGuestCart(snapshot)
      const item = guestItem(stored, product, snapshot)
      upsertCartItem(item)
      return item
    }

    const createServerCartProduct = async (
      product: SpecialEquipmentCommerceProduct,
      quantity = 1,
      parentItemId: UUID | null = null,
    ) => {
      const response = await cartApi.createCartItem({
        product_id: product.id,
        quantity: safeQuantity(quantity),
        parent_item_id: parentItemId,
        is_selected: true,
      })
      upsertCartItem(response.cart_item)
      return response
    }

    const addCartProduct = async (
      product: SpecialEquipmentCommerceProduct,
      quantity = 1,
      parentItemId: UUID | null = null,
    ): Promise<SpecialEquipmentCartItem> => {
      if (!authStore.isAuthenticated) {
        return addGuestCartProduct(product, quantity, parentItemId)
      }
      return (await createServerCartProduct(product, quantity, parentItemId)).cart_item
    }

    const addCartGroup = async (
      parent: SpecialEquipmentCommerceProduct,
      quantity: number,
      children: SpecialEquipmentCartGroupChild[],
    ): Promise<SpecialEquipmentCartItem> => {
      if (!authStore.isAuthenticated) {
        const current = readSpecialEquipmentGuestCart() ?? createSpecialEquipmentGuestCart()
        const reconciled = reconcileSpecialEquipmentGuestCartGroup(
          current,
          parent.id,
          quantity,
          children.map(child => ({
            product_id: child.product.id,
            quantity: child.quantity,
          })),
          () => crypto.randomUUID(),
        )
        const { snapshot, parent: parentLine, children: childLines } = reconciled
        writeSpecialEquipmentGuestCart(snapshot)
        const parentItem = guestItem(parentLine, parent, snapshot)
        cartItemsState.value = [
          ...cartItemsState.value.filter(item => (
            item.id !== parentLine.local_id
            && item.parent_item_id !== parentLine.local_id
          )),
          parentItem,
          ...childLines.map((line, index) => guestItem(line, children[index]!.product, snapshot)),
        ]
        syncCartIndexes()
        cartInitialized.value = true
        return parentItem
      }

      await loadCart({ force: true, resolveGuestProducts: true })
      try {
        const reconciled = await reconcileSpecialEquipmentServerCartGroup({
          api: cartApi,
          currentItems: cartItemsState.value,
          parentProductId: parent.id,
          quantity: safeQuantity(quantity),
          children: children.map(child => ({
            productId: child.product.id,
            quantity: safeQuantity(child.quantity),
          })),
        })
        await loadCart({ force: true, resolveGuestProducts: true })
        const parentItem = cartItemsState.value.find(item => item.id === reconciled.parentCartItemId)
        if (!parentItem) throw new Error('Не удалось подтвердить комплект в корзине')
        return parentItem
      } catch (error: unknown) {
        await loadCart({ force: true, resolveGuestProducts: true })
        throw error
      }
    }

    const mergeGuestState = async (): Promise<boolean> => {
      if (!import.meta.client || !authStore.isAuthenticated) return false
      if (mergeGuestRequest) return mergeGuestRequest

      mergeGuestRequest = (async () => {
        const guestFavoriteIds = readSpecialEquipmentIds(SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY)
        const guestCart = readSpecialEquipmentGuestCart()
        const favoriteResults = await Promise.allSettled(
          guestFavoriteIds.map(productId => api.addFavorite(productId)),
        )
        const failedFavoriteIds = guestFavoriteIds.filter(
          (_, index) => favoriteResults[index]?.status === 'rejected',
        )
        writeSpecialEquipmentIds(SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY, failedFavoriteIds)

        let cartFailed = false
        if (guestCart && guestCart.items.length > 0) {
          try {
            const response = await cartApi.transferGuestCart(
              guestCart.transfer_id,
              specialEquipmentGuestTransferBody(guestCart),
            )
            if (response.transfer_id !== guestCart.transfer_id) {
              throw new Error('Сервер подтвердил перенос корзины с другим transfer_id')
            }
            if (!authStore.isAuthenticated) {
              throw new Error('Сессия завершилась до подтверждения переноса корзины')
            }
            cartItemsState.value = response.items
            syncCartIndexes()
            writeSpecialEquipmentGuestCart(null)
          } catch {
            cartFailed = true
          }
        }
        await loadAll({ force: true, resolveGuestProducts: true })
        return cartFailed || failedFavoriteIds.length > 0
      })()

      try {
        return await mergeGuestRequest
      } finally {
        mergeGuestRequest = null
      }
    }

    const setMembership = (
      collection: 'favorite' | 'cart',
      productId: UUID,
      enabled: boolean,
    ) => {
      if (collection === 'favorite') {
        favoriteIds.value = enabled
          ? uniqueIds([...favoriteIds.value, productId])
          : favoriteIds.value.filter(id => id !== productId)
        if (!enabled) {
          favoriteProductsState.value = favoriteProductsState.value.filter(
            product => product.id !== productId,
          )
        }
        return
      }
      if (!enabled) {
        cartItemsState.value = cartItemsState.value.filter(item => item.product_id !== productId)
        syncCartIndexes()
        persistGuestItems()
      }
    }

    const removeFavorite = async (productId: UUID) => {
      if (authStore.isAuthenticated) await api.removeFavorite(productId)
      setMembership('favorite', productId, false)
      if (!authStore.isAuthenticated) {
        writeSpecialEquipmentIds(SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY, favoriteIds.value)
      }
    }

    const removeCartItem = async (cartItemId: UUID) => {
      const existing = cartItemsState.value.find(item => item.id === cartItemId)
      if (!existing) throw new Error('Позиция спецтехники не найдена в корзине')
      if (authStore.isAuthenticated) {
        await runAuthoritativeSpecialEquipmentCartMutation({
          mutate: async () => { await cartApi.removeCartItem(cartItemId) },
          reload: reloadAuthoritativeCart,
        })
        return
      }
      cartItemsState.value = cartItemsState.value
        .filter(item => item.id !== cartItemId)
        .map(item => item.parent_item_id === cartItemId
          ? { ...item, parent_item_id: null }
          : item)
      syncCartIndexes()
      persistGuestItems()
    }

    const removeProductCartItems = async (productId: UUID) => {
      if (!authStore.isAuthenticated) {
        const snapshot = readSpecialEquipmentGuestCart()
        if (!snapshot) return
        const removedIds = new Set(snapshot.items
          .filter(item => item.product_id === productId)
          .map(item => item.local_id))
        if (removedIds.size === 0) return
        writeSpecialEquipmentGuestCart(replaceSpecialEquipmentGuestCartItems(
          snapshot,
          snapshot.items
            .filter(item => !removedIds.has(item.local_id))
            .map(item => item.parent_local_id !== null && removedIds.has(item.parent_local_id)
              ? { ...item, parent_local_id: null }
              : item),
        ))
        hydrateGuestIds()
        return
      }
      const itemIds = cartItemsState.value
        .filter(item => item.product_id === productId)
        .map(item => item.id)
      for (const itemId of itemIds) await removeCartItem(itemId)
    }

    const removeStandaloneCartProduct = async (productId: UUID) => {
      const item = cartItemsState.value.find(
        cartItem => cartItem.product_id === productId && cartItem.parent_item_id === null,
      )
      if (!item && !authStore.isAuthenticated) {
        const snapshot = readSpecialEquipmentGuestCart()
        const stored = snapshot?.items.find(cartItem => (
          cartItem.product_id === productId && cartItem.parent_local_id === null
        ))
        if (!snapshot || !stored) return
        writeSpecialEquipmentGuestCart(replaceSpecialEquipmentGuestCartItems(
          snapshot,
          snapshot.items
            .filter(cartItem => cartItem.local_id !== stored.local_id)
            .map(cartItem => cartItem.parent_local_id === stored.local_id
              ? { ...cartItem, parent_local_id: null }
              : cartItem),
        ))
        hydrateGuestIds()
        return
      }
      if (!item) return
      await removeCartItem(item.id)
    }

    const hasStandaloneCartProduct = (productId: UUID): boolean => {
      if (cartItemsState.value.some(item => (
        item.product_id === productId && item.parent_item_id === null
      ))) return true
      if (authStore.isAuthenticated) return false
      return readSpecialEquipmentGuestCart()?.items.some(item => (
        item.product_id === productId && item.parent_local_id === null
      )) ?? false
    }

    const updateCartItem = async (
      cartItemId: UUID,
      patch: SpecialEquipmentCartItemPatch,
    ) => {
      const existing = cartItemsState.value.find(item => item.id === cartItemId)
      if (!existing) throw new Error('Позиция спецтехники не найдена в корзине')

      if (authStore.isAuthenticated) {
        if (patch.parent_item_id !== undefined) {
          await runAuthoritativeSpecialEquipmentCartMutation({
            mutate: async () => { await cartApi.updateCartItem(cartItemId, patch) },
            reload: reloadAuthoritativeCart,
          })
          return
        }
        const response = await cartApi.updateCartItem(cartItemId, patch)
        Object.assign(existing, response.cart_item)
        syncCartIndexes()
        return
      }

      if (patch.quantity !== undefined) existing.quantity = safeQuantity(patch.quantity)
      if (patch.parent_item_id !== undefined) existing.parent_item_id = patch.parent_item_id
      if (patch.allow_overstock !== undefined) {
        existing.allow_overstock = existing.parent_item_id === null ? patch.allow_overstock : false
      }
      if (patch.is_selected !== undefined) existing.is_selected = patch.is_selected
      if (patch.custom_price !== undefined) existing.custom_price = patch.custom_price
      if (patch.comment !== undefined) existing.comment = patch.comment
      if (patch.equipments !== undefined) existing.equipments = patch.equipments
      if (patch.services !== undefined) existing.services = patch.services
      existing.updated_at = new Date().toISOString()
      persistGuestItems()
    }

    const clearCart = async () => {
      if (authStore.isAuthenticated) await cartApi.clearCartItems()
      cartIds.value = []
      cartProductsState.value = []
      cartItemsState.value = []
      if (!authStore.isAuthenticated) writeSpecialEquipmentGuestCart(null)
    }

    const reset = () => {
      favoriteIds.value = []
      cartIds.value = []
      favoriteProductsState.value = []
      cartProductsState.value = []
      cartItemsState.value = []
      favoriteInitialized.value = false
      cartInitialized.value = false
      favoriteError.value = ''
      cartError.value = ''
    }

    return {
      favoriteIds,
      cartIds,
      favoriteCount,
      cartCount,
      favoriteProducts,
      cartProducts,
      cartItems,
      unresolvedFavoriteIds,
      unresolvedCartIds,
      favoriteLoading,
      cartLoading,
      favoriteInitialized,
      cartInitialized,
      favoriteError,
      cartError,
      hydrateAuthenticated,
      hydrateGuestIds,
      loadFavorites,
      loadCart,
      loadAll,
      mergeGuestState,
      setMembership,
      upsertCartItem,
      addGuestCartProduct,
      addCartProduct,
      addCartGroup,
      removeFavorite,
      removeCartItem,
      removeProductCartItems,
      removeStandaloneCartProduct,
      hasStandaloneCartProduct,
      updateCartItem,
      clearCart,
      reset,
    }
  },
)
