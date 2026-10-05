<template><WarehousesPanel /></template>
<script setup lang="ts">
const WarehousesPanel = defineAsyncComponent(() => import('~/features/admin/warehouses/components/WarehousesPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
