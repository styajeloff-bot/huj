<template>
  <!-- Loading state -->
  <div data-storefront-block="client.checkout" v-if="props.loadingCompanyData" class="space-y-4 sm:space-y-6" style="color: var(--storefront-text,#000);">
    <div class="text-center py-10">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-3 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем данные компании…</p>
    </div>
  </div>

  <!-- Main content -->
  <div data-storefront-block="client.checkout" v-else class="space-y-4 sm:space-y-6" style="color: var(--storefront-text,#000);">
    <fieldset :disabled="props.readonly" class="space-y-4">
    <!-- Intro text -->
    <div class="p-4 bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-success-border,#bbf7d0)] rounded-lg">
      <p class="text-sm text-[color:var(--storefront-success-text,#166534)]">
        Осталось собрать подписи гендиректора и учредителей (с долей ≥25%) под согласием на обработку персональных данных. Введите их номера — отправим SMS со ссылкой на электронную подпись. Если номера нет — можно подписать бумажно.
      </p>
    </div>

    <!-- Section 1: Contacts & Addresses -->
    <div class="space-y-3 sm:space-y-4" :class="sectionClass(1)">
      <div class="p-4 rounded-r-lg border-l-4" :class="bannerClass(1)">
        <div class="flex items-center gap-3">
          <span
            class="flex-shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-[color:var(--storefront-text,#ffffff)] text-sm font-bold"
            :class="circleClass(1)"
          >
            <svg v-if="isCompleted(1)" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <span v-else>1</span>
          </span>
          <div>
            <p class="text-base font-semibold" :class="titleClass(1)">Контакты и адреса</p>
            <p class="text-xs mt-0.5" :class="descClass(1)">Контактные данные и юридический / фактический адрес</p>
          </div>
        </div>
      </div>

      <QuestionnaireContacts
        ref="contactsRef"
        :company-external-data="props.companyExternalData"
        :autofilled-fields="props.autofilledFields"
        :initial-data="contactsInitialData"
        :user-contact="props.userContact"
        :company-id="props.companyId"
        @update="onContactsUpdate"
      />
    </div>

    <QuestionnaireCompanyDetails :application-id="props.applicationId" :save-before-refresh="saveQuestionnaire" @update="onAdditionalUpdate" />
    <!-- Section 2: Signers / SOPD -->
    <div class="space-y-3 sm:space-y-4" :class="sectionClass(2)">
      <div class="p-4 rounded-r-lg border-l-4" :class="bannerClass(2)">
        <div class="flex items-center gap-3">
          <span
            class="flex-shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-[color:var(--storefront-text,#ffffff)] text-sm font-bold"
            :class="circleClass(2)"
          >
            <svg v-if="isCompleted(2)" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <span v-else>2</span>
          </span>
          <div>
            <p class="text-base font-semibold" :class="titleClass(2)">Согласие на обработку персональных данных</p>
            <p class="text-xs mt-0.5" :class="descClass(2)">Подписание СОПД для учредителей и генерального директора</p>
          </div>
        </div>
      </div>

      <div v-if="props.sopdSignerCandidatesLoading" class="flex items-center justify-center gap-2 py-6 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
        <span class="h-5 w-5 animate-spin rounded-full border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
        Загружаем список подписантов СОПД…
      </div>
      <div v-else-if="props.sopdSignerCandidatesError" class="rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-4" role="alert">
        <p class="text-sm text-[color:var(--storefront-error-text,#991b1b)]">{{ props.sopdSignerCandidatesError }}</p>
        <button type="button" class="storefront-action-ghost mt-3 text-sm font-semibold text-[color:var(--storefront-ghost-foreground,#1d4ed8)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)]" @click="emit('retry-sopd-signer-candidates')">
          Повторить
        </button>
      </div>
      <QuestionnaireSopd
        v-else-if="props.sopdSignerCandidates !== null"
        ref="sopdRef"
        :application-id="props.applicationId"
        :sopd-signer-candidates="mainSignerCandidates"
        @update="onSopdUpdate"
        :run-passport-confirmation="runPassportConfirmation"
      />
    </div>

    <QuestionnaireBeneficiaries ref="beneficiariesRef" :application-id="props.applicationId" :save-beneficiaries="saveBeneficiaries" :run-passport-confirmation="runPassportConfirmation" @update="onAdditionalUpdate" />
    <!-- Section 3: Company Documents -->
    <div class="space-y-3 sm:space-y-4" :class="sectionClass(3)">
      <div class="p-4 rounded-r-lg border-l-4" :class="bannerClass(3)">
        <div class="flex items-center gap-3">
          <span
            class="flex-shrink-0 inline-flex items-center justify-center w-8 h-8 rounded-full text-[color:var(--storefront-text,#ffffff)] text-sm font-bold"
            :class="circleClass(3)"
          >
            <svg v-if="isCompleted(3)" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <span v-else>3</span>
          </span>
          <div>
            <p class="text-base font-semibold" :class="titleClass(3)">Документы компании</p>
            <p class="text-xs mt-0.5" :class="descClass(3)">{{ companyDocsDescription }}</p>
          </div>
        </div>
      </div>

      <QuestionnaireEdo ref="edoRef" :model-value="checkoutStore.questionnaireData.electronic_document_management_systems" @update:model-value="onAdditionalUpdate({ electronic_document_management_systems: $event })" />
      <QuestionnaireCompanyDocs
        ref="docsRef"
        :application-id="props.applicationId"
        :company-inn="companyInn"
        :initial-tax-system="checkoutStore.questionnaireData?.tax_system ?? null"
        :initial-uploaded="checkoutStore.questionnaireData?.company_docs_uploaded === true"
        :tax-system-auto="checkoutStore.questionnaireData?.tax_system_auto ?? false"
        @update="onDocsUpdate"
      />
    </div>
    <p v-if="saveError" class="rounded-md border border-red-200 p-3 text-sm text-red-700" role="alert">{{ saveError }} <button type="button" class="underline" @click="saveQuestionnaire">Повторить сохранение</button></p>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { useNotificationCompanyRequest } from '~/features/notifications'
