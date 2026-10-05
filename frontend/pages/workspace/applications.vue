<template>
  <AdminApplicationsPanel v-if="authStore.isCarCraftEmployee" />
  <MyApplicationsPanel v-else-if="authStore.isDealer || authStore.isDistributor" />
  <div v-else class="rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
    Раздел заявок доступен сотрудникам CarCraft, дилерам и дистрибьюторам.
  </div>
</template>
<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'

const AdminApplicationsPanel = defineAsyncComponent(() => import('~/features/admin/applications/components/AdminApplicationsPanel.vue'))
const MyApplicationsPanel = defineAsyncComponent(() => import('~/features/applications/components/MyApplicationsPanel.vue'))
const authStore = useAuthStore()
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
</script>
