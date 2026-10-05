<template>
  <div class="max-w-3xl"><SecurityPanel /></div>
</template>
<script setup lang="ts">
const SecurityPanel = defineAsyncComponent(() => import('~/features/auth/components/SecurityPanel.vue'))
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
