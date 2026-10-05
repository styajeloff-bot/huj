<template><DealerReportsPanel /></template>
<script setup lang="ts">
const DealerReportsPanel = defineAsyncComponent(() => import('~/features/dealer/components/DealerReportsPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
