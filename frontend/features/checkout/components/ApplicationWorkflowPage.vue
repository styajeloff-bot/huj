<template>
  <ApplicationItemsStep
    v-if="isItemsRoute"
    :items="checkoutStore.applicationItems"
    :loading="bootLoading"
    :saving="saving"
    :error="error"
    @save="saveApplicationItems"
    @back="returnToCompanySelection"
  />

  <div data-storefront-block="client.application" v-else class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-4 sm:py-6 md:py-8">
    <div class="mx-auto max-w-[1900px] px-3 sm:px-6 lg:px-8">
      <nav class="flex mb-4 sm:mb-8 overflow-x-auto" aria-label="Breadcrumb">
        <ol class="flex items-center space-x-2 sm:space-x-4 text-xs sm:text-sm whitespace-nowrap">
          <li>
            <NuxtLink :to="publicRoute('/')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">{{ pageTitle('home') }}</NuxtLink>
          </li>
          <li class="text-[color:var(--storefront-text,#d1d5db)]">/</li>
          <li v-if="isDistributedApplicationView">
            <NuxtLink :to="publicRoute('/cabinet')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">Личный кабинет</NuxtLink>
          </li>
          <li v-else-if="!isSingleCarMode">
            <NuxtLink :to="publicRoute('/cart')" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">Корзина</NuxtLink>
          </li>
          <li v-else>
            <NuxtLink :to="applicationBackLocation" class="text-[color:var(--storefront-link,#9ca3af)] hover:text-[color:var(--storefront-link-hover,#6b7280)]">{{ applicationBackLabel }}</NuxtLink>
          </li>
          <li class="text-[color:var(--storefront-text,#d1d5db)]">/</li>
          <li class="text-[color:var(--storefront-text-muted,#6b7280)]">{{ checkoutBreadcrumbCurrent }}</li>
        </ol>
      </nav>

      <div class="mb-6 md:mb-8">
        <h1 class="text-xl sm:text-2xl md:text-3xl font-bold text-[color:var(--storefront-title,#111827)]">
          {{ checkoutPageTitle }}
        </h1>
        <ApplicationSourceBadge v-if="application && canViewApplicationSource(authStore.userRole)" :source="application.source_type" class="mt-2" />
      </div>

      <div v-if="bootLoading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      </div>

      <div v-else-if="applicationLoadError" role="alert" class="rounded-md border border-[color:var(--storefront-error-border,#f87171)] bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] p-4 text-[color:var(--storefront-error-text,#b91c1c)]">
        <p>{{ applicationLoadError }}</p>
        <NuxtLink :to="publicRoute('/cabinet')" class="mt-3 inline-block underline">Вернуться в личный кабинет</NuxtLink>
      </div>

      <div v-else class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-sm p-4 sm:p-6 md:p-8">
        <div v-if="props.questionnairePage && application" class="mb-6 flex items-center justify-between gap-4">
          <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ applicationTitle }}</p>
          <NuxtLink
            :to="applicationStepPath(application.id, 'company')"
            class="shrink-0 text-sm font-medium text-[color:var(--storefront-link,#2563eb)] underline"
          >К заявке</NuxtLink>
        </div>
        <!-- Stepper -->
        <div class="mb-6 min-w-0 overflow-x-auto md:mb-8">
          <div class="flex min-w-max items-center">
            <div v-for="(step, index) in visibleCheckoutSteps" :key="step.section" class="contents">
              <div
                class="flex items-center"
                :data-testid="`application-step-${step.section === 'documents' ? 'documents' : step.num}`"
                :data-state="stepState(step.section)"
                :class="canJump(step.section) ? 'cursor-pointer' : 'cursor-default'"
                @click="jumpTo(step.section)"
              >
                <div
                  class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium transition-all"
                  :data-testid="`application-step-bubble-${step.section === 'documents' ? 'documents' : step.num}`"
                  :class="stepBubble(step.section)"
                >
                  <svg v-if="step.section !== 'documents' && stepState(step.section) === 'completed'" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  <span v-else>{{ step.section === 'documents' ? '!' : step.num }}</span>
                </div>
                <span
                  class="ml-3 text-sm font-medium"
                  :data-testid="`application-step-label-${step.section === 'documents' ? 'documents' : step.num}`"
                  :class="stepState(step.section) === 'current'
                    ? 'text-[color:var(--storefront-primary,#2563eb)]'
                    : 'text-[color:var(--storefront-text-muted,#4b5563)]'"
                >{{ step.label }}</span>
              </div>
              <div v-if="index < visibleCheckoutSteps.length - 1" class="flex-1 h-px bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] mx-4"></div>
            </div>
          </div>
        </div>

        <div v-if="error" class="mb-6 p-4 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)] rounded">
          {{ error }}
        </div>

        <div v-if="statusRouteNotice" role="status" class="mb-6 rounded-md border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-warning-text,#78350f)]">
          {{ statusRouteNotice }}
        </div>

        <div
          v-if="companyPermissionMessage && !isClientEditStepLocked"
          role="status"
          class="mb-6 rounded-md border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-warning-text,#78350f)]"
        >
          {{ companyPermissionMessage }}
          <button v-if="companyPermissionError" type="button" class="storefront-action-ghost ml-2 underline" @click="refreshCompanyPermissions">
            Повторить
          </button>
        </div>

        <div
          v-if="isWaitingForDistribution"
          class="mb-6 rounded-md border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-text,#1e3a8a)]"
        >
          Заявка отправлена. Ожидаем распределения в лизинговые компании.
        </div>

        <div
          v-else-if="isClientEditStepLocked && !statusRouteReadOnly"
          class="mb-6 rounded-md border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-warning-text,#78350f)]"
        >
          Заявка уже распределена в лизинговые компании. Данные доступны только для просмотра.
        </div>

        <section v-if="authStore.isDealer && application" class="mb-6 rounded-lg border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4">
          <h2 class="font-semibold text-[color:var(--storefront-title,#111827)]">Внутреннее согласование комиссии</h2>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Запросите дополнительную комиссию до направления заявки в первую лизинговую компанию.</p>
          <NuxtLink :to="{ path: '/workspace/monetization', query: { application: application.id, notification_company_id: notificationCompanyContext() } }" class="mt-3 inline-block text-sm font-medium text-[color:var(--storefront-link,#2563eb)] hover:text-[color:var(--storefront-link-hover,#1d4ed8)]">
            Согласовать комиссию с ЛК
          </NuxtLink>
        </section>

        <CommerceApplicationItemsSummary
          :items="checkoutStore.applicationItems"
          :items-count="applicationItemsCount"
          :total-items-price="applicationItemsPrice"
        />

        <fieldset
          class="min-w-0"
          :disabled="currentSection === 'questionnaire' && (isClientEditStepLocked || isWaitingForDistribution)"
          :class="currentSection === 'questionnaire' && (isClientEditStepLocked || isWaitingForDistribution) ? 'pointer-events-none opacity-75' : ''"
        >
          <CheckoutQuestionnaire
            v-if="currentSection === 'questionnaire'"
            ref="questionnaireRef"
            :readonly="!application || isClientEditStepLocked || isWaitingForDistribution || !canCreateCurrentApplication"
            :loading-company-data="loadingCompanyData"
            :company-external-data="companyExternalData"
            :company-id="applicationCompanyId"
            :autofilled-fields="autofilledFields"
            :initial-data="questionnaireData"
            :validation-errors="questionnaireValidationErrors"
            :user-contact="userContact"
            :sopd-signer-candidates="sopdSignerCandidates"
            :sopd-signer-candidates-loading="sopdSignerCandidatesLoading"
            :sopd-signer-candidates-error="sopdSignerCandidatesError"
            :application-id="checkoutStore.applicationId"
            @retry-sopd-signer-candidates="retrySopdSignerCandidates"
            @update="handleQuestionnaireUpdate"
          />

          <CheckoutCompanyData
            v-else-if="currentSection === 'company'"
            ref="companyDataRef"
            :company-id="checkoutStore.selectedCompanyId"
            :company-profile="applicationCompany"
            :tax-system="checkoutStore.questionnaireData?.tax_system ?? null"
          />

          <CheckoutOffersStep
            v-else-if="isCheckoutStatusSection(currentSection) && checkoutStore.applicationId"
            :key="checkoutStore.applicationId"
            :application-id="checkoutStore.applicationId"
            :application="application"
            :status-bucket="currentStatusSection"
            :show-confirmed-additional-options-tooltip="showConfirmedAdditionalOptionsTooltip"
            @lca-items-loaded="handleLcaItemsLoaded"
          />
        </fieldset>

        <section
          v-if="requestHistoryApplicationId && isDistributedApplicationView"
          class="mt-8 border-t border-[color:var(--storefront-border,#e5e7eb)] pt-6"
        >
          <DocumentRequestHistory
            :application-id="requestHistoryApplicationId"
            allow-upload
          />
        </section>

        <div class="mt-6 sm:mt-8 flex flex-col-reverse sm:flex-row justify-between gap-3">
          <button
            v-if="currentSection !== 'questionnaire'"
            type="button"
            class="btn-secondary text-center sm:text-left"
            :disabled="saving"
            @click="goBack"
          >
            Назад
          </button>
          <button
            v-else-if="isClientCheckoutLocked"
            type="button"
            class="btn-secondary text-center sm:text-left opacity-50 cursor-not-allowed"
            disabled
          >
            Назад
          </button>
          <NuxtLink
            v-else
            :to="questionnaireBackLocation"
            class="btn-secondary text-center sm:text-left"
          >
            Назад
          </NuxtLink>

          <button
            v-if="(currentSection === 'questionnaire' || currentSection === 'company') && !isWaitingForDistribution"
            type="button"
            :disabled="saving || (!isClientEditStepLocked && !canCreateCurrentApplication)"
            class="btn-primary w-full sm:w-auto justify-center disabled:opacity-50 disabled:cursor-not-allowed"
            @click="onNext"
          >
            <span v-if="saving" class="flex items-center justify-center gap-2">
              <span class="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-primary-border,#ffffff)]"></span>
              <span>Сохранение…</span>
            </span>
            <span v-else>{{ nextButtonLabel }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { provideNotificationCompanyContext } from '~/features/notifications'
import CheckoutCompanyData from '~/features/checkout/components/CheckoutCompanyData.vue'
import CheckoutOffersStep from '~/features/checkout/components/CheckoutOffersStep.vue'
import CheckoutQuestionnaire from '~/features/checkout/components/CheckoutQuestionnaire.vue'
import ApplicationItemsStep from '~/features/checkout/components/ApplicationItemsStep.vue'
import DocumentRequestHistory from '~/features/documents/components/DocumentRequestHistory.vue'

import { useDraftApplication } from '~/features/checkout/composables/useDraftApplication'
import { useCheckoutAutofill } from '~/features/checkout/composables/useCheckoutAutofill'
import { useApplicationSopdSignerCandidates } from '~/features/checkout/composables/useApplicationSopdSignerCandidates'
import { useAuthStore } from '~/features/auth/store/auth'
import { useApplicationCompanyPermissions } from '~/features/auth/composables/useApplicationCompanyPermissions'
import { clearLegacy, useScopedStorage } from '~/features/auth/composables/useScopedStorage'
import { createApplicationsApi } from '~/features/applications/api/applicationsApi'
import CommerceApplicationItemsSummary from '~/features/commerce/components/CommerceApplicationItemsSummary.vue'
import type { CommerceApplicationItem } from '~/features/commerce/types'
import {
  CHECKOUT_LCA_STATUS_BUCKETS,
  CHECKOUT_STATUS_SECTIONS,
  CHECKOUT_STEPS,
  checkoutSectionForStep,
  checkoutStepForSection,
  getLatestStatusSection,
  isCheckoutStatusSection,
  normalizeCheckoutStep,
  type CheckoutSection,
  type CheckoutStatusBucket,
} from '~/features/checkout/utils/steps'
import { canViewApplicationSource, formatSourcedApplicationNumber } from '~/features/applications/sourceType'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import { isUuid } from '~/types/ids'
import type { Application } from '@/types'
import type { UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'
import { getUserFacingErrorMessage } from '~/utils/userFacingError'

interface CompanyDataExposed {
  companyData: Record<string, unknown> | null
  foundersList: Array<{ name: string; inn: string; share: string; [k: string]: unknown }>
  editableData: Record<string, unknown>
  checkBeforeNext: () => { canProceed: boolean; emptyFields: string[] }
}

interface ManualContact {
  name: string
  position: string
  phone: string
  email: string
}

interface ManualInputData {
  legal_address: string
  actual_address: string
  actual_address_same_as_legal: boolean
  tax_system: string
  contacts: ManualContact[]
}

interface ApplicationItemUpdate {
  line_id: UUID
  kind: 'vehicle' | 'special_equipment'
  leasing_purpose: string | null
  leasing_purposes?: string[] | null
  regions: string[]
  region: string | null
  comment: string | null
}

interface ApplicationLcaStatusItem {
  id?: UUID
  leasing_company_id?: UUID | null
  status?: string | null
  display_status?: string | null
  [key: string]: unknown
}

type SubmittedWithoutLcaStorage = Record<string, boolean>

const CHECKOUT_SUBMITTED_WITHOUT_LCA_KEY = 'checkout-submitted-without-lca'

const props = defineProps<{ questionnairePage?: boolean }>()
const route = useRoute()
const notificationCompanyContext = () => isUuid(route.query.notification_company_id)
  ? route.query.notification_company_id
  : undefined
// Keep the page request selector stable while its children use the authorized
// client application's company after hydration.
provideNotificationCompanyContext(() => route.query.notification_company_id === undefined && authStore.isClient
  ? applicationCompanyId.value
  : route.query.notification_company_id)
let targetDisposed = false
onBeforeUnmount(() => { targetDisposed = true })
const router = useRouter()
const config = useRuntimeConfig()
const { pageTitle, publicRoute } = useStorefront()
const api = createApplicationsApi(config, notificationCompanyContext)
const toast = useToast()
const authStore = useAuthStore()
const checkoutStore = useCheckoutStore()
const submittedWithoutLcaStorage = useScopedStorage<SubmittedWithoutLcaStorage>(CHECKOUT_SUBMITTED_WITHOUT_LCA_KEY)
clearLegacy(CHECKOUT_SUBMITTED_WITHOUT_LCA_KEY)
const {
  loadApplication,
  updateCompany,
  updateQuestionnaire,
  submitApplication,
} = useDraftApplication(notificationCompanyContext)
const {
  autofilledFields,
  companyExternalData,
  loadingCompanyData,
  fetchCompanyData,
  loadAutofilledFieldsFromStorage,
} = useCheckoutAutofill(notificationCompanyContext)
const {
  candidates: sopdSignerCandidates,
  loading: sopdSignerCandidatesLoading,
  error: sopdSignerCandidatesError,
  load: loadSopdSignerCandidates,
  reset: resetSopdSignerCandidates,
  invalidate: invalidateSopdSignerCandidates,
} = useApplicationSopdSignerCandidates(notificationCompanyContext)

const bootLoading = ref(true)
const saving = ref(false)
const error = ref('')
const statusRouteNotice = ref('')
const statusRouteReadOnly = ref(false)
const applicationLoadError = ref('')
const maxReachedStep = ref(Math.min(normalizeCheckoutStep(checkoutStore.currentStep), 2))
const submittedWithoutAvailableStatus = ref(false)
const distributionJustArrived = ref(false)
const application = ref<(Application & Record<string, unknown>) | null>(null)
const applicationCompany = ref<Record<string, unknown> | null>(null)
const applicationCompanyId = computed<UUID | null>(() =>
  typeof application.value?.company_id === 'string' ? application.value.company_id : null,
)
const createBlockedMessage = 'Создание заявок ограничено администратором компании. Если вас не устраивает такое положение, напишите в поддержку.'
let waitingDistributionTimer: ReturnType<typeof setInterval> | null = null
let applicationHydrationGeneration = 0
let waitingDistributionRequest: {
  applicationId: UUID
  companyContext: UUID | undefined
} | null = null

const applicationItemsCount = computed(() => typeof application.value?.items_count === 'number' ? application.value.items_count : null)
const applicationItemsPrice = computed(() => typeof application.value?.total_items_price === 'string' ? application.value.total_items_price : null)
const activeApplicationItemsCount = computed(() => applicationItemsCount.value ?? checkoutStore.applicationItems.filter((item) => !item.status || !['removed', 'replaced', 'rejected'].includes(item.status)).length)
const isSingleCarMode = computed(() => checkoutStore.applicationItems.length > 0
  ? activeApplicationItemsCount.value === 1
  : checkoutStore.isSingleCarMode)
const primaryApplicationItemType = computed(() => checkoutStore.applicationItems.find((item) => !item.status || !['removed', 'replaced', 'rejected'].includes(item.status))?.type ?? null)
const applicationBackLocation = computed(() => {
  if (!isSingleCarMode.value) return publicRoute('/cart')
  return publicRoute('/special-equipment')
})
const applicationBackLabel = computed(() => pageTitle('special_equipment_catalog'))
const isItemsRoute = computed(() => !props.questionnairePage && getFirstRouteValue(route.query.step) === 'items')
const applicationStepPath = (id: UUID, step: string) => {
  const query: Record<string, string> = { step }
  const company = notificationCompanyContext()
  if (company) query.notification_company_id = company
  if (isUuid(route.query.leasing_company_id)) query.leasing_company_id = route.query.leasing_company_id
  if (typeof route.query.return_storefront === 'string') query.return_storefront = route.query.return_storefront
  const path = step === '1' ? `/questionnaire/${id}` : `/application/${id}`
  return publicRoute(`${path}?${new URLSearchParams(query)}`)
}
const questionnaireBackLocation = computed(() => (
  authStore.isClient && checkoutStore.applicationId
    ? applicationStepPath(checkoutStore.applicationId, 'items')
    : applicationBackLocation.value
))

const companyDataRef = ref<CompanyDataExposed | null>(null)
const questionnaireRef = ref<InstanceType<typeof CheckoutQuestionnaire> | null>(null)

const userContact = computed(() => {
  const user = authStore.user as { name?: string; phone?: string; email?: string; role?: string } | null
  const ext = companyExternalData.value as Record<string, string | undefined> | null
  const externalContact = {
    name: ext?.contact_name || '',
    phone: ext?.contact_phone || '',
    email: ext?.contact_email || '',
  }

  if (user?.role === 'dealer') {
    return externalContact
  }

  return {
    name: externalContact.name || user?.name || '',
    phone: externalContact.phone || user?.phone || '',
    email: externalContact.email || user?.email || '',
  }
})

const questionnaireData = ref<ManualInputData>({
  legal_address: '',
  actual_address: '',
  actual_address_same_as_legal: false,
  tax_system: '',
  contacts: [{ name: '', position: '', phone: '', email: '' }],
})
const questionnaireValidationErrors = ref<string[]>([])

const retrySopdSignerCandidates = () => {
  const applicationId = application.value?.id
  if (applicationId) void loadSopdSignerCandidates(applicationId).catch(() => {})
}

const handleQuestionnaireUpdate = (data: ManualInputData) => {
  questionnaireData.value = { ...data }
  questionnaireValidationErrors.value = []
  error.value = ''
}

const isDealer = computed(() => authStore.user?.role === 'dealer')
const showConfirmedAdditionalOptionsTooltip = computed(() => authStore.user?.role === 'client')
const {
  canCreate: selectedCompanyCanCreate,
  hasSelection: hasCompanySelection,
  loading: companyPermissionLoading,
  error: companyPermissionError,
  refresh: refreshCompanyPermissions,
} = useApplicationCompanyPermissions(
  () => route.query.notification_company_id,
  () => isDealer.value || authStore.canCreateApplications,
)
const canCreateCurrentApplication = computed(() => selectedCompanyCanCreate.value
  && (!hasCompanySelection.value || Boolean(application.value?.id)))
const companyPermissionMessage = computed(() => {
  if (companyPermissionLoading.value) return 'Проверяем права выбранной компании…'
  if (companyPermissionError.value) return companyPermissionError.value
  return canCreateCurrentApplication.value ? '' : createBlockedMessage
})

const hasRealLcaDistribution = (app: Record<string, unknown> | null) => {
  const items = app?.leasing_company_applications
  if (!Array.isArray(items)) return false
  return items.some((item) => {
    if (!item || typeof item !== 'object') return false
    return Boolean((item as Record<string, unknown>).leasing_company_id)
  })
}

const isDistributedApplicationView = computed(() => hasRealLcaDistribution(application.value))
const requestHistoryApplicationId = computed<UUID | null>(() => application.value?.id ?? null)
const isClientCheckoutLocked = computed(() =>
  authStore.user?.role === 'client' && (isDistributedApplicationView.value || statusRouteReadOnly.value),
)
const isClientEditStepLocked = computed(() =>
  isClientCheckoutLocked.value
    && (currentSection.value === 'questionnaire' || currentSection.value === 'company'),
)
const applicationNumber = computed(() => formatSourcedApplicationNumber(application.value, canViewApplicationSource(authStore.userRole)))
const applicationTitle = computed(() =>
  applicationNumber.value === '—' ? 'Заявка' : `Заявка ${applicationNumber.value}`,
)
const checkoutPageTitle = computed(() => props.questionnairePage ? 'Заполнение анкеты' : applicationTitle.value)
const checkoutBreadcrumbCurrent = computed(() => applicationTitle.value)
const nextButtonLabel = computed(() => {
  if (isClientEditStepLocked.value) return 'Далее'
  return currentSection.value === 'questionnaire' ? 'Сохранить и продолжить' : 'Отправить заявку'
})

const applyApplicationCompanyData = () => {
  if (!isDealer.value || !applicationCompany.value) return false
  companyExternalData.value = { ...applicationCompany.value }
  return true
}

const fetchResolvedCompanyProfile = async () => {
  if (!applicationCompanyId.value) return
  applyApplicationCompanyData()
  await fetchCompanyData(applicationCompanyId.value)
}

const shouldHydrateCompanyFromApplication = (app: Record<string, unknown>) => {
  if (checkoutStore.selectedApplicationCompany) return false
  if (!checkoutStore.selectedCompanyId) return true
  const applicationCompanyId = app.company_id as UUID | null | undefined
  if (!applicationCompanyId) return false
  return checkoutStore.selectedCompanyId === applicationCompanyId
}

const cloneContacts = (contacts: ManualContact[]) => contacts.map((contact) => ({ ...contact }))

const syncQuestionnaireFromComponent = () => {
  const data = questionnaireRef.value?.getData?.() as Partial<ManualInputData> | undefined
  if (!data) return

  const next = { ...questionnaireData.value }
  if (typeof data.legal_address === 'string') next.legal_address = data.legal_address
  if (typeof data.actual_address === 'string') next.actual_address = data.actual_address
  if (typeof data.actual_address_same_as_legal === 'boolean') {
    next.actual_address_same_as_legal = data.actual_address_same_as_legal
  }
  if (typeof data.tax_system === 'string') next.tax_system = data.tax_system
  if (Array.isArray(data.contacts)) next.contacts = cloneContacts(data.contacts)
  questionnaireData.value = next
}

const getFirstRouteValue = (value: unknown) => Array.isArray(value) ? value[0] : value

const getRouteValue = (value: unknown): UUID | undefined => {
  const routeValue = getFirstRouteValue(value)
  return typeof routeValue === 'string' ? routeValue : undefined
}

const getQueryValue = getFirstRouteValue

const currentSection = ref<CheckoutSection>(props.questionnairePage ? 'questionnaire' : checkoutSectionForStep(checkoutStore.currentStep))
const currentStatusSection = computed<CheckoutStatusBucket>(() =>
  isCheckoutStatusSection(currentSection.value) ? currentSection.value : 'sent',
)

const routeSection = (step: unknown, section: unknown): CheckoutSection => {
  if (props.questionnairePage) return 'questionnaire'
  const requestedSection = getQueryValue(section)
  if (requestedSection === 'preliminary' || requestedSection === 'documents' || requestedSection === 'final') {
    return requestedSection
  }
  const value = getQueryValue(step)
  return value === 'company' ? 'company' : checkoutSectionForStep(value)
}

const hasStatusBucketInItems = (
  bucket: CheckoutStatusBucket,
  items: ApplicationLcaStatusItem[] | undefined,
) => {
  const statuses = CHECKOUT_LCA_STATUS_BUCKETS[bucket].statuses as readonly string[]
  return Array.isArray(items) && items.some(item => {
    // Document status is a presentation overlay. The permanent workflow
    // sections must remain available according to the actual LCA status.
    const status = bucket === 'documents'
      ? item?.display_status ?? item?.status
      : item?.status
    return typeof status === 'string' && statuses.includes(status)
  })
}

const availableStatusSections = computed(() => {
  const sections = new Set<CheckoutStatusBucket>()
  const lcas = application.value?.leasing_company_applications as ApplicationLcaStatusItem[] | undefined
  for (const step of CHECKOUT_STATUS_SECTIONS) {
    if (hasStatusBucketInItems(step.bucket, lcas)) {
      sections.add(step.section)
    }
  }
  if ((Array.isArray(lcas) && lcas.length > 0) || sections.size > 0) {
    sections.add('sent')
  }
  return sections
})

type CheckoutStepDisplay = {
  section: CheckoutSection
  num?: number
  label: string
  bucket?: CheckoutStatusBucket
}

const visibleCheckoutSteps = computed<CheckoutStepDisplay[]>(() => {
  const permanentSteps: CheckoutStepDisplay[] = CHECKOUT_STEPS.map(step => ({ ...step }))
  if (!availableStatusSections.value.has('documents')) return permanentSteps
  const finalIndex = permanentSteps.findIndex(step => step.section === 'final')
  const documentStep = CHECKOUT_STATUS_SECTIONS.find(step => step.section === 'documents')!
  return [
    ...permanentSteps.slice(0, finalIndex),
    { ...documentStep },
    ...permanentSteps.slice(finalIndex),
  ]
})

const maxReachedStepIndex = ref(0)
const updateMaxReachedStep = (section: CheckoutSection) => {
  const index = visibleCheckoutSteps.value.findIndex(step => step.section === section)
  if (index > maxReachedStepIndex.value) {
    maxReachedStepIndex.value = index
  }
}

watch([currentSection, visibleCheckoutSteps], () => {
  updateMaxReachedStep(currentSection.value)
}, { immediate: true })

const isWaitingForDistribution = computed(() =>
  submittedWithoutAvailableStatus.value && availableStatusSections.value.size === 0,
)
const firstAvailableStatusSection = computed(() =>
  CHECKOUT_STATUS_SECTIONS.find(step => availableStatusSections.value.has(step.section))?.section ?? null,
)
const latestAvailableStatusSection = computed(() => getLatestStatusSection(availableStatusSections.value))
const fallbackEditableSection = () => checkoutSectionForStep(Math.min(maxReachedStep.value, 2))
const hasAnyStatusBucket = (items: ApplicationLcaStatusItem[] | undefined) =>
  CHECKOUT_STATUS_SECTIONS.some(step => hasStatusBucketInItems(step.bucket, items))

const submittedWithoutLcaKey = (applicationId: UUID | null | undefined) => applicationId ?? null

const readSubmittedWithoutLcaMap = () => submittedWithoutLcaStorage.get() || {}

const hasSubmittedWithoutAvailableStatusMarker = (applicationId: UUID | null | undefined) => {
  const key = submittedWithoutLcaKey(applicationId)
  if (!key) return false
  return Boolean(readSubmittedWithoutLcaMap()[key])
}

const markSubmittedWithoutAvailableStatus = (
  applicationId: UUID | null | undefined,
  waiting: boolean,
) => {
  submittedWithoutAvailableStatus.value = waiting
  const key = submittedWithoutLcaKey(applicationId)
  if (!key) return

  const map = readSubmittedWithoutLcaMap()
  if (waiting) {
    map[key] = true
  } else {
    delete map[key]
  }

  if (Object.keys(map).length > 0) {
    submittedWithoutLcaStorage.set(map)
  } else {
    submittedWithoutLcaStorage.remove()
  }
}

const isSectionAvailable = (section: CheckoutSection) =>
  !isCheckoutStatusSection(section) || availableStatusSections.value.has(section)

const resolveAllowedSection = (
  requested: CheckoutSection,
  options: { preferLatestStatus?: boolean } = {},
): CheckoutSection => {
  if (isCheckoutStatusSection(requested)) {
    return isSectionAvailable(requested)
      ? requested
      : latestAvailableStatusSection.value || firstAvailableStatusSection.value || (statusRouteReadOnly.value ? 'questionnaire' : fallbackEditableSection())
  }
  if (options.preferLatestStatus && latestAvailableStatusSection.value) return latestAvailableStatusSection.value
  return requested
}

const rememberStatusRouteFallback = (requested: CheckoutSection) => {
  if (!isCheckoutStatusSection(requested)) return
  const unavailable = !isSectionAvailable(requested)
  statusRouteReadOnly.value = unavailable && availableStatusSections.value.size === 0
  statusRouteNotice.value = unavailable
    ? statusRouteReadOnly.value
      ? 'Состояние заявки изменилось. Раздел из уведомления больше недоступен. Данные заявки доступны только для просмотра.'
      : 'Состояние заявки изменилось. Открыт актуальный доступный раздел вместо раздела из уведомления.'
    : ''
}

const syncRouteSection = async (section: CheckoutSection, mode: 'replace' | 'push' = 'replace') => {
  const requestedSection = routeSection(route.query.step, route.query.section)
  if (statusRouteReadOnly.value && isCheckoutStatusSection(requestedSection)) return
  const nextSection = resolveAllowedSection(section)
  const nextApplicationId = getRouteValue(route.params.id) ?? checkoutStore.applicationId
  if (!nextApplicationId) return
  const nextQuery: Record<string, string> = {}
  if (nextSection === 'company') nextQuery.step = 'company'
  else if (nextSection === 'questionnaire') nextQuery.step = '1'
  else if (nextSection === 'documents') nextQuery.section = 'documents'
  else nextQuery.step = String(checkoutStepForSection(nextSection))
  const notificationCompanyId = notificationCompanyContext()
  if (notificationCompanyId) nextQuery.notification_company_id = notificationCompanyId
  if (isUuid(route.query.notification_id)) nextQuery.notification_id = route.query.notification_id
  if (isUuid(route.query.leasing_company_id)) nextQuery.leasing_company_id = route.query.leasing_company_id
  if (typeof route.query.return_storefront === 'string') nextQuery.return_storefront = route.query.return_storefront
  const nextPath = publicRoute(props.questionnairePage && nextSection === 'questionnaire'
    ? `/questionnaire/${nextApplicationId}` : `/application/${nextApplicationId}`)
  if (requestedSection === nextSection && getRouteValue(route.params.id) === nextApplicationId && route.path === nextPath) return
  await router[mode]({ path: nextPath, query: nextQuery, hash: route.hash })
}

const setSection = (section: CheckoutSection, options: { syncRoute?: boolean; routeMode?: 'replace' | 'push' } = {}) => {
  const nextSection = resolveAllowedSection(section)
  // Keep the form mounted until the route guard has flushed its pending save.
  if (props.questionnairePage && nextSection !== 'questionnaire' && options.syncRoute !== false) {
    void syncRouteSection(nextSection, options.routeMode || 'push')
    return
  }
  currentSection.value = nextSection
  if (nextSection !== 'documents') {
    const step = checkoutStepForSection(nextSection)
    checkoutStore.setStep(step)
    if (step > maxReachedStep.value) maxReachedStep.value = step
  }
  updateMaxReachedStep(nextSection)
  error.value = ''
  if (options.syncRoute !== false) void syncRouteSection(nextSection, options.routeMode || 'replace')
}

const ensureCurrentStatusSectionAvailable = () => {
  if (!isCheckoutStatusSection(currentSection.value) || isSectionAvailable(currentSection.value)) return
  rememberStatusRouteFallback(currentSection.value)
  setSection(latestAvailableStatusSection.value || firstAvailableStatusSection.value || 'questionnaire', { routeMode: 'replace' })
}

const handleLcaItemsLoaded = (items: ApplicationLcaStatusItem[]) => {
  if (!application.value) return
  const previousLatest = latestAvailableStatusSection.value
  const previousSection = currentSection.value
  application.value = { ...application.value, leasing_company_applications: items as Application['leasing_company_applications'] }
  if (hasAnyStatusBucket(items)) markSubmittedWithoutAvailableStatus(application.value.id, false)
  if (props.questionnairePage) return
  const nextLatest = latestAvailableStatusSection.value
  const previousIndex = CHECKOUT_STATUS_SECTIONS.findIndex(step => step.section === previousSection)
  const nextIndex = nextLatest ? CHECKOUT_STATUS_SECTIONS.findIndex(step => step.section === nextLatest) : -1
  if (nextLatest && (!isCheckoutStatusSection(previousSection) || (previousLatest !== nextLatest && previousIndex < nextIndex))) {
    setSection(nextLatest, { routeMode: 'replace' })
    return
  }
  ensureCurrentStatusSectionAvailable()
}

const canJump = (section: CheckoutSection) => {
  if (isCheckoutStatusSection(section)) return isSectionAvailable(section)
  if (isClientCheckoutLocked.value) return section === 'questionnaire' || section === 'company'
  const index = visibleCheckoutSteps.value.findIndex(step => step.section === section)
  return (index >= 0 && index <= maxReachedStepIndex.value) || checkoutStepForSection(section) <= maxReachedStep.value
}

const jumpTo = (section: CheckoutSection) => {
  if (section !== currentSection.value && canJump(section)) setSection(section)
}

type StepState = 'current' | 'completed' | 'upcoming'
const stepState = (section: CheckoutSection): StepState => {
  const currentIndex = visibleCheckoutSteps.value.findIndex(step => step.section === currentSection.value)
  const index = visibleCheckoutSteps.value.findIndex(step => step.section === section)
  if (index === currentIndex) return 'current'
  if (index >= 0 && index < maxReachedStepIndex.value) return 'completed'
  return 'upcoming'
}
const stepBubble = (section: CheckoutSection) => stepState(section) === 'current'
  ? 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)] ring-4 ring-[color:var(--storefront-border,#dbeafe)]'
  : 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)]'

