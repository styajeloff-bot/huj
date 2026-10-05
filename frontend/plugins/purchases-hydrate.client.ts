import { useAuthStore } from '~/features/auth/store/auth'

export default defineNuxtPlugin(() => {
  const authStore = useAuthStore()
  const purchasesStore = usePurchasesStore()

  const shouldLoad = () => authStore.isAuthenticated && authStore.hasScope('purchases:read')

  if (shouldLoad()) {
    purchasesStore.loadMyVehicleIds()
  }

  watch(() => authStore.isAuthenticated, () => {
    if (shouldLoad()) {
      purchasesStore.loadMyVehicleIds()
    }
  })
})
