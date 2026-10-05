<template>
  <div data-storefront-block="client.cabinet" class="bg-transparent">
    <div class="flex items-center justify-between mb-6">
      <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">Мои документы</h3>
      <div class="flex items-center space-x-4">
        <button 
          @click="showUploadModal = true" 
          class="btn-primary"
        >
          Загрузить документ
        </button>
        <button 
          @click="refreshDocuments" 
          class="btn-secondary"
          :disabled="loading"
        >
          Обновить
        </button>
      </div>
    </div>

    <!-- Фильтры -->
    <div class="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4">
      <div>
        <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">Фильтр по заявкам</label>
        <select 
          v-model="filters.applicationId" 
          class="storefront-control form-select w-full"
          @change="applyFilters"
        >
          <option value="">Все документы</option>
          <option 
            v-for="app in applications" 
            :key="app.id" 
            :value="app.id"
          >
            Заявка {{ formatApplicationNumber(app as any) }} ({{ formatDate(app.created_at) }})
          </option>
        </select>
      </div>
      
      <div>
        <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">Тип документа</label>
        <select 
          v-model="filters.documentType" 
          class="storefront-control form-select w-full"
          @change="applyFilters"
        >
          <option value="">Все типы</option>
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
        <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">Статус</label>
        <select 
          v-model="filters.status" 
          class="storefront-control form-select w-full"
          @change="applyFilters"
        >
          <option value="">Все статусы</option>
          <option value="uploaded">Загружен</option>
          <option value="under_review">На проверке</option>
          <option value="verified">Проверен</option>
          <option value="rejected">Отклонен</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем документы...</p>
    </div>

    <div v-else-if="error" class="text-center py-8">
      <div class="bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg p-4">
        <p class="text-[color:var(--storefront-error-text,#dc2626)]">{{ error }}</p>
        <button @click="fetchDocuments" class="btn-primary mt-4">
          Попробовать снова
        </button>
      </div>
    </div>

    <div v-else-if="filteredDocuments.length === 0" class="text-center py-12">
      <svg class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
        </path>
      </svg>
      <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-2">
        {{ hasFilters ? 'Документы не найдены' : 'Документы не загружены' }}
      </h3>
      <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-4">
        {{ hasFilters ? 'Попробуйте изменить параметры фильтра' : 'Загрузите документы для ускорения процесса рассмотрения заявок' }}
      </p>
    </div>

    <!-- Таблица документов -->
    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
        <thead class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
          <tr>
            <th 
              scope="col" 
              class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
              @click="sortBy('file_name')"
            >
              <div class="flex items-center space-x-1">
                <span>Название файла</span>
                <svg v-if="sortField === 'file_name'" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path v-if="sortDirection === 'asc'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path>
                  <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
              </div>
            </th>
            <th 
              scope="col" 
              class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
              @click="sortBy('document_type')"
            >
              <div class="flex items-center space-x-1">
                <span>Тип документа</span>
                <svg v-if="sortField === 'document_type'" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path v-if="sortDirection === 'asc'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path>
                  <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
              </div>
            </th>
            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
              Заявка
            </th>
            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
              Версия
            </th>
            <th 
              scope="col" 
              class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
              @click="sortBy('status')"
            >
              <div class="flex items-center space-x-1">
                <span>Статус</span>
                <svg v-if="sortField === 'status'" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path v-if="sortDirection === 'asc'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path>
                  <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
              </div>
            </th>
            <th scope="col" class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
              Размер
            </th>
            <th 
              scope="col" 
              class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider cursor-pointer hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
              @click="sortBy('uploaded_at')"
            >
              <div class="flex items-center space-x-1">
                <span>Дата загрузки</span>
                <svg v-if="sortField === 'uploaded_at'" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path v-if="sortDirection === 'asc'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path>
                  <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                </svg>
              </div>
            </th>
            <th v-if="authStore.isLeasingCompany" scope="col" class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
              Статус лизинговой компании
            </th>
            <th scope="col" class="px-6 py-3 text-right text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
              Действия
            </th>
          </tr>
        </thead>
        <tbody class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
          <tr 
            v-for="document in sortedDocuments" 
            :key="document.id"
            class="hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
          >
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="flex items-center">
                <div class="flex-shrink-0">
                  <svg class="w-8 h-8 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
                    </path>
                  </svg>
                </div>
                <div class="ml-4">
                  <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">{{ document.file_name }}</div>
                  <div v-if="document.comments" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ document.comments }}</div>
                </div>
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span class="text-sm text-[color:var(--storefront-text,#111827)]">{{ getDocumentTypeDisplay(document.document_type) }}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span
                v-if="document.related_application_display_number"
                class="text-sm text-[color:var(--storefront-text-muted,#2563eb)]"
              >
                {{ document.related_application_display_number }}
              </span>
              <span v-else class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">—</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="flex items-center space-x-2">
                <span class="text-sm text-[color:var(--storefront-text,#111827)]">v{{ document.version || 1 }}</span>
                <button 
                  v-if="document.parent_document_id || hasVersions(document)"
                  @click="showVersions(document)"
                  class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
                >
                  Показать версии
                </button>
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                :class="getStatusBadgeClass(document.status)">
                {{ getStatusDisplay(document.status) }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ formatFileSize(document.file_size) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ formatDate(document.uploaded_at) }}
            </td>
            <td v-if="authStore.isLeasingCompany" class="px-6 py-4 whitespace-nowrap">
              <div class="flex items-center space-x-2">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
                  :class="getLeasingCompanyStatusBadgeClass(document.leasing_company_status)">
                  {{ getLeasingCompanyStatusDisplay(document.leasing_company_status) }}
                </span>
                <button 
                  v-if="canReviewDocument(document)"
                  @click="reviewDocument(document)"
                  class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
                >
                  Рассмотреть
                </button>
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
              <div class="flex items-center justify-end space-x-2">
                <button
                  @click="previewDocument(document)"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)]"
                  title="Предпросмотр"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                  </svg>
                </button>
                <button
                  @click="downloadDocument(document)"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#16a34a)] hover:text-[color:var(--storefront-ghost-hover-foreground,#14532d)]"
                  title="Скачать"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                  </svg>
                </button>
                <button
                  v-if="canUploadNewVersion(document)"
                  @click="uploadNewVersion(document)"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9333ea)] hover:text-[color:var(--storefront-ghost-hover-foreground,#581c87)]"
                  title="Загрузить новую версию"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
                  </svg>
                </button>
                <button
                  v-if="canDeleteDocument(document)"
                  @click="deleteDocument(document)"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#7f1d1d)]"
                  title="Удалить"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                  </svg>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Модальные окна -->
    <DocumentUploadModal 
      v-if="showUploadModal" 
      :parent-document="uploadingNewVersionFor"
      @close="closeUploadModal"
      @success="handleUploadSuccess" 
    />
    
    <DocumentReviewModal
      v-if="showReviewModal && reviewingDocument"
      :document="reviewingDocument"
      @close="closeReviewModal"
      @success="handleReviewSuccess"
    />

    <DocumentVersionsModal
      v-if="showVersionsModal && viewingVersionsFor"
      :document="viewingVersionsFor"
      @close="closeVersionsModal"
    />
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { formatApplicationNumber } from '~/utils'
import DocumentUploadModal from '~/features/documents/components/DocumentUploadModal.vue'
import DocumentReviewModal from '~/features/documents/components/DocumentReviewModal.vue'
import DocumentVersionsModal from '~/features/documents/components/DocumentVersionsModal.vue'
import type { UUID } from '~/types/ids'

interface DocumentItem {
  id: UUID
  file_name: string
  document_type: string
  status: string
  file_size: number
  uploaded_at: string
  comments?: string
  related_application_id?: UUID | null
  parent_document_id?: UUID | null
  version?: number
  leasing_company_status?: string
  [key: string]: unknown
}

interface ApplicationItem {
  id: UUID
  created_at: string
  selected_leasing_companies?: string[]
}

type DocumentStatus = 'uploaded' | 'under_review' | 'verified' | 'rejected'
type LeasingCompanyStatus = 'pending' | 'approved' | 'rejected' | 'revision_required'
type SortField = 'file_name' | 'document_type' | 'status' | 'uploaded_at'

interface DocumentsResponse {
  documents: DocumentItem[]
}

interface ApplicationsResponse {
  applications?: ApplicationItem[]
}

interface PreviewResponse {
  success: boolean
  preview_url?: string
}

interface DownloadResponse {
  success: boolean
  download_url?: string
  file_name?: string
}

const authStore = useAuthStore()
const config = useRuntimeConfig()
const toast = useToast()

const documents = ref<DocumentItem[]>([])
const applications = ref<ApplicationItem[]>([])
const loading = ref(true)
const error = ref('')

const showUploadModal = ref(false)
const showReviewModal = ref(false)
const showVersionsModal = ref(false)
const uploadingNewVersionFor = ref<DocumentItem>()
const reviewingDocument = ref<DocumentItem>()
const viewingVersionsFor = ref<DocumentItem>()

const filters = ref({
  applicationId: '',
  documentType: '',
  status: ''
})

const sortField = ref<SortField>('uploaded_at')
const sortDirection = ref<'asc' | 'desc'>('desc')

const documentTypes = ref<Record<string, string>>({})

const fetchDocumentTypes = async () => {
  try {
    const response = await $fetch<{ types?: { type_code: string; display_name: string }[] }>('/api/v1/documents/types', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    if (response.types) {
      const typesMap: Record<string, string> = {}
      response.types.forEach((t: { type_code: string; display_name: string }) => {
        typesMap[t.type_code] = t.display_name
      })
      documentTypes.value = typesMap
    }
  } catch (err) {
    console.error('Ошибка при загрузке типов документов:', err)
  }
}

const hasFilters = computed(() => {
  return filters.value.applicationId || filters.value.documentType || filters.value.status
})

const filteredDocuments = computed(() => {
  let result = documents.value

  if (filters.value.applicationId) {
    result = result.filter(doc => String(doc.related_application_id) === filters.value.applicationId)
  }

  if (filters.value.documentType) {
    result = result.filter(doc => doc.document_type === filters.value.documentType)
  }

  if (filters.value.status) {
    result = result.filter(doc => doc.status === filters.value.status)
  }

  return result
})

const sortedDocuments = computed(() => {
  const sorted = [...filteredDocuments.value]

  sorted.sort((a, b) => {
    const field = sortField.value
    const aDoc = a as Record<string, unknown>
    const bDoc = b as Record<string, unknown>
    let aRaw: unknown = aDoc[field]
    let bRaw: unknown = bDoc[field]

    if (field === 'uploaded_at') {
      aRaw = new Date(aRaw as string)
      bRaw = new Date(bRaw as string)
    }

    if ((aRaw as string | number | Date) < (bRaw as string | number | Date)) return sortDirection.value === 'asc' ? -1 : 1
    if ((aRaw as string | number | Date) > (bRaw as string | number | Date)) return sortDirection.value === 'asc' ? 1 : -1
    return 0
  })

  return sorted
})

const fetchDocuments = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await $fetch<DocumentsResponse>('/api/v1/documents?scope=user&enhanced=true', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    documents.value = response.documents
  } catch (err: unknown) {
    const fetchErr = err as { data?: { error?: string } }
    error.value = fetchErr.data?.error || 'Ошибка при загрузке документов'
  } finally {
    loading.value = false
  }
}

const fetchApplications = async () => {
  try {
    const response = await $fetch<ApplicationsResponse>('/api/v1/applications', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    applications.value = response.applications || []
  } catch (err) {
    console.error('Ошибка при загрузке заявок:', err)
  }
}

const refreshDocuments = () => {
  fetchDocuments()
}

const applyFilters = () => {
  // Фильтрация происходит автоматически через computed свойство
}

const sortBy = (field: SortField) => {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDirection.value = 'asc'
  }
}

const getDocumentTypeDisplay = (type: string) => {
  return documentTypes.value[type] || type
}

const getStatusDisplay = (status: string) => {
  const statusMap: Record<string, string> = {
    'uploaded': 'Загружен',
    'under_review': 'На проверке',
    'verified': 'Проверен',
    'rejected': 'Отклонен'
  }
  return statusMap[status] || status
}

const getStatusBadgeClass = (status: string) => {
  const classes: Record<string, string> = {
    'uploaded': 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]',
    'under_review': 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#854d0e)]',
    'verified': 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]',
    'rejected': 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]'
  }
  return classes[status] || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
}