const goBack = () => {
  const currentIndex = visibleCheckoutSteps.value.findIndex(step => step.section === currentSection.value)
  for (let index = currentIndex - 1; index >= 0; index -= 1) {
    const section = visibleCheckoutSteps.value[index].section
    if (canJump(section)) return setSection(section)
  }
  setSection('questionnaire')
}

const returnToCompanySelection = async () => {
  await router.push(publicRoute('/application/new'))
}

const saveApplicationItems = async (items: ApplicationItemUpdate[]) => {
  const applicationId = getRouteValue(route.params.id)
  const companyContext = notificationCompanyContext()
  if (!applicationId || saving.value) return
  if (!canCreateCurrentApplication.value) {
    error.value = companyPermissionMessage.value || createBlockedMessage
    toast.error(error.value)
    return
  }

  saving.value = true
  error.value = ''
  try {
    await api.updateApplicationItems(applicationId, items)
    if (targetDisposed || companyContext !== notificationCompanyContext()) return
    checkoutStore.setApplicationItems(checkoutStore.applicationItems.map(item => {
      const update = items.find(candidate => candidate.line_id === item.id && candidate.kind === item.type)
      return update
        ? {
            ...item,
            leasing_purpose: update.leasing_purpose,
            leasing_purposes: update.leasing_purposes,
            regions: [...update.regions],
            region: update.region,
            comment: update.comment,
          }
        : item
    }))
    checkoutStore.clearApplicationCreateIdempotencyKey()
    checkoutStore.setCommerceItems([])
    checkoutStore.setCalculation(null)
    await router.push(applicationStepPath(applicationId, '1'))
  } catch (err: unknown) {
    if (targetDisposed || companyContext !== notificationCompanyContext()) return
    if (hasCompanySelection.value) void refreshCompanyPermissions()
    error.value = getUserFacingErrorMessage(err, 'Не удалось сохранить позиции заявки')
    toast.error(error.value)
  } finally {
    saving.value = false
  }
}

