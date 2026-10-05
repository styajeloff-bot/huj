<template>
  <SupportAdminPanel v-if="authStore.isCarCraftEmployee" />
  <SupportWorkspacePanel
    v-else-if="panel"
    :support-panel="panel"
    :compensation-panel="CompensationRegistryPanel"
  />
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })

const SupportAdminPanel = defineAsyncComponent(() => import('~/features/admin/support/components/SupportAdminPanel.vue'))
const DistributorSupportPanel = defineAsyncComponent(() => import('~/features/distributor/support/components/DistributorSupportPanel.vue'))
const OrganizationSupportPanel = defineAsyncComponent(() => import('~/features/support/components/OrganizationSupportPanel.vue'))
const SupportWorkspacePanel = defineAsyncComponent(() => import('~/features/support/components/SupportWorkspacePanel.vue'))
const CompensationRegistryPanel = defineAsyncComponent(() => import('~/features/compensations/components/CompensationRegistryPanel.vue'))

const authStore = useAuthStore()
const panel = computed(() => {
  if (authStore.isDistributor) return DistributorSupportPanel
  if (authStore.isDealer || authStore.isLeasingCompany) return OrganizationSupportPanel
  return null
})
</script>
