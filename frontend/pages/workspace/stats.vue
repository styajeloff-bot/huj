<template><AdminStatsPanel /></template>
<script setup lang="ts">
const AdminStatsPanel = defineAsyncComponent(() => import('~/features/admin/stats/components/AdminStatsPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