const collectStep4DocumentIds = (): UUID[] => {
  const ids = new Set<UUID>()
  const selected = checkoutStore.form.selectedDocuments ?? {}
  for (const value of Object.values(selected)) {
    if (Array.isArray(value)) {
      for (const id of value) {
        if (id) ids.add(id)
      }
    } else if (value) {
      ids.add(value)
    }
  }
  return Array.from(ids)
}

const attachStep4Documents = async (applicationId: UUID): Promise<void> => {
  const documentIds = collectStep4DocumentIds()
  if (documentIds.length === 0) return
  try {
    await api.attachDocuments(applicationId, documentIds)
  } catch (err) {
    // Non-fatal: linking is best-effort — the LC flow accepts the submit
    // even if a few docs fail to attach. Admin can always relink later.
    console.warn('Failed to attach step-4 documents to application', err)
  }
}

const onNext = async () => {
  if (saving.value || isWaitingForDistribution.value) return
  const companyContext = notificationCompanyContext()
  const isCurrentTarget = () => !targetDisposed && companyContext === notificationCompanyContext()
  error.value = ''
  if (isClientEditStepLocked.value) {
    setSection(currentSection.value === 'questionnaire'
      ? 'company'
      : currentSection.value === 'company'
        ? firstAvailableStatusSection.value || fallbackEditableSection()
        : currentSection.value)
    return
  }
  if (!canCreateCurrentApplication.value) {
    error.value = companyPermissionMessage.value || createBlockedMessage
    toast.error(error.value)
    return
  }

  if (currentSection.value === 'questionnaire') {
    // Step 1: Anketa (questionnaire)
    if (questionnaireRef.value?.validate() === false) { error.value = 'Проверьте выделенные поля анкеты'; toast.error(error.value); return }
    syncQuestionnaireFromComponent()
    saving.value = true
    try {
      checkoutStore.updateQuestionnaireData(questionnaireData.value as unknown as Record<string, unknown>)
      if (checkoutStore.applicationId) {
        if (questionnaireRef.value && !await questionnaireRef.value.save()) return
      }
      if (!isCurrentTarget()) return
      setSection('company')
    } catch (err: unknown) {
      if (!isCurrentTarget()) return
      if (hasCompanySelection.value) void refreshCompanyPermissions()
      error.value = getUserFacingErrorMessage(err, 'Не удалось сохранить анкету')
      toast.error(error.value)
    } finally {
      saving.value = false
    }
    return
  }

  if (currentSection.value === 'company') {
    // Step 2: Company info
    const check = companyDataRef.value?.checkBeforeNext?.() ?? { canProceed: true, emptyFields: [] }
    if (!check.canProceed) {
      error.value = `Заполните поля: ${check.emptyFields.join(', ')}`
      return
    }
    saving.value = true
    try {
      if (checkoutStore.selectedCompanyId && checkoutStore.applicationId) {
        await updateCompany(checkoutStore.applicationId, checkoutStore.selectedCompanyId)
        if (!isCurrentTarget()) return
        invalidateSopdSignerCandidates(checkoutStore.applicationId)
      }
      if (checkoutStore.applicationId) {
        const submittedApplicationId = checkoutStore.applicationId
        await attachStep4Documents(submittedApplicationId)
        if (!isCurrentTarget()) return
        await submitApplication(submittedApplicationId)
        if (!isCurrentTarget()) return
        await hydrateApplication(submittedApplicationId)
        if (!isCurrentTarget()) return
        markSubmittedWithoutAvailableStatus(submittedApplicationId, !firstAvailableStatusSection.value)
        setSection(firstAvailableStatusSection.value || fallbackEditableSection(), { routeMode: 'push' })
      }
      toast.success('Заявка успешно отправлена')
    } catch (err: unknown) {
      if (!isCurrentTarget()) return
      if (hasCompanySelection.value) void refreshCompanyPermissions()
      error.value = getUserFacingErrorMessage(err, 'Не удалось отправить заявку')
      toast.error(error.value)
    } finally {
      saving.value = false
    }
    return
  }
}

