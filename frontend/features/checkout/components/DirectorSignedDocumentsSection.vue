<template>
  <div data-storefront-block="client.checkout" class="space-y-4">
    <!-- Tax system selector -->
    <div class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
      <div class="flex items-center gap-2 mb-2">
        <p class="text-sm font-medium text-[color:var(--storefront-text,#374151)]">
          Система налогообложения
        </p>
        <span
          v-if="props.taxSystemAuto"
          class="inline-flex items-center gap-1 text-xs text-[color:var(--storefront-text,#1d4ed8)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)] rounded-md px-2 py-0.5"
        >
          <svg class="text-[color:var(--storefront-icon,inherit)] w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Определено по данным ФНС
        </span>
      </div>
      <div class="space-y-2">
        <label
          v-for="opt in taxOptions"
          :key="opt.value"
          class="flex items-start gap-2 p-2.5 rounded-md border cursor-pointer transition-colors"
          :class="taxSystem === opt.value
            ? 'border-[color:var(--storefront-border,#3b82f6)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]'
            : 'border-[color:var(--storefront-border,#e5e7eb)] hover:border-[color:var(--storefront-border,#d1d5db)]'"
        >
          <input
            type="radio"
            name="tax-system"
            :checked="taxSystem === opt.value"
            class="storefront-control mt-0.5"
            @change="setTaxSystem(opt.value)"
          >
          <div class="flex-1">
            <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">{{ opt.label }}</div>
            <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ opt.description }}</div>
          </div>
        </label>
      </div>
    </div>

    <!-- Helper panel -->
    <div
      v-if="!isBankStatementMode"
      class="rounded-lg border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4"
    >
      <div class="flex items-start gap-3">
        <svg class="w-5 h-5 text-[color:var(--storefront-icon,#2563eb)] mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div>
          <p class="text-sm font-medium text-[color:var(--storefront-text,#1e3a8a)] mb-1">Что загружать?</p>
          <p class="text-xs text-[color:var(--storefront-text,#1e40af)] leading-relaxed">
            Загрузите <strong>один XML-файл</strong> — экспорт бухгалтерской отчётности из 1С Бухгалтерия.
            Мы извлечём из него автоматически:
          </p>
          <ul class="text-xs text-[color:var(--storefront-text,#1e40af)] mt-1 space-y-0.5 list-disc list-inside">
            <li>Бухгалтерский баланс (форма №1)</li>
            <li>Отчёт о финансовых результатах (форма №2)</li>
            <li>Отчёт об изменениях капитала (форма №3)</li>
            <li>Отчёт о движении денежных средств (форма №4)</li>
          </ul>
          <p class="text-xs text-[color:var(--storefront-text,#1d4ed8)] mt-2">
            Файл должен быть в формате XML, кодировка windows-1251.
          </p>
        </div>
      </div>
    </div>

    <!-- Upload -->
    <div class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4">
      <p class="text-sm font-medium text-[color:var(--storefront-text,#374151)] mb-2">
        {{ uploadTitle }}
      </p>
      <p v-if="isBankStatementMode" class="mb-3 text-xs text-[color:var(--storefront-text-muted,#4b5563)] leading-relaxed">
        Загрузите одним или несколькими файлами .txt выписки банка за последние 2 года
      </p>
      
      <div v-if="uploadState === 'idle' || uploadState === 'error'">
        <input
          ref="fileInput"
          type="file"
          :accept="inputAccept"
          :multiple="isBankStatementMode"
          class="storefront-control hidden"
          @change="handleFileChange"
        >
        <button
          type="button"
          class="storefront-action-ghost w-full flex items-center justify-center gap-2 px-4 py-3 rounded-md border-2 border-dashed transition-colors"
          :class="canUploadFiles
            ? 'border-[color:var(--storefront-primary-border,#d1d5db)] hover:border-[color:var(--storefront-primary-hover-border,#60a5fa)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]'
            : 'border-[color:var(--storefront-primary-border,#e5e7eb)] bg-[color:rgb(var(--storefront-primary-rgb,249_250_251)/var(--tw-bg-opacity,1))] cursor-not-allowed opacity-70'"
          :disabled="!canUploadFiles"
          @click="openFilePicker"
        >
          <svg class="w-5 h-5 text-[color:var(--storefront-primary-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <span class="text-sm text-[color:var(--storefront-primary-foreground,#4b5563)]">{{ buttonText }}</span>
        </button>
        <p v-if="uploadError" class="mt-2 text-xs text-[color:var(--storefront-error-text,#dc2626)]">{{ uploadError }}</p>
      </div>

      <div v-else-if="uploadState === 'uploading'" class="flex items-center gap-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
        <svg class="text-[color:var(--storefront-icon,inherit)] w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        Загрузка...
      </div>

      <div v-else-if="uploadState === 'success'" class="space-y-2">
        <div class="flex items-center gap-2 text-sm text-[color:var(--storefront-success-text,#15803d)]">
          <svg class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
          {{ successTitle }}
        </div>
        <div v-if="isBankStatementMode" class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] space-y-0.5">
          <p>Распознано транзакций: {{ bankUploadResult?.total_recognized_transactions_count ?? 0 }}</p>
          <p>Всего транзакций: {{ bankUploadResult?.total_transactions_count ?? 0 }}</p>
          <p v-if="bankUploadResult?.items?.length">Файлов: {{ bankUploadResult.items.length }}</p>
        </div>
        <div v-else class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] space-y-0.5">
          <p>ИНН: {{ uploadResult?.inn }}</p>
          <p>Период: {{ uploadResult?.period_name }}</p>
          <p>Форм: {{ uploadResult?.forms?.length || 0 }}</p>
          <p>Строк: {{ uploadResult?.total_rows || 0 }}</p>
          <p v-if="uploadResult?.document_id">Документ сохранён</p>
        </div>
        <button
          type="button"
          class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] underline"
          @click="resetUpload"
        >
          Загрузить другой файл
        </button>
      </div>
    </div>

    <p v-if="isBankStatementMode && !applicationId" class="text-xs text-[color:var(--storefront-warning-text,#b45309)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fde68a)] rounded-md p-3">
      Загрузка станет доступна после сохранения предыдущих шагов заявки.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useBankStatementUpload, type BankStatementUploadResponse } from '../composables/useBankStatementUpload'
