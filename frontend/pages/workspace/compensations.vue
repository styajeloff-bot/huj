<template>
  <div />
</template>

<script setup lang="ts">
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })

const route = useRoute()
await navigateTo({
  path: '/workspace/support',
  query: {
    ...route.query,
    tab: 'compensations',
  },
}, { replace: true })
</script>
