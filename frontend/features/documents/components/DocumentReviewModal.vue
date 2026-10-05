<template>
  <Modal @close="$emit('close')" size="lg">
    <template #title>
      Рассмотрение документа
    </template>
    
    <div data-storefront-block="client.cabinet" class="space-y-6">
      <!-- Информация о документе -->
      <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
        <h4 class="text-sm font-medium text-[color:var(--storefront-title,#111827)] mb-3">Информация о документе:</h4>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="font-medium text-[color:var(--storefront-text,#374151)]">Название:</span>
            <span class="text-[color:var(--storefront-text,#111827)] ml-2">{{ document.file_name }}</span>
          </div>
          <div>
            <span class="font-medium text-[color:var(--storefront-text,#374151)]">Тип:</span>
            <span class="text-[color:var(--storefront-text,#111827)] ml-2">{{ getDocumentTypeDisplay(document.document_type) }}</span>
          </div>
          <div>
            <span class="font-medium text-[color:var(--storefront-text,#374151)]">Размер:</span>
            <span class="text-[color:var(--storefront-text,#111827)] ml-2">{{ formatFileSize(document.file_size) }}</span>
          </div>
          <div>
            <span class="font-medium text-[color:var(--storefront-text,#374151)]">Загружен:</span>
            <span class="text-[color:var(--storefront-text,#111827)] ml-2">{{ formatDate(document.uploaded_at) }}</span>
          </div>
          <div v-if="document.related_application_display_number">
            <span class="font-medium text-[color:var(--storefront-text,#374151)]">Заявка:</span>
            <span class="text-[color:var(--storefront-text,#111827)] ml-2">{{ document.related_application_display_number }}</span>
          </div>
          <div>
            <span class="font-medium text-[color:var(--storefront-text,#374151)]">Версия:</span>
            <span class="text-[color:var(--storefront-text,#111827)] ml-2">v{{ document.version || 1 }}</span>
          </div>
        </div>
      </div>

      <!-- Предпросмотр документа -->
      <div>
        <h4 class="text-sm font-medium text-[color:var(--storefront-title,#111827)] mb-3">Предпросмотр документа:</h4>
        <div class="border rounded-lg p-4 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]">
          <div class="flex items-center justify-center space-x-4">
            <button
              @click="previewDocument"
              class="btn-secondary"
              :disabled="loadingPreview"
            >
              <div v-if="loadingPreview" class="flex items-center">
                <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#4b5563)] mr-2"></div>
                Загружаем...
              </div>
              <span v-else>Открыть для просмотра</span>
            </button>
            <button
              @click="downloadDocument"
              class="btn-secondary"
            >
              Скачать документ
            </button>
          </div>
        </div>
      </div>

      <!-- Форма рассмотрения -->
      <form @submit.prevent="submitReview" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Статус рассмотрения <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
          </label>
          <div class="space-y-3">
            <label class="flex items-center">
              <input
                type="radio"
                v-model="form.status"
                value="approved"
                class="storefront-control form-radio text-[color:var(--storefront-success-text,#16a34a)]"
                required
              >
              <span class="ml-2 text-sm text-[color:var(--storefront-text,#111827)]">
                <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">Одобрить</span> - документ соответствует требованиям
              </span>
            </label>
            <label class="flex items-center">
              <input
                type="radio"
                v-model="form.status"
                value="rejected"
                class="storefront-control form-radio text-[color:var(--storefront-error-text,#dc2626)]"
                required
              >
              <span class="ml-2 text-sm text-[color:var(--storefront-text,#111827)]">
                <span class="font-medium text-[color:var(--storefront-error-text,#dc2626)]">Отклонить</span> - документ не соответствует требованиям
              </span>
            </label>
            <label class="flex items-center">
              <input
                type="radio"
                v-model="form.status"
                value="revision_required"
                class="storefront-control form-radio text-[color:var(--storefront-warning-text,#ca8a04)]"
                required
              >
              <span class="ml-2 text-sm text-[color:var(--storefront-text,#111827)]">
                <span class="font-medium text-[color:var(--storefront-warning-text,#ca8a04)]">Требуется доработка</span> - нужны исправления
              </span>
            </label>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Комментарий
            <span v-if="form.status === 'rejected' || form.status === 'revision_required'" class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
          </label>
          <textarea
            v-model="form.comments"
            rows="4"
            class="storefront-control form-textarea w-full"
            placeholder="Добавьте комментарий к решению..."
            :required="form.status === 'rejected' || form.status === 'revision_required'"
          ></textarea>
          <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            {{ form.status === 'approved' ? 'Опционально: добавьте комментарий' : 'Обязательно: укажите причину отклонения или требования к доработке' }}
          </p>
        </div>

        <div v-if="form.status === 'revision_required'" class="bg-[color:rgb(var(--storefront-warning-rgb,254_252_232)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fef08a)] rounded-lg p-4">
          <h5 class="text-sm font-medium text-[color:var(--storefront-warning-text,#854d0e)] mb-2">Требования к доработке:</h5>
          <p class="text-sm text-[color:var(--storefront-warning-text,#a16207)]">
            Клиент получит уведомление о необходимости загрузить исправленную версию документа.
            Обязательно укажите в комментарии, что именно нужно исправить.
          </p>
        </div>

        <div class="flex justify-end space-x-3 pt-4">
          <button
            type="button"
            @click="$emit('close')"
            class="btn-secondary"
            :disabled="submitting"
          >
            Отмена
          </button>
          <button
            type="submit"
            class="btn-primary"
            :disabled="!form.status || submitting"
          >
            <div v-if="submitting" class="flex items-center">
              <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#ffffff)] mr-2"></div>
              Сохраняем...
            </div>
            <span v-else>Сохранить решение</span>
          </button>
        </div>
      </form>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import type { ReviewableDocument, DocumentTypeCode } from '~/features/documents/types'

