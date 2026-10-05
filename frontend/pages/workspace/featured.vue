<template><AdminFeaturedPanel /></template>
<script setup lang="ts">
const AdminFeaturedPanel = defineAsyncComponent(() => import('~/features/admin/featured/components/AdminFeaturedPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
