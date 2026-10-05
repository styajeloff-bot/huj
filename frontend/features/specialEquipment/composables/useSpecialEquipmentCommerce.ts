import { useAuthStore } from '~/features/auth/store/auth'
import { useStorefront } from '~/features/storefront'
import type { UUID } from '~/types/ids'
import { createSpecialEquipmentApi } from '../api/specialEquipmentApi'
import { toSpecialEquipmentCommerceProduct } from '../adapters/specialEquipmentCommerceProduct'
import { useSpecialEquipmentCommerceShellStore } from '../store/commerceShell'
import {
  SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY,
  writeSpecialEquipmentIds,
} from './commerceStorage'
import type {
  SpecialEquipmentCartItem,
  SpecialEquipmentCommerceProduct,
  SpecialEquipmentProductCard,
  SpecialEquipmentProblemDetails,
} from '../types'

interface FetchFailure {
  status?: number
  statusCode?: number
  response?: { status?: number }
  data?: SpecialEquipmentProblemDetails
  message?: string
}

interface CommerceOptions {
  onAuthRequired?: () => void
}

const failureStatus = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined
  const failure = error as FetchFailure
  return failure.statusCode ?? failure.status ?? failure.response?.status
}

const failureMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== 'object') return fallback
  const failure = error as FetchFailure
  return failure.data?.detail ?? failure.data?.title ?? failure.message ?? fallback
}