const getLeasingCompanyStatusDisplay = (status: string | undefined) => {
  if (!status) return ''
  const statusMap: Record<string, string> = {
    'pending': 'Ожидает рассмотрения',
    'approved': 'Одобрен',
    'rejected': 'Отклонен',
    'revision_required': 'Требуется доработка'
  }
  return statusMap[status] || status
}

const getLeasingCompanyStatusBadgeClass = (status: string | undefined) => {
  if (!status) return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
  const classes: Record<string, string> = {
    'pending': 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]',
    'approved': 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]',
    'rejected': 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]',
    'revision_required': 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#854d0e)]'
  }
  return classes[status] || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
}

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const formatDate = (date: string | undefined) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const hasVersions = (document: DocumentItem) => {
  return documents.value.some(doc => 
    doc.parent_document_id === document.id || 
    (doc.parent_document_id && doc.parent_document_id === document.parent_document_id)
  )
}

const canReviewDocument = (document: DocumentItem) => {
  if (!authStore.isLeasingCompany || document.leasing_company_status !== 'pending') {
    return false
  }

  // Проверяем, что документ связан с заявкой, где участвует эта лизинговая компания
  if (!document.related_application_id) {
    return false
  }

  // Находим заявку и проверяем, есть ли наша лизинговая компания в selected_leasing_companies
  const application = applications.value.find(app => app.id === document.related_application_id)
  if (!application || !application.selected_leasing_companies) {
    return false
  }

  const user = authStore.user as Record<string, unknown> | null
  const companyId = user?.company_id
  return typeof companyId === 'string' && application.selected_leasing_companies.includes(companyId)
}

