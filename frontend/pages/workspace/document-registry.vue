<template>
  <DocumentRegistryWorkspace v-if="roleAllowed" :key="contextKey" :api="api" :can-manage="auth.isCarCraftEmployee" :document-id="documentId" @open="openDocument" @close-document="closeDocument" />
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useHydrationReady } from '~/composables/useHydrationReady'
import { useAuthStore } from '~/features/auth/store/auth'
import { DocumentRegistryWorkspace, createDocumentRegistryApi } from '~/features/documentRegistry'
import { provideNotificationCompanyContext } from '~/features/notifications'
import { isBusinessRoleName } from '~/features/workspace/config/menu'
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })
const auth = useAuthStore(); const route = useRoute(); const router = useRouter()
const hydrationReady = useHydrationReady()
const roleAllowed = computed(() => hydrationReady.value && isBusinessRoleName(auth.userRole))
const documentId = computed(() => typeof route.query.document === 'string' ? route.query.document : undefined)
const companyContext = provideNotificationCompanyContext(() => route.query.notification_company_id)
const api = createDocumentRegistryApi(useRuntimeConfig(), companyContext)
const contextKey = computed(() => JSON.stringify([auth.userRole, auth.user?.company_id, route.query.notification_company_id]))
const openDocument = (id: string) => router.push({ query: { ...route.query, document: id } })
const closeDocument = () => { const query = { ...route.query }; delete query.document; return router.replace({ query }) }
</script>