export const useSpecialEquipmentCommerce = (options: CommerceOptions = {}) => {
  const config = useRuntimeConfig()
  const { apiPath } = useStorefront()
  const api = createSpecialEquipmentApi(config, apiPath)
  const authStore = useAuthStore()
  const shellStore = useSpecialEquipmentCommerceShellStore()
  const toast = useToast()

  const favoriteIds = ref<Set<UUID>>(new Set())
  const cartIds = computed<ReadonlySet<UUID>>(() => new Set(shellStore.cartIds))
  const pendingFavoriteIds = ref<Set<UUID>>(new Set())
  const pendingCartIds = ref<Set<UUID>>(new Set())
  const overlayLoading = ref(false)

  const replaceSetValue = (target: Ref<Set<UUID>>, productId: UUID, enabled: boolean) => {
    const next = new Set(target.value)
    if (enabled) next.add(productId)
    else next.delete(productId)
    target.value = next
  }

  watch(
    () => shellStore.favoriteIds,
    ids => { favoriteIds.value = new Set(ids) },
    { immediate: true },
  )
  const loadGuestState = () => {
    shellStore.hydrateGuestIds()
    favoriteIds.value = new Set(shellStore.favoriteIds)
  }

  const loadAuthenticatedOverlay = async () => {
    if (!authStore.isAuthenticated) return
    overlayLoading.value = true
    try {
      const [favorites, cart] = await Promise.all([
        api.getFavorites(),
        api.getCartItems(),
      ])
      favoriteIds.value = new Set(favorites.items.map((item) => item.product_id))
      shellStore.hydrateAuthenticated(favorites, cart)
      await shellStore.loadCart({ force: true, resolveGuestProducts: true })
    } catch (error: unknown) {
      if (failureStatus(error) === 401) {
        authStore.logoutLocal()
        loadGuestState()
        options.onAuthRequired?.()
        return
      }
      toast.error(failureMessage(error, 'Не удалось загрузить избранное и корзину'))
    } finally {
      overlayLoading.value = false
    }
  }

  let mergeGuestPromise: Promise<void> | null = null

  const mergeGuestState = async () => {
    if (!import.meta.client || !authStore.isAuthenticated) return
    if (mergeGuestPromise) return mergeGuestPromise

    mergeGuestPromise = (async () => {
      const hasFailure = await shellStore.mergeGuestState()
      await loadAuthenticatedOverlay()

      if (hasFailure) {
        toast.warning('Часть сохранённых позиций недоступна и не была перенесена')
      }
    })()

    try {
      await mergeGuestPromise
    } finally {
      mergeGuestPromise = null
    }
  }

  const toggleFavorite = async (productId: UUID, isAllowed = true) => {
    if (!isAllowed || pendingFavoriteIds.value.has(productId)) return
    const shouldAdd = !favoriteIds.value.has(productId)
    replaceSetValue(favoriteIds, productId, shouldAdd)
    shellStore.setMembership('favorite', productId, shouldAdd)

    if (!authStore.isAuthenticated) {
      writeSpecialEquipmentIds(SPECIAL_EQUIPMENT_FAVORITES_STORAGE_KEY, favoriteIds.value)
      toast.success(shouldAdd ? 'Добавлено в избранное' : 'Удалено из избранного')
      return
    }

    replaceSetValue(pendingFavoriteIds, productId, true)
    try {
      if (shouldAdd) await api.addFavorite(productId)
      else await api.removeFavorite(productId)
      toast.success(shouldAdd ? 'Добавлено в избранное' : 'Удалено из избранного')
    } catch (error: unknown) {
      replaceSetValue(favoriteIds, productId, !shouldAdd)
      shellStore.setMembership('favorite', productId, !shouldAdd)
      if (failureStatus(error) === 401) {
        authStore.logoutLocal()
        options.onAuthRequired?.()
      } else {
        toast.error(failureMessage(error, 'Не удалось изменить избранное'))
      }
    } finally {
      replaceSetValue(pendingFavoriteIds, productId, false)
    }
  }

  const toggleCart = async (
    productId: UUID,
    isAllowed = true,
    product?: SpecialEquipmentCommerceProduct | SpecialEquipmentProductCard,
  ) => {
    if (overlayLoading.value || pendingCartIds.value.has(productId)) return
    const shouldAdd = !cartIds.value.has(productId)
    if (shouldAdd && !isAllowed) return

    replaceSetValue(pendingCartIds, productId, true)
    try {
      if (shouldAdd) {
        const resolvedProduct = product && 'mark' in product
          ? product
          : toSpecialEquipmentCommerceProduct(product ?? await api.getProduct(productId))
        await shellStore.addCartProduct(resolvedProduct)
      } else {
        await shellStore.removeProductCartItems(productId)
      }
      toast.success(shouldAdd ? 'Добавлено в корзину' : 'Удалено из корзины')
    } catch (error: unknown) {
      if (failureStatus(error) === 401) {
        authStore.logoutLocal()
        options.onAuthRequired?.()
      } else {
        toast.error(failureMessage(error, 'Не удалось изменить корзину'))
      }
    } finally {
      replaceSetValue(pendingCartIds, productId, false)
    }
  }

  const ensureCartItem = async (productId: UUID, isAllowed = true): Promise<boolean> => {
    if (!isAllowed) return false
    if (cartIds.value.has(productId)) return true
    await toggleCart(productId, true)
    return cartIds.value.has(productId)
  }

  const addCartGroup = async (
    parent: SpecialEquipmentProductCard,
    quantity: number,
    children: Array<{ product: SpecialEquipmentProductCard; quantity: number }>,
    isAllowed = true,
  ): Promise<SpecialEquipmentCartItem[] | null> => {
    if (!isAllowed || overlayLoading.value || pendingCartIds.value.has(parent.id)) return null
    replaceSetValue(pendingCartIds, parent.id, true)
    try {
      const parentItem = await shellStore.addCartGroup(
        toSpecialEquipmentCommerceProduct(parent),
        quantity,
        children.map(child => ({
          product: toSpecialEquipmentCommerceProduct(child.product),
          quantity: child.quantity,
        })),
      )
      const group = [
        parentItem,
        ...shellStore.cartItems.filter(item => item.parent_item_id === parentItem.id),
      ]
      toast.success(children.length > 0 ? 'Комплект добавлен в корзину' : 'Добавлено в корзину')
      return group
    } catch (error: unknown) {
      if (failureStatus(error) === 401) {
        authStore.logoutLocal()
        options.onAuthRequired?.()
      } else {
        toast.error(failureMessage(error, 'Не удалось добавить комплект в корзину'))
      }
      return null
    } finally {
      replaceSetValue(pendingCartIds, parent.id, false)
    }
  }

  const removeStandaloneCartProduct = async (productId: UUID): Promise<boolean> => {
    if (overlayLoading.value || pendingCartIds.value.has(productId)) return false
    replaceSetValue(pendingCartIds, productId, true)
    try {
      await shellStore.removeStandaloneCartProduct(productId)
      toast.success('Удалено из корзины')
      return true
    } catch (error: unknown) {
      if (failureStatus(error) === 401) {
        authStore.logoutLocal()
        options.onAuthRequired?.()
      } else {
        toast.error(failureMessage(error, 'Не удалось изменить корзину'))
      }
      return false
    } finally {
      replaceSetValue(pendingCartIds, productId, false)
    }
  }

  const getCartGroup = (productId: UUID): SpecialEquipmentCartItem[] | null => {
    const parent = shellStore.cartItems.find(item => (
      item.product_id === productId && item.parent_item_id === null
    ))
    if (!parent) return null
    return [
      parent,
      ...shellStore.cartItems.filter(item => item.parent_item_id === parent.id),
    ]
  }

  const handleAuthenticated = async () => {
    await authStore.checkAuth(true)
    await mergeGuestState()
  }

  onMounted(async () => {
    if (authStore.isAuthenticated) await loadAuthenticatedOverlay()
    else loadGuestState()
  })

  watch(() => authStore.isAuthenticated, async (isAuthenticated, wasAuthenticated) => {
    if (isAuthenticated && !wasAuthenticated) await mergeGuestState()
    if (!isAuthenticated && wasAuthenticated) loadGuestState()
  })

  return {
    favoriteIds: readonly(favoriteIds),
    cartIds,
    pendingFavoriteIds: readonly(pendingFavoriteIds),
    pendingCartIds: readonly(pendingCartIds),
    overlayLoading: readonly(overlayLoading),
    isFavorite: (productId: UUID) => favoriteIds.value.has(productId),
    isInCart: (productId: UUID) => cartIds.value.has(productId),
    isStandaloneInCart: (productId: UUID) => shellStore.hasStandaloneCartProduct(productId),
    isFavoritePending: (productId: UUID) => pendingFavoriteIds.value.has(productId),
    isCartPending: (productId: UUID) =>
      overlayLoading.value || pendingCartIds.value.has(productId),
    toggleFavorite,
    toggleCart,
    ensureCartItem,
    addCartGroup,
    getCartGroup,
    removeStandaloneCartProduct,
    handleAuthenticated,
    refreshOverlay: loadAuthenticatedOverlay,
  }
}
