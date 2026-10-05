/**
 * True when auth-dependent markup can safely use the client session.
 *
 * The application intentionally resolves authentication on the client. During
 * the initial SSR hydration pass, server markup therefore represents an
 * anonymous session. Keeping auth-dependent branches neutral until mount makes
 * the first client render identical. Client-side navigations are ready
 * immediately and do not incur an extra placeholder frame.
 */
export const useHydrationReady = () => {
  const nuxtApp = useNuxtApp()
  const ready = ref(import.meta.client && !nuxtApp.isHydrating)

  onMounted(() => {
    ready.value = true
  })

  return computed(() => ready.value)
}
