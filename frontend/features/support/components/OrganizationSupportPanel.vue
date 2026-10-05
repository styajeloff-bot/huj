<template>
  <SupportPanel
    :readonly="true"
    :fetch-fn="fetchOrganizationSupportPrograms"
    :deep-link-target="deepLinkTarget"
    title="Поддержки"
    loading-text="Загружаем доступные поддержки..."
    empty-text="Для вашей организации поддержки не найдены"
  />
</template>

<script setup lang="ts">
import type { Pagination, SupportProgram } from '~/types/admin'
import SupportPanel from '~/features/support/components/SupportPanel.vue'
import { readSupportDeepLinkTarget } from '~/utils/supportDeepLink'

const config = useRuntimeConfig()
const route = useRoute()
const deepLinkTarget = computed(() => readSupportDeepLinkTarget(route.query))

type SupportProgramListResponse = {
  items: SupportProgram[]
  pagination: Pagination
}

const requestPrograms = (params: Record<string, string>) => {
  const apiParams = { ...params }
  if (apiParams.status === 'true' || apiParams.status === 'false') {
    apiParams.is_active = apiParams.status
  }
  delete apiParams.status
  const query = new URLSearchParams(apiParams).toString()
  return $fetch<SupportProgramListResponse>(`/api/v1/support-programs?${query}`, {
    baseURL: config.public.apiBase,
    credentials: 'include',
  })
}

const fetchOrganizationSupportPrograms = requestPrograms
</script>
