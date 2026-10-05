<template>
  <SupportPanel
    :readonly="true"
    :fetch-fn="fetchDistributorSupportPrograms"
    :deep-link-target="deepLinkTarget"
  />
</template>

<script setup lang="ts">
import SupportPanel from '~/features/support/components/SupportPanel.vue'
import type { Pagination, SupportProgram } from '~/types/admin'
import { readSupportDeepLinkTarget } from '~/utils/supportDeepLink'

const config = useRuntimeConfig()
const route = useRoute()
const deepLinkTarget = computed(() => readSupportDeepLinkTarget(route.query))

type SupportProgramListResponse = {
  items: SupportProgram[]
  pagination: Pagination
}

const requestPrograms = (params: Record<string, string>) => {
  const query = new URLSearchParams(params).toString()
  return $fetch<SupportProgramListResponse>(`/api/v1/distributor/support-programs?${query}`, {
    baseURL: config.public.apiBase,
    credentials: 'include',
  })
}

const fetchDistributorSupportPrograms = requestPrograms
</script>
