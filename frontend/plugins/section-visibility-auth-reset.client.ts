import { useAuthStore } from '~/features/auth/store/auth'
import { createSectionVisibilityAuthIdentityTracker } from '~/features/sectionVisibility/authIdentity'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'

export default defineNuxtPlugin(() => {
  const authStore = useAuthStore()
  const visibilityStore = useSectionVisibilityStore()
  const trackIdentity = createSectionVisibilityAuthIdentityTracker(
    visibilityStore.resetAuthenticated,
  )

  watch(
    () => authStore.user
      ? {
          id: typeof authStore.user?.id === 'string' ? authStore.user.id : null,
          role: typeof authStore.user?.role === 'string' ? authStore.user.role : null,
        }
      : null,
    trackIdentity,
    { immediate: true, flush: 'sync' },
  )
})
