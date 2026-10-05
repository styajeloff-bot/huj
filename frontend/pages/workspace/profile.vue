<template>
  <component :is="panel" v-if="panel" />
</template>
<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })

const EmployeeProfilePanel = defineAsyncComponent(() => import('~/features/admin/profile/components/EmployeeProfilePanel.vue'))
const DealerProfilePanel = defineAsyncComponent(() => import('~/features/dealer/components/DealerProfilePanel.vue'))
const DistributorProfilePanel = defineAsyncComponent(() => import('~/features/distributor/components/DistributorProfilePanel.vue'))
const LeasingCompanyProfilePanel = defineAsyncComponent(() => import('~/features/leasing/components/LeasingCompanyProfilePanel.vue'))

const authStore = useAuthStore()

if (authStore.isCarCraftEmployee) {
  await navigateTo('/workspace', { replace: true })
}

const panel = computed(() => {
  if (authStore.isDealer) return DealerProfilePanel
  if (authStore.isDistributor) return DistributorProfilePanel
  if (authStore.isLeasingCompany) return LeasingCompanyProfilePanel
  return null
})
</script>
