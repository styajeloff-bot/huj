export function useStorefrontCanonical(): void {
  const route = useRoute()
  const config = useRuntimeConfig()
  const canonical = computed(() => new URL(route.path, config.public.siteUrl).toString())

  useHead({
    link: [
      { rel: 'canonical', href: canonical },
    ],
  })
}