const { request: notificationRequest } = useNotificationCompanyRequest()
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { UUID } from '~/types/ids'
import type { QuestionnaireData } from '~/features/applications/constants/application'
import { questionnaireWritePayload, type QuestionnairePerson } from '~/features/questionnaire/types'
import QuestionnaireCompanyDetails from '~/features/questionnaire/components/QuestionnaireCompanyDetails.vue'
import QuestionnaireBeneficiaries from '~/features/questionnaire/components/QuestionnaireBeneficiaries.vue'
import QuestionnaireEdo from '~/features/questionnaire/components/QuestionnaireEdo.vue'
import QuestionnaireContacts from './QuestionnaireContacts.vue'
import QuestionnaireSopd from './QuestionnaireSopd.vue'
import QuestionnaireCompanyDocs from './QuestionnaireCompanyDocs.vue'
import type { SopdSignerCandidate } from '~/features/checkout/types/sopdSigners'

interface Contact {
  name: string
  position: string
  phone: string
  email: string
}

interface FormData {
  legal_address: string
  actual_address: string
  actual_address_same_as_legal: boolean
  tax_system: string
  contacts: Contact[]
}

interface UserContact {
  name: string
  phone: string
  email: string
}

const props = defineProps<{
  readonly: boolean
  companyId?: UUID | null
  loadingCompanyData?: boolean
  companyExternalData?: Record<string, any> | null
  autofilledFields?: Record<string, boolean>
  initialData?: FormData | null
  validationErrors?: string[]
  userContact?: UserContact | null
  sopdSignerCandidates: SopdSignerCandidate[] | null
  sopdSignerCandidatesLoading?: boolean
  sopdSignerCandidatesError?: string
  applicationId?: UUID | null
}>()

const emit = defineEmits<{
  (e: 'update', data: FormData): void
  (e: 'ready'): void
  (e: 'retry-sopd-signer-candidates'): void
}>()

const checkoutStore = useCheckoutStore()