// --- Mount: hydrate cart/vehicle/application state --------------------------

const hydrateApplication = async (appIdRaw: UUID, distributionOnly = false) => {
  const companyContext = notificationCompanyContext()
  const requestGeneration = ++applicationHydrationGeneration
  const isCurrentRequest = () =>
    !targetDisposed
      && requestGeneration === applicationHydrationGeneration
      && (!distributionOnly || !saving.value)
      && companyContext === notificationCompanyContext()
      && (getRouteValue(route.params.id) ?? checkoutStore.applicationId) === appIdRaw
  let app
  try {
    app = await loadApplication(appIdRaw)
  } catch (cause: unknown) {
    if (!isCurrentRequest()) return false
    const httpStatus = (cause as { statusCode?: number; status?: number })?.statusCode
      ?? (cause as { status?: number })?.status
    // A background refresh must not discard the form because of a temporary outage.
    if (distributionOnly && (httpStatus == null || httpStatus === 429 || httpStatus >= 500)) return false
    applicationLoadError.value = httpStatus === 403 || httpStatus === 404
      ? 'Заявка недоступна. Возможно, ваши права доступа изменились.'
      : 'Не удалось загрузить заявку. Обновите страницу, чтобы повторить попытку.'
    application.value = null
    applicationCompany.value = null
    checkoutStore.setApplicationItems([])
    stopWaitingDistributionPolling()
    return false
  }
  if (!isCurrentRequest()) return false
  if (!app.id) return false
  applicationLoadError.value = ''
  const wasSubmittedInCurrentPage = application.value?.id === app.id && submittedWithoutAvailableStatus.value
  const preserveEditableData = distributionOnly && application.value?.id === app.id
  application.value = preserveEditableData
    ? {
        ...application.value!,
        status: app.status as Application['status'],
        leasing_company_applications: app.leasing_company_applications as Application['leasing_company_applications'],
      }
    : app as Application & Record<string, unknown>
  const lcaItems = app.leasing_company_applications as ApplicationLcaStatusItem[] | undefined
  const applicationId = app.id
  const hadWaitingDistributionMarker = wasSubmittedInCurrentPage || hasSubmittedWithoutAvailableStatusMarker(applicationId)
  if (hasAnyStatusBucket(lcaItems)) {
    if (hadWaitingDistributionMarker) {
      distributionJustArrived.value = true
    }
    markSubmittedWithoutAvailableStatus(applicationId, false)
  } else {
    submittedWithoutAvailableStatus.value = hadWaitingDistributionMarker
  }
  if (preserveEditableData) return true
  checkoutStore.setApplicationId(applicationId)
  if (Array.isArray(app.vehicles)) {
    checkoutStore.setVehicles(
      app.vehicles as Array<{ mark_name: string; model_name: string; [k: string]: unknown }>,
    )
  }
  if (Array.isArray(app.items)) {
    checkoutStore.setApplicationItems(app.items as CommerceApplicationItem[])
  } else {
    checkoutStore.setApplicationItems([])
  }
  const shouldUseApplicationCompany = shouldHydrateCompanyFromApplication(app)
  if (shouldUseApplicationCompany && app.company_id) {
    checkoutStore.setSelectedCompanyId(app.company_id)
  }
  if (shouldUseApplicationCompany && app.company && typeof app.company === 'object') {
    applicationCompany.value = app.company as Record<string, unknown>
    checkoutStore.setSelectedApplicationCompany(applicationCompany.value as any)
    applyApplicationCompanyData()
  }
  const questionnaire = app.questionnaire as Record<string, unknown> | null | undefined
  if (questionnaire && typeof questionnaire === 'object') {
    checkoutStore.updateQuestionnaireData(questionnaire)
    if (typeof questionnaire.legal_address === 'string') questionnaireData.value.legal_address = questionnaire.legal_address
    if (typeof questionnaire.actual_address === 'string') questionnaireData.value.actual_address = questionnaire.actual_address
    if (typeof questionnaire.tax_system === 'string') questionnaireData.value.tax_system = questionnaire.tax_system
    if (Array.isArray(questionnaire.contacts)) {
      questionnaireData.value.contacts = cloneContacts(questionnaire.contacts as ManualContact[])
    }
  }
  return true
}

