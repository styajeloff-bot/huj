<template>
  <div class="[overflow-anchor:none] [overflow-wrap:anywhere]">
    <StorefrontPageRenderer :layout="pageLayout">
      <template #fallback>
        <HeroBanner />
        <SpecialEquipmentHomepageModule v-if="isSpecialEquipmentCatalogVisible" />
        <Advantages />
        <LeasingCalculator />
        <HowToGetCar />
        <FAQ />
        <LeasingCompanies />
      </template>
    </StorefrontPageRenderer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LeasingCalculator from '~/features/calculator/components/LeasingCalculator.vue'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import SpecialEquipmentHomepageModule from '~/features/specialEquipment/components/SpecialEquipmentHomepageModule.vue'
import { useStorefront } from '~/features/storefront'
import { StorefrontPageRenderer } from '~/features/storefrontBuilder'
import { useStorefrontPagesApi } from '~/features/storefrontBuilder/api/storefrontPagesApi'

const { slug } = useStorefront()
const pagesApi = useStorefrontPagesApi()

const { data: pageData } = await useAsyncData(
  () => `storefront-page-home-${slug.value || 'default'}`,
  async () => {
    try {
      return await pagesApi.getPublicPage(slug.value || '', 'home')
    } catch (_e) {
      return null
    }
  },
  {
    watch: [slug],
  },
)

const pageLayout = computed(() => {
  if (!pageData.value || pageData.value.fallback_layout || !pageData.value.layout) {
    return null
  }
  return pageData.value.layout
})

const visibilityStore = useSectionVisibilityStore()
const isSpecialEquipmentCatalogVisible = computed(() =>
  visibilityStore.isSectionVisible('public', 'special_equipment_catalog'),
)

useHead(() => ({
  title: pageData.value?.layout?.settings?.title || 'CarCraft Multileasing - Лизинговая платформа для дилеров',
  meta: [
    {
      name: 'description',
      content:
        pageData.value?.layout?.settings?.description ||
        'Оформите лизинг на автомобили через нашу платформу. Быстро, удобно, выгодно.',
    },
    { name: 'robots', content: 'noindex' },
  ],
}))
</script>

