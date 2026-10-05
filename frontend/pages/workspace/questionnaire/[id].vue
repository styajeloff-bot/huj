<template>
  <QuestionnairePage workspace />
</template>

<script setup lang="ts">
import QuestionnairePage from '~/features/questionnaire/components/QuestionnairePage.vue'
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'], key: route => route.fullPath })
</script>