const contactsRef = ref<InstanceType<typeof QuestionnaireContacts> | null>(null)
const sopdRef = ref<InstanceType<typeof QuestionnaireSopd> | null>(null)
const docsRef = ref<InstanceType<typeof QuestionnaireCompanyDocs> | null>(null)
const beneficiariesRef = ref<InstanceType<typeof QuestionnaireBeneficiaries> | null>(null)
const edoRef = ref<InstanceType<typeof QuestionnaireEdo> | null>(null)
const saveError = ref('')
const pendingChanges = ref<Record<string, unknown>>({})

const mainSignerCandidates = computed(() => (props.sopdSignerCandidates || []).filter(candidate => candidate.role !== 'beneficiary'))
const contactsInitialData = computed<FormData>(() => {
  const q = checkoutStore.questionnaireData
  return {
    ...q,
    legal_address: q.legal_address || '',
    actual_address: q.actual_address || '',
    actual_address_same_as_legal: q.actual_address_same_as_legal === true,
    tax_system: q.tax_system || '',
    contacts: (q.contacts || []) as Contact[],
  }
})

const companyInn = computed(() => {
  const company = props.companyExternalData as Record<string, unknown> | null | undefined
  const storeCompany = checkoutStore.selectedApplicationCompany as Record<string, unknown> | null
  return String(company?.inn || storeCompany?.inn || checkoutStore.questionnaireData?.inn || '')
})

const isBankStatementTaxSystem = computed(() => {
  const taxSystem = String(checkoutStore.questionnaireData?.tax_system || '').toLowerCase()
  return taxSystem.includes('усн') || taxSystem.includes('автоусн') || taxSystem.includes('ausn')
})

const companyDocsDescription = computed(() => {
  if (isBankStatementTaxSystem.value) {
    return '.txt выписки банка за последние 2 года. После загрузки лизинговая увидит финансовые показатели.'
  }
  return 'XML по стандарту 1С Бухгалтерия. После загрузки гендиректор получит SMS с ссылкой на подписание.'
})

const completedSubSteps = computed(() => checkoutStore.completedSubSteps)

const isCompleted = (n: number) => completedSubSteps.value.includes(n)
const isActive = (n: number) => !isCompleted(n)

const sectionClass = (_n: number) => ''
const bannerClass = (n: number) => {
  if (isCompleted(n)) return 'bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-success-border,#22c55e)]'
  if (isActive(n)) return 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-border,#2563eb)]'
  return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-border,#9ca3af)]'
}
const circleClass = (n: number) => {
  if (isCompleted(n)) return 'bg-[color:rgb(var(--storefront-success-rgb,22_163_74)/var(--tw-bg-opacity,1))]'
  if (isActive(n)) return 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))]'
  return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,156_163_175)/var(--tw-bg-opacity,1))]'
}
const titleClass = (n: number) => {
  if (isCompleted(n)) return 'text-[color:var(--storefront-success-text,#14532d)]'
  if (isActive(n)) return 'text-[color:var(--storefront-text,#1e3a8a)]'
  return 'text-[color:var(--storefront-text,#111827)]'
}
const descClass = (n: number) => {
  if (isCompleted(n)) return 'text-[color:var(--storefront-success-text,#15803d)]'
  if (isActive(n)) return 'text-[color:var(--storefront-text,#1d4ed8)]'
  return 'text-[color:var(--storefront-text,#374151)]'
}

const syncSubStepCompletion = (step: number, completed: boolean) => {
  checkoutStore.setSubStepCompleted(step, completed)
}

