<template><AdminUsersPanel /></template>
<script setup lang="ts">
const AdminUsersPanel = defineAsyncComponent(() => import('~/features/admin/users/components/AdminUsersPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
