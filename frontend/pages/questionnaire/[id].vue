<template>
  <ApplicationWorkflowPage questionnaire-page />
</template>

<script setup lang="ts">
import { ApplicationWorkflowPage } from '~/features/checkout'
definePageMeta({
  middleware: ['auth', 'questionnaire-workspace'],
  key: route => `${route.path}:${route.query.notification_company_id || ''}`,
})
</script>
