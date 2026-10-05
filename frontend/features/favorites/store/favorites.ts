import {
  createFavoritesApi,
  hasFavoriteVehicleId,
  normalizeFavoriteItem,
  type FavoriteItem,
} from '../api/favoritesApi'
import { createCarsApi } from '~/features/cars/api/carsApi'
import { useStorefront } from '~/features/storefront'
import type { UUID } from '~/types/ids'

const getCarsList = (response: unknown): Record<string, unknown>[] => {
  const payload = response && typeof response === 'object'
    ? response as { items?: unknown; vehicles?: unknown }
    : null
  const list = Array.isArray(response) ? response : payload?.items ?? payload?.vehicles ?? []
  return Array.isArray(list) ? list : []
}

const enrichFavoritesWithCars = async (
  favorites: FavoriteItem[],
  loadCars: (vehicleIds: UUID[]) => Promise<unknown>,
): Promise<FavoriteItem[]> => {
  if (favorites.length === 0) {
    return []
  }

  const vehicleIds = favorites.map((favorite) => favorite.vehicle_id)

  try {
    const response = await loadCars(vehicleIds)
    const cars = getCarsList(response)
    const carsByVehicleId = new Map<UUID, Record<string, unknown>>(
      cars
        .filter(hasFavoriteVehicleId)
        .map((car) => [car.vehicle_id, car] as const)
    )

    return favorites.map((favorite) => {
      const fullCar = carsByVehicleId.get(favorite.vehicle_id)
      if (!fullCar) {
        return favorite
      }

      return normalizeFavoriteItem({
        ...favorite,
        ...fullCar,
        id: favorite.id,
        vehicle_id: favorite.vehicle_id,
        added_at: favorite.added_at,
      })
    })
  } catch {
    return favorites
  }
}

export const useFavoritesStore = defineStore('favorites', () => {
  const items = ref<FavoriteItem[]>([])
  const loading = ref(false)
  const guestIds = ref<UUID[]>([])
  const guestItems = ref<FavoriteItem[]>([])
  const config = useRuntimeConfig()
  const { apiPath, storageKey } = useStorefront()
  const favoritesApi = createFavoritesApi(config, apiPath)
  const carsApi = createCarsApi(config, apiPath)
  const GUEST_FAVORITES_KEY = computed(() => storageKey('guest-favorites'))

  const count = computed(() => items.value.length)
  const isEmpty = computed(() => items.value.length === 0)
  const guestCount = computed(() => guestIds.value.length)

  // Guest favorites (localStorage-based for non-authenticated users)
  const loadGuestFavorites = () => {
    if (typeof window === 'undefined') return
    try {
      const stored = localStorage.getItem(GUEST_FAVORITES_KEY.value)
      const parsed: unknown = stored ? JSON.parse(stored) : []
      guestIds.value = Array.isArray(parsed)
        ? parsed.filter((id): id is UUID => typeof id === 'string' && id.length > 0)
        : []
    } catch {
      guestIds.value = []
    }
  }

  const saveGuestFavorites = () => {
    if (typeof window === 'undefined') return
    localStorage.setItem(GUEST_FAVORITES_KEY.value, JSON.stringify(guestIds.value))
  }

  const addToGuestFavorites = (vehicleId: UUID) => {
    if (!guestIds.value.includes(vehicleId)) {
      guestIds.value.push(vehicleId)
      saveGuestFavorites()
    }
  }

  const removeFromGuestFavorites = (vehicleId: UUID) => {
    guestIds.value = guestIds.value.filter((id) => id !== vehicleId)
    guestItems.value = guestItems.value.filter(
      (item) => item.vehicle_id !== vehicleId
    )
    saveGuestFavorites()
  }

  const isInGuestFavorites = (vehicleId: UUID) => {
    return guestIds.value.includes(vehicleId)
  }

  const fetchGuestFavorites = async () => {
    loadGuestFavorites() // sync from localStorage in case of SSR hydration mismatch
    if (guestIds.value.length === 0) {
      guestItems.value = []
      return
    }
    try {
      // Batch-read: GET /api/v1/cars?ids=1&ids=2 (Phase 11 R9).
      const response = await carsApi.getCars({ ids: guestIds.value })
      const list = getCarsList(response)
      guestItems.value = list
        .filter(hasFavoriteVehicleId)
        .map((vehicle) => normalizeFavoriteItem(vehicle))
    } catch {
      guestItems.value = []
    }
  }

  const mergeGuestFavorites = async () => {
    // Always clear guest state first — ensures localStorage is clean after any login
    const idsToMerge = [...guestIds.value]
    guestIds.value = []
    guestItems.value = []
    if (typeof window !== 'undefined') {
      localStorage.removeItem(GUEST_FAVORITES_KEY.value)
    }

    if (idsToMerge.length === 0) return

    // Silently push each ID to the DB; allSettled so individual 404/403 don't throw
    await Promise.allSettled(
      idsToMerge.map((id) => favoritesApi.addFavorite(id))
    )
    await fetchFavorites()
  }

  const fetchFavorites = async () => {
    loading.value = true
    try {
      const response = await favoritesApi.getFavorites()
      const normalizedFavorites = response.favorites
        .filter(hasFavoriteVehicleId)
        .map((favorite) => normalizeFavoriteItem(favorite))
      items.value = await enrichFavoritesWithCars(
        normalizedFavorites,
        (ids) => carsApi.getCars({ ids }),
      )
    } catch (error) {
      console.error('Error fetching favorites:', error)
      items.value = []
    } finally {
      loading.value = false
    }
  }

  const addToFavorites = async (vehicleId: UUID) => {
    try {
      await favoritesApi.addFavorite(vehicleId)
      await fetchFavorites()
      return { success: true }
    } catch (error: unknown) {
      const msg = (error as { data?: { error?: string } }).data?.error || ''
      if (msg.includes('уже в избранном')) {
        await fetchFavorites()
        return { success: true }
      }
      return { success: false }
    }
  }

  const removeFromFavorites = async (vehicleId: UUID) => {
    try {
      await favoritesApi.removeFavorite(vehicleId)
      items.value = items.value.filter(
        (item) => item.vehicle_id !== vehicleId
      )
      return { success: true }
    } catch (error) {
      return { success: false }
    }
  }

  const isInFavorites = (vehicleId: UUID) => {
    return items.value.some(
      (item) => item.vehicle_id === vehicleId
    )
  }

  const clearFavorites = async () => {
    try {
      await favoritesApi.clearFavorites()
      items.value = []
      return { success: true }
    } catch (error) {
      return { success: false }
    }
  }

  const bulkRemoveFavorites = async (vehicleIds: UUID[]) => {
    await favoritesApi.bulkRemoveFavorites(vehicleIds)
    await fetchFavorites()
  }

  if (typeof window !== 'undefined') {
    loadGuestFavorites()
  }

  return {
    items,
    loading,
    count,
    isEmpty,
    guestIds,
    guestItems,
    guestCount,
    fetchFavorites,
    fetchGuestFavorites,
    addToFavorites,
    removeFromFavorites,
    isInFavorites,
    clearFavorites,
    bulkRemoveFavorites,
    loadGuestFavorites,
    addToGuestFavorites,
    removeFromGuestFavorites,
    isInGuestFavorites,
    mergeGuestFavorites,
  }
})
