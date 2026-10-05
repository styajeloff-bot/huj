<template>
  <ApplicationWorkflowPage />
</template>

<script setup lang="ts">
import { ApplicationWorkflowPage } from '~/features/checkout'
definePageMeta({ key: route => `${route.path}:${route.query.notification_company_id || ''}` })
</script>
