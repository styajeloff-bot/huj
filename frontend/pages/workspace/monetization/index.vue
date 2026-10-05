<template>
  <MonetizationWorkspace v-if="role" :key="contextKey" :api="api" :role="role" :target="target" @navigate="navigate" />
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'
import MonetizationWorkspace from '~/features/monetization/components/MonetizationWorkspace.vue'
import { createMonetizationApi } from '~/features/monetization/api'
import { monetizationQuery, monetizationTarget, type MonetizationTarget } from '~/features/monetization/routes'
import type { Role } from '~/features/monetization/types'
import { isUuid } from '~/types/ids'
import type { LocationQueryRaw } from 'vue-router'

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const notificationCompanyId = computed(() => isUuid(route.query.notification_company_id) ? route.query.notification_company_id : undefined)
const leasingCompanyId = computed(() => isUuid(route.query.leasing_company_id) ? route.query.leasing_company_id : undefined)
const api = createMonetizationApi(useRuntimeConfig(), () => notificationCompanyId.value, () => leasingCompanyId.value)
const target = computed(() => monetizationTarget(route.query))
const role = computed<Role | null>(() => {
  const value = auth.userRole
  return value === 'carcraft_employee' || value === 'dealer' || value === 'distributor' || value === 'leasing_company' ? value : null
})
const contextKey = computed(() => JSON.stringify([role.value, auth.user?.company_id, notificationCompanyId.value, leasingCompanyId.value]))
const navigate = (value: MonetizationTarget) => router.push({ query: monetizationQuery(route.query, value) as LocationQueryRaw })
</script>
