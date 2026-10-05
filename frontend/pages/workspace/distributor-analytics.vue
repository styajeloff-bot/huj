<template>
  <DistributorAnalyticsDashboard />
</template>

<script setup lang="ts">
import DistributorAnalyticsDashboard from '~/features/distributor/components/DistributorAnalyticsDashboard.vue'

definePageMeta({
  layout: 'workspace',
  middleware: ['auth', 'require-workspace'],
})

useHead({
  title: 'Аналитика - CarCraft Multileasing',
})
</script>