const props = defineProps<{
  document: ReviewableDocument
}>()

const emit = defineEmits(['close', 'success'])

const config = useRuntimeConfig()
const toast = useToast()

const form = ref({
  status: '',
  comments: ''
})

const submitting = ref(false)
const loadingPreview = ref(false)

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

const getDocumentTypeDisplay = (type: string): string => {
  return documentTypes[type] || type
}

const formatFileSize = (bytes: number | undefined): string => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDate = (date: string | undefined): string => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const previewDocument = async () => {
  loadingPreview.value = true

  try {
    const blob = await $fetch<Blob>(`/api/v1/documents/${props.document.id}/content?disposition=inline`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(blob)
    window.open(url, '_blank')
  } catch (err: unknown) {
    toast.error('Ошибка при предпросмотре документа')
  } finally {
    loadingPreview.value = false
  }
}

const downloadDocument = async () => {
  try {
    const blob = await $fetch<Blob>(`/api/v1/documents/${props.document.id}/content`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(blob)
    const link = window.document.createElement('a')
    link.href = url
    link.download = props.document.file_name
    window.document.body.appendChild(link)
    link.click()
    window.document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (err: unknown) {
    toast.error('Ошибка при скачивании документа')
  }
}

const submitReview = async () => {
  submitting.value = true

  try {
    await $fetch(`/api/v1/documents/${props.document.id}/reviews`, {
      method: 'POST',
      body: {
        status: form.value.status,
        comments: form.value.comments
      },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const statusText: Record<string, string> = {
      'approved': 'одобрен',
      'rejected': 'отклонен',
      'revision_required': 'отправлен на доработку'
    }

    toast.success(`Документ ${statusText[form.value.status] || ''}`)
    emit('success')
  } catch (err: unknown) {
    toast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при сохранении решения')
  } finally {
    submitting.value = false
  }
}
</script>