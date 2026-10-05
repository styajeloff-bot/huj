import { useAuthStore } from '~/features/auth/store/auth'

export default defineNuxtPlugin(async () => {
  const authStore = useAuthStore()
  await authStore.checkAuth()
})