import type { UUID } from '~/types/ids'

interface Props {
  applicationId: UUID | null
  companyInn?: string | null
  initialTaxSystem?: string | null
  taxSystemAuto?: boolean
}
const props = defineProps<Props>()

const config = useRuntimeConfig()

const emit = defineEmits<{
  (e: 'tax-system-change', value: string): void
  (e: 'completion-change', completed: boolean): void
}>()

type TaxSystem = 'osn' | 'usn' | 'patent' | 'ausn'

interface TaxOption {
  value: TaxSystem
  label: string
  description: string
}

const TAX_OPTIONS: TaxOption[] = [
  { value: 'osn', label: 'ОСН', description: 'Общая система налогообложения' },
  { value: 'usn', label: 'УСН', description: 'Упрощённая система налогообложения' },
  { value: 'patent', label: 'Патент', description: 'Патентная система налогообложения' },
  { value: 'ausn', label: 'АвтоУСН', description: 'Автоматизированная упрощённая система налогообложения' },
]

const IP_TAX_OPTIONS: TaxOption[] = [
  { value: 'osn', label: 'ОСН', description: 'Общая система налогообложения' },
  { value: 'usn', label: 'УСН', description: 'Упрощённая система налогообложения' },
  { value: 'ausn', label: 'АвтоУСН', description: 'Автоматизированная упрощённая система налогообложения' },
]

const taxSystem = ref<TaxSystem>(_normalizeTaxSystem(props.initialTaxSystem) ?? 'osn')
const { uploadBankStatements } = useBankStatementUpload()

const normalizedInn = computed(() => String(props.companyInn || '').replace(/\D/g, ''))
const isIndividualEntrepreneur = computed(() => normalizedInn.value.length === 12)
const taxOptions = computed(() => isIndividualEntrepreneur.value ? IP_TAX_OPTIONS : TAX_OPTIONS)
const isBankStatementMode = computed(() => taxSystem.value === 'usn' || taxSystem.value === 'ausn')
const uploadTitle = computed(() => isBankStatementMode.value ? 'Выписки банка' : 'Бухгалтерская отчётность (XML)')
const inputAccept = computed(() => isBankStatementMode.value ? '.txt,text/plain' : '.xml')
const buttonText = computed(() => isBankStatementMode.value ? 'Выбрать файл' : 'Выбрать XML-файл')
const successTitle = computed(() => isBankStatementMode.value ? 'Файл успешно загружен' : 'Загружено успешно')
const canUploadFiles = computed(() => !isBankStatementMode.value || Boolean(props.applicationId))

watch(
  () => props.initialTaxSystem,
  (incoming) => {
    const normalised = _normalizeTaxSystem(incoming)
    if (normalised && normalised !== taxSystem.value) taxSystem.value = normalised
  },
)

