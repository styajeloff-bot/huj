<template>
  <span v-if="value == null || value === ''" class="text-gray-500">Не указано</span>
  <span v-else-if="typeof value === 'boolean'">{{ value ? 'Да' : 'Нет' }}</span>
  <span v-else-if="typeof value === 'string' || typeof value === 'number'" class="whitespace-pre-wrap break-words">{{ scalarValue }}</span>
  <ul v-else-if="Array.isArray(value)" class="space-y-3"><li v-for="(item, index) in value" :key="index" class="rounded border p-3"><QuestionnaireValue :value="item" :field="field" :application-id="applicationId" :leasing-company-id="leasingCompanyId" :dictionary-names="dictionaryNames" /></li><li v-if="!value.length" class="text-gray-500">Нет сведений</li></ul>
  <div v-else class="space-y-2">
    <p v-if="textValue" class="whitespace-pre-wrap break-words">{{ textValue }}</p>
    <div v-if="consentDocumentId" class="flex flex-wrap gap-3"><a :href="consentDocumentUrl(true)" target="_blank" rel="noopener" class="text-blue-700 underline">Открыть СОПД</a><a :href="consentDocumentUrl(false)" download class="text-blue-700 underline">Скачать СОПД</a></div>
    <div v-for="document in documents" :key="document.document_id" class="flex flex-wrap gap-3"><a :href="documentUrl(document.document_id, true)" target="_blank" rel="noopener" class="text-blue-700 underline">Открыть {{ document.user_title || 'документ' }}</a><a :href="documentUrl(document.document_id, false)" download class="text-blue-700 underline">Скачать</a></div>
    <div v-if="isManagementCompany" class="space-y-2">
      <p class="text-gray-600">{{ questionnaireLabels.requisites }}</p>
      <QuestionnaireValue :value="record.requisites" field="requisites" :application-id="applicationId" :leasing-company-id="leasingCompanyId" :dictionary-names="dictionaryNames" />
    </div>
    <dl v-else-if="!textValue" class="space-y-2"><div v-for="[key, item] in entries" :key="key" class="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-3"><dt class="text-gray-600">{{ questionnaireLabels[key] }}</dt><dd class="min-w-0 break-words"><QuestionnaireValue :value="item" :field="key" :application-id="applicationId" :leasing-company-id="leasingCompanyId" :dictionary-names="dictionaryNames" /></dd></div></dl>
  </div>
</template>
<script setup lang="ts">
import { questionnaireLabels } from '~/features/questionnaire/labels'
import { createDocumentsApi } from '~/features/documents/api/documentsApi'
import { useNotificationCompanyContext } from '~/features/notifications'
const props = defineProps<{ value: unknown; field?: string; applicationId?: string; leasingCompanyId?: string; dictionaryNames?: Record<string, string> }>()
const api = createDocumentsApi(useRuntimeConfig(), () => props.leasingCompanyId, useNotificationCompanyContext())
const record = computed(() => typeof props.value === 'object' && props.value !== null && !Array.isArray(props.value) ? props.value as Record<string, unknown> : {})
const isManagementCompany = computed(() => props.field === 'management_company_details' && 'requisites' in record.value)
const textValue = computed(() => {
  if (isManagementCompany.value) {
    return record.value.status === 'file_attached' && typeof record.value.file_name === 'string' && record.value.file_name
      ? 'Файл приложен: ' + record.value.file_name
      : 'Документ об управляющей компании не предоставлен'
  }
  return typeof record.value.text === 'string' ? record.value.text : ''
})
const consentDocumentId = computed(() => props.applicationId && props.field && typeof record.value.signature_request_id === 'string' ? record.value.signature_request_id : '')
const consentDocumentUrl = (inline: boolean) => api.downloadUrl(`/api/v1/questionnaire/${props.applicationId}/consents/${consentDocumentId.value}/content?field=${encodeURIComponent(props.field || '')}&disposition=${inline ? 'inline' : 'attachment'}`)
const entries = computed(() => Object.entries(record.value).filter(([key]) => Boolean(questionnaireLabels[key]) && !['document_type', 'user_title'].includes(key)))
const scalarValue = computed(() => typeof props.value === 'string' && props.dictionaryNames?.[props.value] ? props.dictionaryNames[props.value] : ['beneficial_owner_basis', 'no_beneficial_owner_reason'].includes(props.field || '') ? 'Сохранённое значение справочника' : props.value === 'male' ? 'Мужской' : props.value === 'female' ? 'Женский' : props.value)
const documents = computed(() => {
  const list = Array.isArray(record.value.documents) ? record.value.documents : typeof record.value.document_id === 'string' ? [record.value] : []
  return list.filter((item): item is { document_id: string; user_title?: string } => typeof item === 'object' && item !== null && typeof (item as { document_id?: unknown }).document_id === 'string')
})
const documentUrl = (id: string, inline: boolean) => api.downloadUrl(`/api/v1/documents/${id}/content${inline ? '?disposition=inline' : ''}`)
</script>
