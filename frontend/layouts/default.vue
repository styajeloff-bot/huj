<template>
  <div
    class="storefront-theme min-h-screen bg-storefront-background text-storefront-text"
    :style="rootStyle"
  >
    <TheHeader />
    <main class="min-h-screen pt-28">
      <slot />
    </main>
    <TheFooter />
    <ToastNotifications />
  </div>
</template>

<script setup lang="ts">
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { useStorefrontCanonical } from '~/features/storefront/composables/useStorefrontCanonical'
import { useStorefront, useStorefrontTheme } from '~/features/storefront'

const visibilityStore = useSectionVisibilityStore()
const { id, slug, is_resolved } = useStorefront()
const { rootStyle } = useStorefrontTheme()
useStorefrontCanonical()

const loadPublicVisibility = async (): Promise<void> => {
  if (is_resolved.value && id.value) {
    await visibilityStore.loadPublic(id.value, slug.value)
  }
}

await loadPublicVisibility()

watch([id, slug, is_resolved], ([nextId, nextSlug, resolved], [previousId]) => {
  if (!resolved || !nextId || nextId === previousId) return
  void visibilityStore.loadPublic(nextId, nextSlug)
})
</script>
