<template>
  <SpecialEquipmentImportPage />
</template>

<script setup lang="ts">
import SpecialEquipmentImportPage from '~/features/specialEquipmentImport/components/SpecialEquipmentImportPage.vue'

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace', 'require-special-equipment-import'] })
</script>