const canUploadNewVersion = (_document: DocumentItem) => {
  return !authStore.isLeasingCompany && (authStore.isClient || authStore.isDealer)
}

const canDeleteDocument = (_document: DocumentItem) => {
  return !authStore.isLeasingCompany && (authStore.isClient || authStore.isDealer || authStore.isCarCraftEmployee)
}

const previewDocument = async (document: DocumentItem) => {
  try {
    const blob = await $fetch<Blob>(`/api/v1/documents/${document.id}/content?disposition=inline`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(blob)
    window.open(url, '_blank')
  } catch (err) {
    console.error('Preview error:', err)
    toast.error('Ошибка при предпросмотре документа')
  }
}

const downloadDocument = async (doc: DocumentItem) => {
  try {
    const blob = await $fetch<Blob>(`/api/v1/documents/${doc.id}/content`, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      responseType: 'blob'
    })
    const url = window.URL.createObjectURL(blob)
    const link = window.document.createElement('a')
    link.href = url
    link.download = doc.file_name
    window.document.body.appendChild(link)
    link.click()
    window.document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (err) {
    console.error('Download error:', err)
    toast.error('Ошибка при скачивании документа')
  }
}

const uploadNewVersion = (document: DocumentItem) => {
  uploadingNewVersionFor.value = document
  showUploadModal.value = true
}

const deleteDocument = async (document: DocumentItem) => {
  if (!confirm('Вы уверены, что хотите удалить этот документ?')) {
    return
  }

  try {
    await $fetch(`/api/v1/documents/${document.id}`, {
      method: 'DELETE',
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    
    toast.success('Документ успешно удален')
    await fetchDocuments()
  } catch (err) {
    toast.error('Ошибка при удалении документа')
  }
}

const reviewDocument = (document: DocumentItem) => {
  reviewingDocument.value = document
  showReviewModal.value = true
}

const showVersions = (document: DocumentItem) => {
  viewingVersionsFor.value = document
  showVersionsModal.value = true
}

const closeUploadModal = () => {
  showUploadModal.value = false
  uploadingNewVersionFor.value = undefined
}

const closeReviewModal = () => {
  showReviewModal.value = false
  reviewingDocument.value = undefined
}

const closeVersionsModal = () => {
  showVersionsModal.value = false
  viewingVersionsFor.value = undefined
}

const handleUploadSuccess = async () => {
  closeUploadModal()
  await fetchDocuments()
  toast.success('Документ успешно загружен')
}

const handleReviewSuccess = async () => {
  closeReviewModal()
  await fetchDocuments()
  toast.success('Документ успешно рассмотрен')
}

onMounted(async () => {
  await Promise.all([fetchDocuments(), fetchApplications(), fetchDocumentTypes()])
})
</script>
