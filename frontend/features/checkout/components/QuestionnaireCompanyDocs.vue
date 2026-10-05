<template>
  <div data-storefront-block="client.checkout" class="space-y-3 sm:space-y-4">
    <QuestionnaireFiles :application-id="props.applicationId" />
    <DirectorSignedDocumentsSection
      :application-id="props.applicationId ?? null"
      :company-inn="props.companyInn ?? null"
      :initial-tax-system="props.initialTaxSystem"
      :tax-system-auto="props.taxSystemAuto"
      @tax-system-change="onTaxSystemChange"
      @completion-change="onCompletionChange"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import QuestionnaireFiles from '~/features/questionnaire/components/QuestionnaireFiles.vue'
import DirectorSignedDocumentsSection from './DirectorSignedDocumentsSection.vue'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  applicationId?: UUID | null
  companyInn?: string | null
  initialTaxSystem?: string | null
  initialUploaded?: boolean
  taxSystemAuto?: boolean
}>()

const emit = defineEmits<{
  (e: 'update', data: Record<string, unknown>): void
}>()

const persistedByValue: Record<string, string> = {
  osn: 'ОСН',
  usn: 'УСН',
  patent: 'Патент',
  ausn: 'АвтоУСН',
}

const currentTaxSystem = ref(_initialTaxSystem())
const hasUploadedCompanyDocs = ref(Boolean(props.initialUploaded))

watch(
  () => props.initialTaxSystem,
  (value) => {
    if (value?.trim()) currentTaxSystem.value = value
  },
)

watch(
  () => props.initialUploaded,
  (value) => {
    hasUploadedCompanyDocs.value = Boolean(value)
  },
)

const validate = (): boolean => {
  return currentTaxSystem.value.trim().length > 0
}

const getData = (): Record<string, unknown> => {
  return {
    tax_system: currentTaxSystem.value,
    tax_system_auto: props.taxSystemAuto,
    company_docs_uploaded: hasUploadedCompanyDocs.value,
  }
}

const isComplete = (): boolean => {
  return hasUploadedCompanyDocs.value
}

const onTaxSystemChange = (value: string) => {
  const nextValue = persistedByValue[value] ?? value
  currentTaxSystem.value = nextValue
  emit('update', getData())
}

const onCompletionChange = (completed: boolean) => {
  hasUploadedCompanyDocs.value = completed
  emit('update', getData())
}

function _initialTaxSystem(): string {
  return props.initialTaxSystem?.trim() || 'ОСН'
}

defineExpose({
  validate,
  getData,
  isComplete,
})
</script>
