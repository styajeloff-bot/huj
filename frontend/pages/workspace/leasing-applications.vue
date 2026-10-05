<template>
  <NuxtPage v-if="isDetailRoute" />
  <LeasingApplicationsPanel v-else />
</template>

<script setup lang="ts">
const LeasingApplicationsPanel = defineAsyncComponent(() => import('~/features/leasing/components/LeasingApplicationsPanel.vue'))
const route = useRoute()
const isDetailRoute = computed(() => route.path !== '/workspace/leasing-applications')

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
