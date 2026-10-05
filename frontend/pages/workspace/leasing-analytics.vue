<template>
  <AnalyticsDashboard />
</template>

<script setup lang="ts">
import AnalyticsDashboard from '~/features/leasing/components/AnalyticsDashboard.vue'

definePageMeta({
  layout: 'workspace',
  middleware: ['auth', 'require-workspace'],
})
</script>
