<template>
  <SpecialEquipmentCatalogPage
    v-if="context.kind === 'category'"
    :category-path="context.categoryPath"
  />
  <SpecialEquipmentProductPage
    v-else-if="context.kind === 'product'"
    :category-path="context.categoryPath"
    :product-id="context.productId"
    :product-slug="context.productSlug"
  />
</template>

<script setup lang="ts">
import { parseSpecialEquipmentContextRoute } from '../categoryNavigation'
import SpecialEquipmentCatalogPage from './SpecialEquipmentCatalogPage.vue'
import SpecialEquipmentProductPage from './SpecialEquipmentProductPage.vue'

const route = useRoute()
const context = computed(() => parseSpecialEquipmentContextRoute(route.params.segments))

if (context.value.kind === 'invalid') {
  throw createError({
    statusCode: 404,
    statusMessage: 'Раздел каталога не найден',
    fatal: true,
  })
}

watch(context, nextContext => {
  if (nextContext.kind !== 'invalid') return
  showError({ statusCode: 404, statusMessage: 'Раздел каталога не найден' })
})
</script>
