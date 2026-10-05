<template>
  <div data-storefront-block="shared.form" :class="[
    'border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg p-4 transition-colors',
    hasError ? 'border-[color:var(--storefront-error-border,#fca5a5)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] shadow-sm' : 'hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]'
  ]">
    <div class="flex items-start justify-between mb-3">
      <div class="flex items-start space-x-2 flex-1">
        <div v-if="hasError" class="mt-0.5">
          <svg class="w-5 h-5 text-[color:var(--storefront-error-icon,#ef4444)]" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clip-rule="evenodd" />
          </svg>
        </div>
        <div class="flex-1">
          <h5 :class="[
            'font-medium',
            hasError ? 'text-[color:var(--storefront-error-text,#7f1d1d)]' : 'text-[color:var(--storefront-title,#111827)]'
          ]">{{ requirement.display_name }}</h5>
          <p v-if="requirement.description || formatDescription" :class="[
            'text-xs mt-1',
            hasError ? 'text-[color:var(--storefront-error-text,#b91c1c)]' : 'text-[color:var(--storefront-text-muted,#4b5563)]'
          ]">
            {{ formatDescription || requirement.description }}
          </p>
        </div>
      </div>
      <div v-if="personName" class="flex items-center ml-2">
        <span class="text-sm text-[color:var(--storefront-text,#374151)] font-medium">
          {{ personName }}
        </span>
      </div>
    </div>
    
    <div class="space-y-3">
      <div v-if="userDocuments.length > 0">
        <label v-if="!useSelect" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
          Выберите документ:
        </label>
        <select class="storefront-control"
          v-if="useSelect"
          v-model="selectedDocument"
          :multiple="maxFiles > 1"
          :class="{
            'select-field text-sm py-1': true,
            'border-[color:var(--storefront-error-border,#ef4444)]': hasError
          }"
          @change="handleExistingDocumentSelect"
        >
          <option v-if="maxFiles === 1" value="">Выберите существующий документ</option>
          <option v-for="doc in userDocuments" :key="doc.id" :value="doc.id">
            {{ doc.file_name }} ({{ formatDate(doc.uploaded_at) }})
          </option>
        </select>
        <div v-else class="space-y-2">
          <div v-for="doc in userDocuments" :key="doc.id"
               class="flex items-center p-3 border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
            <input 
              :id="`doc-${requirement.document_type}-${doc.id}`"
              v-model="selectedDocument"
              :value="doc.id"
              type="radio"
              :name="`document-${requirement.document_type}`"
              @change="handleExistingDocumentSelect"
              class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)]"
            >
            <div class="ml-3 flex-1">
              <label :for="`doc-${requirement.document_type}-${doc.id}`" 
                     class="block text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                {{ doc.file_name }}
              </label>
              <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
                Загружен: {{ formatDate(doc.uploaded_at) }}
                <span v-if="doc.status === 'verified'" class="ml-2 text-[color:var(--storefront-success-text,#16a34a)]">✓ Проверен</span>
                <span v-else-if="doc.status === 'under_review'" class="ml-2 text-[color:var(--storefront-warning-text,#ca8a04)]">⏳ На проверке</span>
              </p>
            </div>
          </div>
        </div>
      </div>
      
      <div class="flex items-center">
        <input 
          :id="`upload-${requirement.document_type}`"
          type="file"
          :accept="acceptedFileTypes"
          :multiple="maxFiles > 1"
          @change="handleFileUpload"
          class="storefront-control hidden"
          :disabled="isProcessing"
        >
        <label :for="`upload-${requirement.document_type}`" :class="[
          'cursor-pointer text-sm py-1 px-3 rounded-md transition-colors duration-200',
          hasError
            ? 'bg-[color:rgb(var(--storefront-destructive-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-destructive-foreground,#b91c1c)] border border-[color:var(--storefront-destructive-border,#fca5a5)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_202_202)/var(--tw-bg-opacity,1))]'
            : 'btn-secondary',
          isProcessing ? 'opacity-50 cursor-not-allowed' : ''
        ]" :disabled="isProcessing">
          <span class="flex items-center space-x-1">
            <svg v-if="!isProcessing" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <div v-else class="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
            <span>{{ isProcessing ? 'Обработка...' : (useSelect ? 'Загрузить новый' : 'Выбрать файл') }}</span>
          </span>
        </label>
        <span v-if="uploadedFileLabel && !isProcessing"
          class="text-sm text-[color:var(--storefront-success-text,#16a34a)] ml-2 flex items-center space-x-1">
          <svg class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{{ uploadedFileLabel }}</span>
        </span>
        <span v-if="isProcessing"
          class="text-sm text-[color:var(--storefront-text-muted,#2563eb)] ml-2 flex items-center space-x-1">
          <div class="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
          <span>Обработка документа...</span>
        </span>
        <button v-if="uploadedFileLabel && !isProcessing"
          @click="handleRemoveFile" type="button"
          class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)] text-sm ml-2 flex items-center space-x-1 transition-colors duration-200">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
          <span>Удалить</span>
        </button>
      </div>
      
      <div v-if="uploadedFileDetails && !useSelect" 
           class="p-3 bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)] rounded-lg">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium text-[color:var(--storefront-text,#1e3a8a)]">
              {{ uploadedFileDetails.name }}
            </p>
            <p class="text-xs text-[color:var(--storefront-text,#1d4ed8)]">
              {{ uploadedFileDetails.sizeLabel }}
            </p>
          </div>
        </div>
      </div>

      <div v-if="validationError"
        class="mt-2 p-2 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border-l-4 border-[color:var(--storefront-error-border,#ef4444)] rounded-r">
        <div class="flex items-start space-x-2">
          <svg class="w-4 h-4 text-[color:var(--storefront-error-icon,#ef4444)] mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clip-rule="evenodd" />
          </svg>
          <p class="text-[color:var(--storefront-error-text,#b91c1c)] text-sm font-medium">
            {{ validationError }}
          </p>
        </div>
      </div>

      <div v-if="recognitionError"
        class="mt-2 p-3 bg-[color:rgb(var(--storefront-warning-rgb,255_247_237)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fdba74)] rounded-md">
        <div class="flex items-start justify-between">
          <div class="flex items-start space-x-2">
            <svg class="w-5 h-5 text-[color:var(--storefront-warning-icon,#f97316)] mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clip-rule="evenodd" />
            </svg>
            <div>
              <p class="text-[color:var(--storefront-warning-text,#9a3412)] text-sm font-medium">Ошибка распознавания</p>
              <p class="text-[color:var(--storefront-warning-text,#c2410c)] text-xs mt-1">{{ recognitionError }}</p>
            </div>
          </div>
          <button v-if="showRetryButton" type="button" @click="handleRetry"
            class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#c2410c)] hover:text-[color:var(--storefront-ghost-hover-foreground,#7c2d12)] font-medium underline ml-2">
            Повторить
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'

interface DocRequirement {
  display_name: string
  description?: string
  document_type: string
  validation_rules?: { max_files?: number | string }
  [key: string]: unknown
}

interface UserDocument {
  id: number
  file_name: string
  uploaded_at: string
  status?: string
  [key: string]: unknown
}

const props = defineProps({
  requirement: {
    type: Object as PropType<DocRequirement>,
    required: true
  },
  userDocuments: {
    type: Array as PropType<UserDocument[]>,
    default: () => []
  },
  validationError: {
    type: String,
    default: ''
  },
  recognitionError: {
    type: String,
    default: ''
  },
  isProcessing: {
    type: Boolean,
    default: false
  },
  useSelect: {
    type: Boolean,
    default: false
  },
  formatDescription: {
    type: String,
    default: ''
  },
  acceptedFileTypes: {
    type: String,
    default: '.pdf,.jpg,.jpeg,.png,.doc,.docx,.xlsx'
  },
  showRetryButton: {
    type: Boolean,
    default: false
  },
  personName: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['file-upload', 'existing-document-select', 'remove-file', 'retry'])

const selectedDocument = defineModel<string | number | number[] | null>('selectedDocument')
const uploadedFile = defineModel<File | File[] | null>('uploadedFile')

const { formatDate } = useFormatDate()

const hasError = computed(() => {
  return !!(props.validationError || props.recognitionError)
})

const maxFiles = computed(() => {
  const raw = props.requirement?.validation_rules?.max_files
  const value = typeof raw === 'number' ? raw : parseInt(String(raw), 10)
  return Number.isFinite(value) && value > 0 ? value : 1
})

const normalizeFiles = (value: File | File[] | null | undefined): File[] => {
  if (!value) return []
  return Array.isArray(value) ? value : [value]
}

const uploadedFileLabel = computed(() => {
  const files = normalizeFiles(uploadedFile.value)
  if (files.length === 0) return ''
  if (files.length === 1) return files[0]?.name || ''
  return `Выбрано файлов: ${files.length}`
})

const uploadedFileDetails = computed(() => {
  const files = normalizeFiles(uploadedFile.value)
  if (files.length === 0) return null
  if (files.length === 1) {
    const f = files[0]
    return f ? { name: f.name, sizeLabel: formatFileSize(f.size) } : null
  }
  const totalSize = files.reduce((sum, f) => sum + (f?.size || 0), 0)
  return { name: files.map(f => f?.name).filter(Boolean).join(', '), sizeLabel: formatFileSize(totalSize) }
})

const validateFileFormat = (file: File) => {
  if (!file?.name) return true
  if (!props.acceptedFileTypes) return true
  const allowed = props.acceptedFileTypes
    .split(',')
    .map(s => s.trim().toLowerCase())
    .filter(Boolean)
  if (allowed.length === 0) return true
  const fileName = file.name.toLowerCase()
  return allowed.some(ext => fileName.endsWith(ext))
}

const isSameFile = (a: File | null, b: File | null) => {
  return a && b &&
    a.name === b.name &&
    a.size === b.size &&
    a.type === b.type &&
    a.lastModified === b.lastModified
}

const handleFileUpload = (event: Event) => {
  const target = event.target as HTMLInputElement
  const filesList = Array.from(target?.files || [])
  if (filesList.length === 0) {
    if (uploadedFile.value) {
      uploadedFile.value = null
    }
    return
  }

  const invalid = filesList.find(f => !validateFileFormat(f))
  if (invalid) {
    if (target) target.value = ''
    return
  }

  const current = normalizeFiles(uploadedFile.value)
  const merged = [...current]
  for (const f of filesList) {
    if (!merged.some(existing => isSameFile(existing, f))) {
      merged.push(f)
    }
  }

  const limited = merged.slice(0, maxFiles.value)
  uploadedFile.value = maxFiles.value > 1 ? limited : limited[0]
  selectedDocument.value = null
  emit('file-upload', { documentType: props.requirement.document_type, files: limited })
  if (target) target.value = ''
}

const handleExistingDocumentSelect = () => {
  uploadedFile.value = null
  
  const inputElement = document.getElementById(`upload-${props.requirement.document_type}`) as HTMLInputElement | null
  if (inputElement) {
    inputElement.value = ''
  }

  emit('existing-document-select', props.requirement.document_type)
}

const handleRemoveFile = () => {
  uploadedFile.value = null

  const inputElement = document.getElementById(`upload-${props.requirement.document_type}`) as HTMLInputElement | null
  if (inputElement) {
    inputElement.value = ''
  }

  emit('remove-file', props.requirement.document_type)
}

const handleRetry = () => {
  const inputElement = document.getElementById(`upload-${props.requirement.document_type}`) as HTMLInputElement | null
  if (inputElement) {
    inputElement.value = ''
    inputElement.click()
  }
  
  emit('retry', props.requirement.document_type)
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}
</script>

<style scoped>
.select-field {
  @apply w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)];
}

.btn-secondary {
  @apply bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)] px-4 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-offset-2;
}
</style>