const stopWaitingDistributionPolling = () => {
  if (!waitingDistributionTimer) return
  clearInterval(waitingDistributionTimer)
  waitingDistributionTimer = null
}

const refreshWaitingDistribution = async () => {
  if (bootLoading.value || saving.value) return
  const applicationId = getRouteValue(route.params.id) ?? checkoutStore.applicationId
  if (!applicationId) return
  const companyContext = notificationCompanyContext()
  if (
    waitingDistributionRequest?.applicationId === applicationId
    && waitingDistributionRequest.companyContext === companyContext
  ) return

  const request = { applicationId, companyContext }
  waitingDistributionRequest = request
  try {
    const ok = await hydrateApplication(applicationId, true)
    if (!ok) return
    const nextStatusSection = latestAvailableStatusSection.value || firstAvailableStatusSection.value
    if (!nextStatusSection) return
    markSubmittedWithoutAvailableStatus(applicationId, false)
    stopWaitingDistributionPolling()
    if (!props.questionnairePage) setSection(nextStatusSection, { routeMode: 'replace' })
  } finally {
    if (waitingDistributionRequest === request) waitingDistributionRequest = null
  }
}

const startWaitingDistributionPolling = () => {
  if (waitingDistributionTimer) return
  void refreshWaitingDistribution()
  waitingDistributionTimer = setInterval(() => {
    void refreshWaitingDistribution()
  }, 15000)
}

