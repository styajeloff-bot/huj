<template>
  <Modal @close="$emit('close')">
    <template #title>
      {{ parentDocument ? 'Загрузить новую версию документа' : 'Загрузить документ' }}
    </template>
    
    <div data-storefront-block="client.cabinet" class="space-y-6">
      <div v-if="parentDocument" class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
        <h4 class="text-sm font-medium text-[color:var(--storefront-title,#1e3a8a)] mb-2">Текущий документ:</h4>
        <p class="text-sm text-[color:var(--storefront-text,#1d4ed8)]">{{ parentDocument.file_name }}</p>
        <p class="text-xs text-[color:var(--storefront-text-muted,#2563eb)]">Версия: {{ parentDocument.version || 1 }}</p>
      </div>

      <form @submit.prevent="uploadDocument" class="space-y-4">
        <div v-if="!parentDocument">
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Тип документа <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
          </label>
          <select 
            v-model="form.document_type" 
            class="storefront-control form-select w-full"
            required
          >
            <option value="">Выберите тип документа</option>
            <option 
              v-for="(name, type) in documentTypes" 
              :key="type" 
              :value="type"
            >
              {{ name }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Связать с заявкой
          </label>
          <select 
            v-model="form.related_application_id" 
            class="storefront-control form-select w-full"
          >
            <option value="">Не привязывать к заявке</option>
            <option 
              v-for="app in applications" 
              :key="app.id" 
              :value="app.id"
            >
              Заявка {{ formatApplicationNumber(app) }} ({{ formatDate(app.created_at) }})
            </option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Файл документа <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
          </label>
          <FileDropZone
            @file-selected="onFileSelected"
            @file-error="onFileError"
            :accepted-types="acceptedFileTypes"
            :max-size-mb="10"
          />
          <div v-if="fileError" class="mt-2 text-sm text-[color:var(--storefront-error-text,#dc2626)]">
            {{ fileError }}
          </div>
        </div>

        <div v-if="form.selectedFile" class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-3">
              <svg class="w-8 h-8 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
                </path>
              </svg>
              <div>
                <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">{{ form.selectedFile.name }}</div>
                <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ formatFileSize(form.selectedFile.size) }}</div>
              </div>
            </div>
            <button
              type="button"
              @click="removeFile"
              class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)]"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </button>
          </div>
        </div>

        <div class="flex justify-end space-x-3 pt-4">
          <button
            type="button"
            @click="$emit('close')"
            class="btn-secondary"
            :disabled="uploading"
          >
            Отмена
          </button>
          <button
            type="submit"
            class="btn-primary"
            :disabled="!canUpload || uploading"
          >
            <div v-if="uploading" class="flex items-center">
              <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#ffffff)] mr-2"></div>
              Загружаем...
            </div>
            <span v-else>
              {{ parentDocument ? 'Загрузить новую версию' : 'Загрузить документ' }}
            </span>
          </button>
        </div>
      </form>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import type { ReviewableDocument, ApplicationRef } from '~/features/documents/types'
import { formatApplicationNumber } from '~/utils'

interface UploadForm {
  document_type: string
  related_application_id: string
  selectedFile: File | null
}

interface ApplicationsListResponse {
  applications?: ApplicationRef[]
}

const props = defineProps<{
  parentDocument?: ReviewableDocument | null
}>()

const emit = defineEmits(['close', 'success'])

const config = useRuntimeConfig()
const toast = useToast()

const form = ref<UploadForm>({
  document_type: props.parentDocument?.document_type || '',
  related_application_id: props.parentDocument?.related_application_id?.toString() || '',
  selectedFile: null
})

const applications = ref<ApplicationRef[]>([])
const uploading = ref(false)
const fileError = ref('')

const documentTypes: Record<string, string> = {
  'passport_general_director': 'Паспорт генерального директора',
  'questionnaire': 'Анкета',
  'consent_personal_data': 'Согласие на обработку персональных данных',
  'enterprise_card': 'Карточка предприятия',
  'account_51_card': 'Справка по счету 51',
  'income_declaration': 'Декларация о доходах',
  'passport_founder': 'Паспорт учредителя',
  'company_charter': 'Устав компании',
  'lease_agreement_copy': 'Копия договора лизинга',
  'passport': 'Паспорт',
  'inn_certificate': 'Справка ИНН',
  'income_certificate': 'Справка о доходах',
  'bank_statement': 'Справка из банка',
  'employment_certificate': 'Справка с работы',
  'company_registration': 'Свидетельство о регистрации',
  'balance_sheet': 'Бухгалтерский баланс',
  'tax_return': 'Налоговая декларация',
  'other': 'Другое'
}

const acceptedFileTypes = ['.pdf', '.jpg', '.jpeg', '.png', '.docx', '.xlsx']

const canUpload = computed(() => {
  return form.value.selectedFile &&
         (props.parentDocument || form.value.document_type)
})

const fetchApplications = async () => {
  try {
    // Ordinary applications only: the dealer/distributor list also contains fast deals by default.
    const response = await $fetch<ApplicationsListResponse>('/api/v1/applications', {
      baseURL: config.public.apiBase,
      credentials: 'include',
      query: { kind: 'application' }
    })
    applications.value = response.applications || []
  } catch (err: unknown) {
    console.error('Ошибка при загрузке заявок:', err)
  }
}

const onFileSelected = (file: File) => {
  form.value.selectedFile = file
  fileError.value = ''
}

const onFileError = (error: string) => {
  fileError.value = error
  form.value.selectedFile = null
}

const removeFile = () => {
  form.value.selectedFile = null
  fileError.value = ''
}

const formatFileSize = (bytes: number): string => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDate = (date: string): string => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

const uploadDocument = async () => {
  if (!canUpload.value || !form.value.selectedFile) return

  uploading.value = true

  try {
    const formData = new FormData()
    formData.append('files', form.value.selectedFile)
    if (!props.parentDocument) {
      formData.append('document_type', form.value.document_type)
      if (form.value.related_application_id) {
        formData.append('application_id', form.value.related_application_id)
      }
    } else {
      formData.append('parent_document_id', String(props.parentDocument.id))
    }

    await $fetch('/api/v1/documents', {
      method: 'POST',
      body: formData,
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    emit('success')
  } catch (err: unknown) {
    toast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке документа')
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  fetchApplications()
})
</script>
