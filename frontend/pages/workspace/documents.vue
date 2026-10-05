<template><DocumentManager /></template>
<script setup lang="ts">
const DocumentManager = defineAsyncComponent(() => import('~/features/documents/components/DocumentManager.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