onMounted(async () => {
  try {
    const applicationIdParam = getRouteValue(route.params.id)

    if (applicationIdParam) {
      const ok = await hydrateApplication(applicationIdParam)
      if (targetDisposed) return
      if (ok) {
        if (isItemsRoute.value) return
        const requestedSection = routeSection(route.query.step, route.query.section)
        rememberStatusRouteFallback(requestedSection)
        const startSection = resolveAllowedSection(requestedSection, { preferLatestStatus: !props.questionnairePage && ((!route.query.step && !route.query.section) || distributionJustArrived.value) })
        setSection(startSection, { syncRoute: false })
        if (startSection !== 'documents') maxReachedStep.value = Math.max(maxReachedStep.value, checkoutStepForSection(startSection))
        updateMaxReachedStep(startSection)
        void syncRouteSection(startSection)
      } else {
        if (applicationLoadError.value) return
        error.value = 'Заявка не найдена'
        toast.error(error.value)
        router.push(publicRoute('/cabinet'))
        return
      }
    } else if (checkoutStore.applicationId) {
      // Resume from localStorage — stay on current step
      await hydrateApplication(checkoutStore.applicationId)
      const startSection = resolveAllowedSection(currentSection.value, { preferLatestStatus: !props.questionnairePage && ((!route.query.step && !route.query.section) || distributionJustArrived.value) })
      setSection(startSection, { syncRoute: false })
      void syncRouteSection(startSection)
    } else {
      // No application — redirect to conditions page
      router.push(publicRoute('/cart/conditions'))
      return
    }

    loadAutofilledFieldsFromStorage()
    if (authStore.isAuthenticated) {
      await fetchResolvedCompanyProfile()
    }
  } finally {
    bootLoading.value = false
  }
})

