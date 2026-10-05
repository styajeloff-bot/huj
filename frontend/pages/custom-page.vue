<template>
  <div class="[overflow-anchor:none] [overflow-wrap:anywhere]">
    <StorefrontPageRenderer v-if="pageLayout" :layout="pageLayout" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useStorefront } from '~/features/storefront'
import { StorefrontPageRenderer } from '~/features/storefrontBuilder'
import { useStorefrontPagesApi } from '~/features/storefrontBuilder/api/storefrontPagesApi'
import { isReservedRouteSlug } from '~/features/storefront/routeManifest'

const route = useRoute()
const storefront = useStorefront()
const pagesApi = useStorefrontPagesApi()

const pageSlug = computed(() => {
  const param = route.params.pageSlug
  if (Array.isArray(param)) return param[0] || ''
  return (param as string) || ''
})

const effectiveStorefrontSlug = computed(() => {
  const param = route.params.storefrontSlug
  if (param) {
    return Array.isArray(param) ? param[0] : (param as string)
  }
  return storefront.slug.value || ''
})

if (!pageSlug.value || isReservedRouteSlug(pageSlug.value)) {
  showError({
    statusCode: 404,
    message: 'Страница не найдена',
    statusMessage: 'Страница не найдена',
    fatal: true,
  })
}

const { data: pageData, error } = await useAsyncData(
  () => `custom-page-${effectiveStorefrontSlug.value || 'default'}-${pageSlug.value}`,
  async () => {
    try {
      return await pagesApi.getPublicPage(
        effectiveStorefrontSlug.value,
        pageSlug.value,
      )
    } catch (_e) {
      return null
    }
  },
  {
    watch: [effectiveStorefrontSlug, pageSlug],
  },
)

const pageLayout = computed(() => {
  if (!pageData.value || pageData.value.fallback_layout || !pageData.value.layout) {
    return null
  }
  return pageData.value.layout
})

if (!pageLayout.value || error.value) {
  showError({
    statusCode: 404,
    message: 'Страница не найдена',
    statusMessage: 'Страница не найдена',
    fatal: true,
  })
}

useHead(() => ({
  title:
    pageData.value?.layout?.settings?.title ||
    pageData.value?.title ||
    'Страница витрины',
  meta: [
    ...(pageData.value?.layout?.settings?.description
      ? [
          {
            name: 'description',
            content: String(pageData.value.layout.settings.description),
          },
        ]
      : []),
    ...(pageData.value?.layout?.settings?.keywords
      ? [
          {
            name: 'keywords',
            content: String(pageData.value.layout.settings.keywords),
          },
        ]
      : []),
  ],
}))
</script>
