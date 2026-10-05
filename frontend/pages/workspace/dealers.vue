<template><DistributorDealersPanel /></template>
<script setup lang="ts">
const DistributorDealersPanel = defineAsyncComponent(() => import('~/features/distributor/components/DistributorDealersPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