watch([currentSection, isItemsRoute], async ([section, itemsRoute]) => {
  if (!bootLoading.value && !itemsRoute && section === 'questionnaire' && authStore.isAuthenticated) {
    await fetchResolvedCompanyProfile()
  }
})

watch(
  () => application.value?.id ?? null,
  (applicationId) => {
    resetSopdSignerCandidates(applicationId)
  },
  { immediate: true },
)

watch(
  [currentSection, () => application.value?.id ?? null],
  ([section, applicationId]) => {
    if (section === 'questionnaire' && applicationId) void loadSopdSignerCandidates(applicationId).catch(() => {})
  },
  { immediate: true },
)

watch(
  () => route.params.id,
  async (applicationIdParam) => {
    if (bootLoading.value) return
    const applicationId = getRouteValue(applicationIdParam)
    if (!applicationId || applicationId === checkoutStore.applicationId) return

    bootLoading.value = true
    try {
      const ok = await hydrateApplication(applicationId)
      if (targetDisposed) return
      if (!ok) {
        if (applicationLoadError.value) return
        error.value = 'Заявка не найдена'
        toast.error(error.value)
        await router.push(publicRoute('/cabinet'))
        return
      }
      const requestedSection = routeSection(route.query.step, route.query.section)
      rememberStatusRouteFallback(requestedSection)
      const nextSection = resolveAllowedSection(requestedSection, { preferLatestStatus: !props.questionnairePage && ((!route.query.step && !route.query.section) || distributionJustArrived.value) })
      setSection(nextSection, { syncRoute: false })
      void syncRouteSection(nextSection)
    } finally {
      bootLoading.value = false
    }
  },
)

