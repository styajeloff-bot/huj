<template>
  <div class="[overflow-anchor:none] [overflow-wrap:anywhere]">
    <StorefrontPageRenderer :layout="pageLayout">
      <template #fallback>
        <SpecialEquipmentCatalogPage />
      </template>
    </StorefrontPageRenderer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import SpecialEquipmentCatalogPage from '~/features/specialEquipment/components/SpecialEquipmentCatalogPage.vue'
import { useStorefront } from '~/features/storefront'
import { StorefrontPageRenderer } from '~/features/storefrontBuilder'
import { useStorefrontPagesApi } from '~/features/storefrontBuilder/api/storefrontPagesApi'

const { slug } = useStorefront()
const pagesApi = useStorefrontPagesApi()

const { data: pageData } = await useAsyncData(
  () => `storefront-page-special-equipment-${slug.value || 'default'}`,
  async () => {
    try {
      return await pagesApi.getPublicPage(slug.value || '', 'special_equipment_catalog')
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

useHead(() => ({
  title:
    pageData.value?.layout?.settings?.title ||
    'Каталог спецтехники - CarCraft Multileasing',
  meta: [
    {
      name: 'description',
      content:
        pageData.value?.layout?.settings?.description ||
        'Каталог специальной техники в лизинг для бизнеса. Выгодные условия, быстрое одобрение.',
    },
  ],
}))
</script>
