<template>
  <Modal @close="$emit('close')" size="lg">
    <template #title>
      История версий документа
    </template>
    
    <div data-storefront-block="client.cabinet" class="space-y-6">
      <!-- Информация о документе -->
      <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
        <h4 class="text-sm font-medium text-[color:var(--storefront-title,#111827)] mb-2">Документ:</h4>
        <p class="text-sm text-[color:var(--storefront-text,#374151)]">{{ getDocumentTypeDisplay(document.document_type) }}</p>
      </div>

      <div v-if="loading" class="text-center py-8">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем версии...</p>
      </div>

      <div v-else-if="error" class="text-center py-8">
        <div class="bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg p-4">
          <p class="text-[color:var(--storefront-error-text,#dc2626)]">{{ error }}</p>
          <button @click="fetchVersions" class="btn-primary mt-4">
            Попробовать снова
          </button>
        </div>
      </div>

      <div v-else-if="versions.length === 0" class="text-center py-8">
        <p class="text-[color:var(--storefront-text-muted,#6b7280)]">Версии не найдены</p>
      </div>

      <!-- Список версий -->
      <div v-else class="space-y-4">
        <h4 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">Все версии ({{ versions.length }}):</h4>
        
        <div class="space-y-3">
          <div
            v-for="version in versions"
            :key="version.id"
            class="border rounded-lg p-4"
            :class="version.is_current_version ? 'border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : 'border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]'"
          >
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-4">
                <div class="flex-shrink-0">
                  <div class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium"
                    :class="version.is_current_version ? 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]' : 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'">
                    v{{ version.version }}
                  </div>
                </div>
                
                <div class="flex-1">
                  <div class="flex items-center space-x-2">
                    <h5 class="text-sm font-medium text-[color:var(--storefront-title,#111827)]">{{ version.file_name }}</h5>
                    <span v-if="version.is_current_version" 
                      class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]">
                      Текущая версия
                    </span>
                  </div>
                  
                  <div class="flex items-center space-x-4 mt-1">
                    <span class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
                      Загружена: {{ formatDate(version.uploaded_at) }}
                    </span>
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                      :class="getStatusBadgeClass(version.status)">
                      {{ getStatusDisplay(version.status) }}
                    </span>
                  </div>
                </div>
              </div>
              
              <div class="flex items-center space-x-2">
                <button
                  @click="previewVersion(version)"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)] text-sm"
                  title="Предпросмотр"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                  </svg>
                </button>
                <button
                  @click="downloadVersion(version)"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#16a34a)] hover:text-[color:var(--storefront-ghost-hover-foreground,#14532d)] text-sm"
                  title="Скачать"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                  </svg>
                </button>
                <button
                  v-if="canRestoreVersion(version)"
                  @click="restoreVersion(version)"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9333ea)] hover:text-[color:var(--storefront-ghost-hover-foreground,#581c87)] text-sm"
                  title="Восстановить как текущую"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                  </svg>
                </button>
              </div>
            </div>

            <!-- Комментарии к версии -->
            <div v-if="version.comments" class="mt-3 p-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg">
              <p class="text-sm text-[color:var(--storefront-text,#374151)]">{{ version.comments }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="flex justify-end pt-4">
        <button
          @click="$emit('close')"
          class="btn-secondary"
        >
          Закрыть
        </button>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import type { DocVersion, ReviewableDocument, VersionStatus } from '~/features/documents/types'
import type { VersionsResponse } from '~/features/documents/api/documentsApi'

const props = defineProps<{
  document: ReviewableDocument
}>()

const emit = defineEmits(['close'])

const config = useRuntimeConfig()
const authStore = useAuthStore()
const toast = useToast()

const versions = ref<DocVersion[]>([])
const loading = ref(true)
const error = ref('')

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
}

const fetchVersions = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await $fetch<VersionsResponse>(`/api/v1/documents/${props.document.id}/versions`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    versions.value = response.versions as DocVersion[]
  } catch (err: unknown) {
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке версий документа'
  } finally {
    loading.value = false
  }
}

const getDocumentTypeDisplay = (type: string): string => {
  return documentTypes[type] || type
}

const getStatusDisplay = (status: VersionStatus | string): string => {
  const statusMap: Record<string, string> = {
    'uploaded': 'Загружен',
    'under_review': 'На проверке',
    'verified': 'Проверен',
    'rejected': 'Отклонен'
  }
  return statusMap[status] || status
}

const getStatusBadgeClass = (status: VersionStatus | string): string => {
  const classes: Record<string, string> = {
    'uploaded': 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]',
    'under_review': 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#854d0e)]',
    'verified': 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]',
    'rejected': 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]'
  }
  return classes[status] || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
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

const canRestoreVersion = (version: DocVersion): boolean => {
  return !version.is_current_version &&
         !authStore.isLeasingCompany &&
         (authStore.isClient || authStore.isDealer || authStore.isCarCraftEmployee)
}

const previewVersion = async (version: DocVersion) => {
  try {
    const blob = await $fetch<Blob>(`/api/v1/documents/${version.id}/content?disposition=inline`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(blob)
    window.open(url, '_blank')
  } catch (err: unknown) {
    toast.error('Ошибка при предпросмотре версии документа')
  }
}

const downloadVersion = async (version: DocVersion) => {
  try {
    const blob = await $fetch<Blob>(`/api/v1/documents/${version.id}/content`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(blob)
    const link = window.document.createElement('a')
    link.href = url
    link.download = version.file_name
    window.document.body.appendChild(link)
    link.click()
    window.document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (err: unknown) {
    toast.error('Ошибка при скачивании версии документа')
  }
}

const restoreVersion = async (version: DocVersion) => {
  if (!confirm(`Вы уверены, что хотите восстановить версию ${version.version} как текущую?`)) {
    return
  }

  try {
    await $fetch(`/api/v1/documents/${version.id}/restore`, {
      method: 'POST',
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    toast.success(`Версия ${version.version} восстановлена как текущая`)
    await fetchVersions() // Обновляем список версий
  } catch (err: unknown) {
    toast.error('Ошибка при восстановлении версии')
  }
}

onMounted(() => {
  fetchVersions()
})
</script>
