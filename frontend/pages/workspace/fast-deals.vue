<template>
  <NuxtPage v-if="isDetailRoute" />
  <FastDealsListPanel v-else />
</template>

<script setup lang="ts">
const FastDealsListPanel = defineAsyncComponent(() => import('~/features/fast-deals/components/FastDealsListPanel.vue'))
const route = useRoute()
// `/workspace/fast-deals` is the list; `/workspace/fast-deals/<id>` is rendered by the child page (the card).
const isDetailRoute = computed(() => route.path.replace(/\/+$/, '') !== '/workspace/fast-deals')

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