watch(
  [() => route.query.step, () => route.query.section, () => route.query.notification_id],
  async ([step, section, notificationId], [, , previousNotificationId]) => {
    if (bootLoading.value || getQueryValue(step) === 'items') return
    const requested = routeSection(step, section)
    const newNotification = isUuid(notificationId) && notificationId !== previousNotificationId
    if (isCheckoutStatusSection(requested) && (newNotification || requested !== currentSection.value)) {
      const applicationId = getRouteValue(route.params.id)
      if (!applicationId) return
      bootLoading.value = true
      try {
        if (!await hydrateApplication(applicationId) || targetDisposed) return
      } finally {
        bootLoading.value = false
      }
    }
    const nextSection = resolveAllowedSection(routeSection(route.query.step, route.query.section))
    if (newNotification || requested !== currentSection.value) rememberStatusRouteFallback(requested)
    if (nextSection === currentSection.value) return
    if (canJump(nextSection) || isCheckoutStatusSection(requested)) setSection(nextSection, { syncRoute: false })
    else void syncRouteSection(nextSection)
  },
)

const shouldObserveDistribution = computed(() =>
  authStore.user?.role === 'client'
    && application.value?.status === 'active'
    && availableStatusSections.value.size === 0,
)

watch(shouldObserveDistribution, (waiting) => {
  if (waiting) {
    startWaitingDistributionPolling()
    return
  }
  stopWaitingDistributionPolling()
})

watch(
  () => companyExternalData.value,
  (ext) => {
    if (currentSection.value === 'questionnaire' && ext?.legal_address && !questionnaireData.value.legal_address) {
      questionnaireData.value.legal_address = ext.legal_address as string
    }
  },
  { deep: true },
)

const saveBeforeLeavingQuestionnaire = async () => {
  if (!props.questionnairePage || !application.value || isClientEditStepLocked.value
    || isWaitingForDistribution.value || !canCreateCurrentApplication.value) return true
  try {
    return await questionnaireRef.value?.save() !== false
  } catch (err: unknown) {
    error.value = getUserFacingErrorMessage(err, 'Не удалось сохранить анкету. Повторите переход.')
    return false
  }
}

onBeforeRouteLeave(saveBeforeLeavingQuestionnaire)
onBeforeRouteUpdate((to, from) => {
  if (to.params.id !== from.params.id
    || to.query.notification_company_id !== from.query.notification_company_id
    || to.query.leasing_company_id !== from.query.leasing_company_id) {
    return saveBeforeLeavingQuestionnaire()
  }
})

onBeforeUnmount(stopWaitingDistributionPolling)

useSeoMeta({
  title: () => props.questionnairePage ? 'Заполнение анкеты — CarCraft Multileasing' : 'Оформление заявки — CarCraft Multileasing',
  description: 'Оформление заявки на лизинг техники',
})
</script>

<style scoped>
.btn-primary {
  @apply bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)] px-4 py-2 rounded-md hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2;
}

.btn-secondary {
  @apply bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)] px-4 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2;
}
</style>
