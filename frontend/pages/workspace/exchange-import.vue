<template><AdminExchangeImportPanel /></template>
<script setup lang="ts">
const AdminExchangeImportPanel = defineAsyncComponent(() => import('~/features/admin/exchange/components/AdminExchangeImportPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
