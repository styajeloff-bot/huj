<template><LeasingDocumentRequirementsPanel /></template>
<script setup lang="ts">
const LeasingDocumentRequirementsPanel = defineAsyncComponent(() => import('~/features/leasing/components/LeasingDocumentRequirementsPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
