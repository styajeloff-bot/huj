<template>
  <component :is="panel" v-if="panel" />
</template>
<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })

const DealerExchangePanel = defineAsyncComponent(() => import('~/features/exchange/components/DealerExchangePanel.vue'))
const LcExchangePanel = defineAsyncComponent(() => import('~/features/exchange/components/LcExchangePanel.vue'))
const DistributorExchangePanel = defineAsyncComponent(() => import('~/features/exchange/components/DistributorExchangePanel.vue'))

const authStore = useAuthStore()
const panel = computed(() => {
  if (authStore.isDealer) return DealerExchangePanel
  if (authStore.isLeasingCompany) return LcExchangePanel
  if (authStore.isDistributor) return DistributorExchangePanel
  return null
})
</script>
