<template>
  <div data-storefront-block="client.application" class="mx-auto w-full max-w-6xl space-y-5 px-6 py-8">
    <nav class="flex flex-wrap items-center gap-5 text-sm" aria-label="Навигация анкеты">
      <NuxtLink :to="backLocation" class="text-[color:var(--storefront-link,#2563eb)] underline">Вернуться к заявке</NuxtLink>
      <a v-if="available" href="#questionnaire-documents" class="text-[color:var(--storefront-link,#2563eb)] underline">Документы заявки</a>
    </nav>
    <ApplicationQuestionnaire v-if="validApplicationId" :application-id="applicationId" :leasing-company-id="leasingCompanyId" @loaded="available = $event" />
    <div v-else class="rounded-lg border border-red-200 p-5 text-red-700" role="alert">Некорректный идентификатор заявки.</div>
    <QuestionnaireFiles v-if="available" id="questionnaire-documents" :application-id="applicationId" :leasing-company-id="leasingCompanyId" />
  </div>
</template>

<script setup lang="ts">
import ApplicationQuestionnaire from './ApplicationQuestionnaire.vue'
import QuestionnaireFiles from './QuestionnaireFiles.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { useQuestionnaireNavigation } from '~/features/questionnaire/composables/useQuestionnaireNavigation'
import { provideNotificationCompanyContext } from '~/features/notifications'
import { useStorefront } from '~/features/storefront'
import { isUuid } from '~/types/ids'

const props = defineProps<{ workspace?: boolean }>()
const route = useRoute()
const authStore = useAuthStore()
const available = ref(false)
provideNotificationCompanyContext(() => route.query.notification_company_id)
const { applicationLocation } = useQuestionnaireNavigation()
const { publicRoute } = useStorefront()
const applicationId = computed(() => typeof route.params.id === 'string' ? route.params.id : '')
const validApplicationId = computed(() => isUuid(applicationId.value))
const leasingCompanyId = computed(() => isUuid(route.query.leasing_company_id) ? route.query.leasing_company_id : undefined)
const backLocation = computed(() => validApplicationId.value ? applicationLocation(applicationId.value, props.workspace === true) : authStore.isLeasingCompany ? '/workspace/leasing-applications' : props.workspace ? '/workspace/applications' : publicRoute('/cabinet'))
useHead({ title: 'Анкета клиента' })
</script>
