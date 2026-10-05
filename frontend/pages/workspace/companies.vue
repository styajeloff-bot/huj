<template>
  <CompaniesAdminPanel v-if="authStore.isCarCraftEmployee" />
  <DealerGroupsPanel v-else-if="authStore.isDistributor" distributor-mode />
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'

const CompaniesAdminPanel = defineAsyncComponent(() => import('~/features/admin/companies/manage/components/CompaniesAdminPanel.vue'))
const DealerGroupsPanel = defineAsyncComponent(() => import('~/features/admin/companies/manage/components/DealerGroupsPanel.vue'))

const authStore = useAuthStore()

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })

onMounted(() => {
  if (!authStore.isCarCraftEmployee && !authStore.isDistributor) {
    navigateTo('/workspace')
  }
})
</script>