let saveTimeout: ReturnType<typeof setTimeout> | null = null
const cancelPendingSave = () => {
  if (saveTimeout) clearTimeout(saveTimeout)
  saveTimeout = null
}
let writeQueue: Promise<unknown> = Promise.resolve()
let passportRefreshFailed = false
const pendingBaselines: Record<string, unknown> = {}
const copyValue = (value: unknown): unknown => value === undefined ? undefined : JSON.parse(JSON.stringify(value))
const sameValue = (left: unknown, right: unknown): boolean => JSON.stringify(left) === JSON.stringify(right)
const recordPendingChanges = (data: Record<string, unknown>) => {
  for (const [key, value] of Object.entries(data)) {
    if (!(key in pendingChanges.value)) pendingBaselines[key] = copyValue(checkoutStore.questionnaireData[key as keyof QuestionnaireData])
    pendingChanges.value[key] = value
  }
}
const passportRefreshError = 'Паспорт сохранён, но не удалось обновить анкету на экране. Повторно откройте заявку.'
function enqueueWrite<T>(operation: () => Promise<T>): Promise<T> {
  const queued = writeQueue.then(operation, operation)
  writeQueue = queued.then(() => undefined, () => undefined)
  return queued
}
const saveQuestionnaire = (): Promise<boolean> => enqueueWrite(performSave)
const persistChanges = async (changes: Record<string, unknown>): Promise<boolean> => {
  if (props.readonly || !props.applicationId) return true
  if (passportRefreshFailed) { saveError.value = passportRefreshError; return false }
  if (!Object.keys(changes).length) return true
  try {
    await notificationRequest(`/api/v1/applications/${props.applicationId}/questionnaire`, { method: 'PUT', baseURL: useRuntimeConfig().public.apiBase, credentials: 'include', body: changes })
    for (const [key, value] of Object.entries(changes)) {
      if (sameValue(pendingChanges.value[key], value)) {
        delete pendingChanges.value[key]
        delete pendingBaselines[key]
      } else if (key in pendingChanges.value) {
        pendingBaselines[key] = copyValue(value)
      }
    }
    saveError.value = ''
    return true
  } catch (error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail
    saveError.value = typeof detail === 'string' ? detail : 'Не удалось сохранить анкету. Проверьте поля и повторите.'
    return false
  }
}
const performSave = async (): Promise<boolean> => {
  if (props.readonly || !props.applicationId) return true
  if (passportRefreshFailed) { saveError.value = passportRefreshError; return false }
  const changes = questionnaireWritePayload(pendingChanges.value)
  if (!Object.keys(changes).length) return true
  if (contactsRef.value?.validate() === false || edoRef.value?.validate() === false) { saveError.value = 'Проверьте выделенные поля анкеты перед сохранением.'; return false }
  return persistChanges(changes)
}
const saveBeneficiaries = (): Promise<boolean> => enqueueWrite(async () => {
  if (props.readonly || !props.applicationId) return false
  // This button saves its section without validating unfinished contact/EDO fields.
  return persistChanges({ beneficiaries: checkoutStore.questionnaireData.beneficiaries, has_beneficiary: checkoutStore.questionnaireData.has_beneficiary })
})
const debouncedSave = () => { cancelPendingSave(); if (!props.readonly) saveTimeout = setTimeout(() => { saveTimeout = null; void saveQuestionnaire() }, 1500) }
const onAdditionalUpdate = (data: Partial<QuestionnaireData>) => { recordPendingChanges(data); checkoutStore.updateQuestionnaireData(data); debouncedSave() }
const personCollections = ['founders', 'beneficiaries', 'other_representatives'] as const
const mergeConfirmedPeople = (current: QuestionnairePerson[], before: QuestionnairePerson[], saved: QuestionnairePerson[], baseline?: QuestionnairePerson[]): QuestionnairePerson[] => current.map(person => {
  if (!person.id) return person
  const previous = before.find(row => row.id === person.id)
  const confirmed = saved.find(row => row.id === person.id)
  const original = baseline?.find(row => row.id === person.id)
  if (!previous || !confirmed || (baseline && !original)) return person
  const unchanged = Object.entries(confirmed).filter(([field]) => {
    const key = field as keyof QuestionnairePerson
    return sameValue(person[key], previous[key]) && (!original || sameValue(person[key], original[key]))
  })
  return { ...person, ...Object.fromEntries(unchanged) }
})
const refreshQuestionnaire = async (before: QuestionnaireData) => {
  try {
    const response = await notificationRequest<{ questionnaire: QuestionnaireData }>(`/api/v1/questionnaire/${props.applicationId}`, { baseURL: useRuntimeConfig().public.apiBase, credentials: 'include' })
    const current = checkoutStore.questionnaireData
    const updates: Record<string, unknown> = Object.fromEntries(Object.entries(response.questionnaire).filter(([key]) => {
      if (personCollections.some(field => field === key)) return false
      const value = current[key as keyof QuestionnaireData]
      return sameValue(value, before[key as keyof QuestionnaireData]) && (!(key in pendingChanges.value) || sameValue(value, pendingBaselines[key]))
    }))
    for (const field of personCollections) {
      if (Array.isArray(current[field]) && Array.isArray(response.questionnaire[field])) {
        const baseline = field in pendingChanges.value ? (pendingBaselines[field] as QuestionnairePerson[] | undefined) || [] : undefined
        updates[field] = mergeConfirmedPeople(current[field] || [], before[field] || [], response.questionnaire[field] || [], baseline)
      }
    }
    checkoutStore.updateQuestionnaireData(updates)
    // Rebase only pending edits; receiving server data does not itself queue a PUT.
    for (const key of Object.keys(pendingChanges.value)) {
      if (key in response.questionnaire) {
        pendingChanges.value[key] = checkoutStore.questionnaireData[key as keyof QuestionnaireData]
        pendingBaselines[key] = copyValue(response.questionnaire[key as keyof QuestionnaireData])
      }
    }
    passportRefreshFailed = false
    saveError.value = ''
  } catch {
    passportRefreshFailed = true
    saveError.value = passportRefreshError
  }
}
const runPassportConfirmation = (confirm: () => Promise<void>): Promise<void> => enqueueWrite(async () => {
  if (props.readonly || !props.applicationId) throw new Error('Анкета недоступна для редактирования')
  const before = JSON.parse(JSON.stringify(checkoutStore.questionnaireData)) as QuestionnaireData
  try { await confirm() }
  finally {
    // Even an interrupted response may have committed the passport on the server.
    await refreshQuestionnaire(before)
  }
})