watch(taxOptions, (options) => {
  if (!options.some((option) => option.value === taxSystem.value)) {
    taxSystem.value = options[0]?.value ?? 'osn'
  }
}, { immediate: true })

watch(taxSystem, (value) => {
  emit('tax-system-change', value)
}, { immediate: true })

watch(isBankStatementMode, () => {
  resetUpload()
})

const setTaxSystem = (value: TaxSystem) => {
  taxSystem.value = value
}

const openFilePicker = () => {
  if (!canUploadFiles.value) {
    showMissingApplicationError()
    return
  }
  fileInput.value?.click()
}

function _normalizeTaxSystem(value: string | null | undefined): TaxSystem | null {
  if (!value) return null
  const lower = String(value).toLowerCase()
  if (lower.includes('автоусн') || lower.includes('аусн') || lower.includes('ausn')) return 'ausn'
  if (lower.includes('осн для ип') || lower.includes('osn_ip')) return 'osn'
  if (lower.includes('усн') || lower.includes('usn')) return 'usn'
  if (lower.includes('осн') || lower.includes('osn') || lower.includes('общ')) return 'osn'
  if (lower.includes('патент') || lower.includes('patent')) return 'patent'
  return null
}

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------

type UploadState = 'idle' | 'uploading' | 'success' | 'error'

const uploadState = ref<UploadState>('idle')
const uploadError = ref<string | null>(null)
const uploadResult = ref<Record<string, any> | null>(null)
const bankUploadResult = ref<BankStatementUploadResponse | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const companyDocsUploadCompleted = computed(() => uploadState.value === 'success')

watch(companyDocsUploadCompleted, (completed) => {
  emit('completion-change', completed)
}, { immediate: true })

const handleFileChange = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  if (files.length === 0) return

  if (!canUploadFiles.value) {
    showMissingApplicationError()
    if (fileInput.value) fileInput.value.value = ''
    return
  }

  if (isBankStatementMode.value) {
    await uploadBankStatementFiles(files)
  } else {
    await uploadAccountingXmlFile(files[0])
  }
}

const uploadBankStatementFiles = async (files: File[]) => {
  if (!canUploadFiles.value) {
    showMissingApplicationError()
    if (fileInput.value) fileInput.value.value = ''
    return
  }

  const hasWrongExtension = files.some((file) => !file.name.toLowerCase().endsWith('.txt'))
  if (hasWrongExtension) {
    uploadState.value = 'error'
    uploadError.value = 'Неверный формат. Загрузите файл в формате .txt'
    uploadResult.value = null
    bankUploadResult.value = null
    if (fileInput.value) fileInput.value.value = ''
    return
  }

  uploadState.value = 'uploading'
  uploadError.value = null
  uploadResult.value = null
  bankUploadResult.value = null

  try {
    const result = await uploadBankStatements(files, props.applicationId)
    bankUploadResult.value = result
    uploadState.value = 'success'
  } catch (err: any) {
    uploadState.value = 'error'
    const detail = extractUploadErrorMessage(err, 'Не удалось загрузить файл')
    uploadError.value = detail
  }
}

const uploadAccountingXmlFile = async (file: File | undefined) => {
  if (!file) return
  uploadState.value = 'uploading'
  uploadError.value = null
  bankUploadResult.value = null

  const formData = new FormData()
  formData.append('file', file)
  if (props.applicationId) {
    formData.append('application_id', props.applicationId)
  }

  try {
    const result = await $fetch('/api/v1/accounting/upload-xml', {
      method: 'POST',
      baseURL: config.public.apiBase,
      body: formData,
      credentials: 'include',
    })
    uploadResult.value = result as Record<string, any>
    uploadState.value = 'success'
  } catch (err: any) {
    uploadState.value = 'error'
    const detail = extractUploadErrorMessage(err, 'Не удалось загрузить файл')
    uploadError.value = detail
  }
}

const resetUpload = () => {
  uploadState.value = 'idle'
  uploadError.value = null
  uploadResult.value = null
  bankUploadResult.value = null
  if (fileInput.value) fileInput.value.value = ''
}

const showMissingApplicationError = () => {
  uploadState.value = 'error'
  uploadError.value = 'Загрузка станет доступна после сохранения предыдущих шагов заявки.'
  uploadResult.value = null
  bankUploadResult.value = null
}

const extractUploadErrorMessage = (err: any, fallback: string): string => {
  const detail = err?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail.message === 'string') return detail.message
  if (typeof err?.message === 'string' && err.message.trim()) return err.message
  return fallback
}
</script>
