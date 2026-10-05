<template><DealerClientsPanel /></template>
<script setup lang="ts">
const DealerClientsPanel = defineAsyncComponent(() => import('~/features/dealer/components/DealerClientsPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
