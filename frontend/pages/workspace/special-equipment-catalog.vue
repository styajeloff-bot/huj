<template>
  <CatalogCorrectionRegistryPage />
</template>

<script setup lang="ts">
import CatalogCorrectionRegistryPage from '~/features/specialEquipment/management/correction/CatalogCorrectionRegistryPage.vue'

definePageMeta({
  layout: 'workspace',
  middleware: ['auth', 'require-workspace', 'require-special-equipment-catalog'],
})
</script>