watch(() => props.readonly, value => { if (value) cancelPendingSave() }, { flush: 'sync' })
onBeforeUnmount(cancelPendingSave)

const onContactsUpdate = (data: FormData) => {
  for (const [key, value] of Object.entries(data)) {
    const old = checkoutStore.questionnaireData[key as keyof QuestionnaireData]
    if (!sameValue(old, value) && !(old == null && (value === '' || value === false))) recordPendingChanges({ [key]: value })
  }
  checkoutStore.updateQuestionnaireData(data as unknown as Record<string, unknown>)
  emit('update', data)
  debouncedSave()
  syncSubStepCompletion(1, contactsRef.value?.isComplete() === true)
}

const onSopdUpdate = (data: Record<string, unknown>) => {
  const values = Object.fromEntries(Object.entries(data).filter(([key]) => key !== 'inviteState' && key !== 'passport'))
  if (Object.keys(values).length) {
    recordPendingChanges(values)
    debouncedSave()
  }
  checkoutStore.updateQuestionnaireData(data)
  syncSubStepCompletion(2, sopdRef.value?.isComplete() === true)
}

const onDocsUpdate = (data: Record<string, unknown>) => {
  recordPendingChanges(data)
  checkoutStore.updateQuestionnaireData(data)
  debouncedSave()
  syncSubStepCompletion(3, docsRef.value?.isComplete() === true)
}

const syncCompletedSubStepsFromMountedForms = async () => {
  await nextTick()
  syncSubStepCompletion(1, contactsRef.value?.isComplete() === true)
  syncSubStepCompletion(2, sopdRef.value?.isComplete() === true)
  syncSubStepCompletion(3, docsRef.value?.isComplete() === true)
}

onMounted(() => {
  void syncCompletedSubStepsFromMountedForms()
})

watch(
  () => [props.companyExternalData, props.initialData] as const,
  () => { void syncCompletedSubStepsFromMountedForms() },
  { deep: true },
)

const validate = (): boolean => contactsRef.value?.validate() !== false && beneficiariesRef.value?.validate() !== false && edoRef.value?.validate() !== false

const getData = (): Record<string, unknown> => {
  return {
    ...questionnaireWritePayload(checkoutStore.questionnaireData),
    ...(contactsRef.value?.getData() ?? {}),
    ...(sopdRef.value?.getData() ?? {}),
    ...(docsRef.value?.getData() ?? {}),
  }
}

const isComplete = (): boolean => true

defineExpose({
  save: saveQuestionnaire,
  validate,
  getData,
  isComplete,
})
</script>
