<template>
  <section aria-labelledby="storefront-fonts-heading">
    <div class="grid grid-cols-[minmax(300px,0.8fr)_minmax(0,1.6fr)] items-start gap-6">
      <form class="rounded-xl border border-gray-200 bg-white p-6" :aria-busy="uploading" @submit.prevent="uploadFont">
        <h2 id="storefront-fonts-heading" class="text-lg font-semibold text-gray-950">Загрузить шрифт</h2>
        <p class="mt-1 text-sm leading-6 text-gray-600">Шрифт появится в настройках всех витрин.</p>

        <div class="mt-5 flex flex-col gap-5">
          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-gray-800">Название шрифта</span>
            <input
              ref="nameInput"
              v-model="uploadForm.name"
              type="text"
              required
              maxlength="120"
              autocomplete="off"
              class="input-field min-h-11"
              :aria-invalid="Boolean(uploadErrors.name)"
              :aria-describedby="uploadErrors.name ? 'storefront-font-name-error' : undefined"
              :disabled="uploading"
              @blur="validateUploadName"
            >
            <span v-if="uploadErrors.name" id="storefront-font-name-error" class="mt-1 flex items-center gap-1.5 text-sm text-red-700" role="alert">
              <ExclamationCircleIcon class="h-4 w-4 shrink-0" aria-hidden="true" />
              {{ uploadErrors.name }}
            </span>
          </label>

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-gray-800">Описание <span class="font-normal text-gray-500">(необязательно)</span></span>
            <textarea
              v-model="uploadForm.description"
              rows="4"
              maxlength="500"
              class="input-field resize-y leading-6"
              :disabled="uploading"
            />
            <span class="mt-1 block text-right text-sm tabular-nums text-gray-500">{{ uploadForm.description.length }}/500</span>
          </label>

          <label class="block">
            <span class="mb-1.5 block text-sm font-medium text-gray-800">Файл шрифта</span>
            <input
              ref="fileInput"
              type="file"
              accept=".woff2,.woff,.ttf,.otf,font/woff2,font/woff,font/ttf,font/otf,application/font-sfnt"
              required
              class="block min-h-11 w-full rounded-lg border border-gray-300 bg-white p-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-gray-800 hover:file:bg-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
              :aria-invalid="Boolean(uploadErrors.file)"
              :aria-describedby="`storefront-font-file-help${uploadErrors.file ? ' storefront-font-file-error' : ''}`"
              :disabled="uploading"
              @change="selectFile"
            >
            <span id="storefront-font-file-help" class="mt-1.5 block text-sm leading-5 text-gray-500">WOFF2, WOFF, TTF или OTF, от 1 байта до 5 МиБ.</span>
            <span v-if="uploadErrors.file" id="storefront-font-file-error" class="mt-1 flex items-center gap-1.5 text-sm text-red-700" role="alert">
              <ExclamationCircleIcon class="h-4 w-4 shrink-0" aria-hidden="true" />
              {{ uploadErrors.file }}
            </span>
          </label>
        </div>

        <p class="mt-5 rounded-lg bg-amber-50 px-4 py-3 text-sm leading-5 text-amber-900">
          Загружайте только шрифты, на использование которых у компании есть права.
        </p>

        <div class="mt-5 min-h-6" aria-live="polite" aria-atomic="true">
          <p v-if="uploadStatus" class="flex items-center gap-2 text-sm font-medium text-green-700">
            <CheckCircleIcon class="h-5 w-5 shrink-0" aria-hidden="true" />
            {{ uploadStatus }}
          </p>
          <p v-else-if="uploadError" class="flex items-start gap-2 text-sm text-red-700" role="alert">
            <ExclamationCircleIcon class="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            {{ uploadError }}
          </p>
        </div>

        <button type="submit" class="btn-primary mt-5 min-h-11 w-full" :disabled="uploading">
          <ArrowPathIcon v-if="uploading" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          <ArrowUpTrayIcon v-else class="h-5 w-5" aria-hidden="true" />
          {{ uploading ? 'Загружаем…' : 'Загрузить шрифт' }}
        </button>
      </form>

      <div class="min-w-0">
        <div class="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 class="text-lg font-semibold text-gray-950">Каталог шрифтов</h2>
            <p class="mt-1 text-sm leading-6 text-gray-600">Общий список для всех публичных витрин.</p>
          </div>
          <span v-if="!loading && !loadError" class="text-sm tabular-nums text-gray-500">Всего: {{ fonts.length }}</span>
        </div>

        <p v-if="catalogStatus" class="mb-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800" aria-live="polite">
          <CheckCircleIcon class="h-5 w-5 shrink-0" aria-hidden="true" />
          {{ catalogStatus }}
        </p>

        <div v-if="loading" class="flex flex-col gap-4" aria-label="Загрузка каталога шрифтов" aria-busy="true">
          <div v-for="index in 3" :key="index" class="h-44 animate-pulse rounded-xl bg-gray-100 motion-reduce:animate-none" />
        </div>

        <div v-else-if="loadError" class="rounded-xl border border-red-200 bg-red-50 p-6 text-red-800" role="alert">
          <div class="flex items-start gap-3">
            <ExclamationCircleIcon class="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <div>
              <h3 class="font-semibold">Не удалось загрузить каталог</h3>
              <p class="mt-1 text-sm leading-5">{{ loadError }}</p>
              <button type="button" class="btn-secondary mt-4 min-h-11" @click="loadFonts">Повторить</button>
            </div>
          </div>
        </div>

        <div v-else-if="sortedFonts.length === 0" class="rounded-xl border border-dashed border-gray-300 bg-white px-8 py-12 text-center">
          <DocumentTextIcon class="mx-auto h-10 w-10 text-gray-400" aria-hidden="true" />
          <h3 class="mt-4 text-base font-semibold text-gray-900">Шрифты пока не загружены</h3>
          <p class="mx-auto mt-2 max-w-md text-sm leading-6 text-gray-600">
            Добавьте первый файл, чтобы выбирать его в оформлении витрин.
          </p>
          <button type="button" class="btn-primary mt-5 min-h-11" @click="focusUploadForm">Загрузить первый шрифт</button>
        </div>

        <div v-else class="flex flex-col gap-4">
          <StorefrontFontItem
            v-for="font in sortedFonts"
            :key="`${font.id}:${itemsRevision}`"
            :font="font"
            :updating="updatingId === font.id"
            :deleting="deletingId === font.id"
            :error="operationErrors[font.id] || ''"
            @save="updateFont"
            @remove="deleteFont"
            @dirty-change="updateItemDirty"
          />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  ArrowPathIcon,
  ArrowUpTrayIcon,
  CheckCircleIcon,
  DocumentTextIcon,
  ExclamationCircleIcon,
} from '@heroicons/vue/24/outline'
import {
  createStorefrontsAdminApi,
  type AdminStorefrontFont,
  type StorefrontFontMetadataWriteRequest,
} from '~/features/admin/storefronts/api/storefrontsAdminApi'
import StorefrontFontItem from '~/features/admin/storefronts/components/StorefrontFontItem.vue'
import { storefrontAdminErrorMessage } from '~/features/admin/storefronts/errorMessage'
import type { UUID } from '~/types/ids'

const emit = defineEmits<{ dirtyChange: [isDirty: boolean] }>()

const MAX_FONT_SIZE = 5 * 1024 * 1024
const ALLOWED_FONT_EXTENSIONS = new Set(['woff2', 'woff', 'ttf', 'otf'])

const config = useRuntimeConfig()
const api = createStorefrontsAdminApi(config)
const fonts = ref<AdminStorefrontFont[]>([])
const loading = ref(true)
const uploading = ref(false)
const updatingId = ref<UUID | null>(null)
const deletingId = ref<UUID | null>(null)
const loadError = ref('')
const uploadError = ref('')
const uploadStatus = ref('')
const catalogStatus = ref('')
const operationErrors = reactive<Record<UUID, string>>({})
const dirtyItems = ref<Set<UUID>>(new Set())
const itemsRevision = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)
const nameInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const uploadForm = reactive({ name: '', description: '' })
const uploadErrors = reactive({ name: '', file: '' })

const sortedFonts = computed(() => [...fonts.value].sort((first, second) =>
  first.name.localeCompare(second.name, 'ru', { sensitivity: 'base' }),
))
const isUploadDirty = computed(() => Boolean(
  uploadForm.name || uploadForm.description || selectedFile.value,
))
const isDirty = computed(() => isUploadDirty.value || dirtyItems.value.size > 0)

const loadFonts = async () => {
  loading.value = true
  loadError.value = ''
  try {
    fonts.value = (await api.listFonts()).items
  } catch (error) {
    loadError.value = storefrontAdminErrorMessage(error, 'Не удалось загрузить список шрифтов')
  } finally {
    loading.value = false
  }
}

const validateUploadName = (): boolean => {
  uploadErrors.name = uploadForm.name.trim() ? '' : 'Укажите название шрифта'
  return !uploadErrors.name
}

const validateSelectedFile = (): boolean => {
  const file = selectedFile.value
  if (!file) {
    uploadErrors.file = 'Выберите файл шрифта'
    return false
  }
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_FONT_EXTENSIONS.has(extension)) {
    uploadErrors.file = 'Поддерживаются только WOFF2, WOFF, TTF и OTF'
    return false
  }
  if (file.size < 1 || file.size > MAX_FONT_SIZE) {
    uploadErrors.file = 'Размер файла должен быть от 1 байта до 5 МиБ'
    return false
  }
  uploadErrors.file = ''
  return true
}

const selectFile = (event: Event) => {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
  validateSelectedFile()
  uploadError.value = ''
  uploadStatus.value = ''
}

const resetUploadForm = () => {
  uploadForm.name = ''
  uploadForm.description = ''
  selectedFile.value = null
  uploadErrors.name = ''
  uploadErrors.file = ''
  if (fileInput.value) fileInput.value.value = ''
}

const uploadFont = async () => {
  uploadError.value = ''
  uploadStatus.value = ''
  if (!validateUploadName() || !validateSelectedFile() || !selectedFile.value) return
  uploading.value = true
  try {
    const created = await api.uploadFont(selectedFile.value, {
      name: uploadForm.name.trim(),
      description: uploadForm.description.trim() || null,
    })
    fonts.value = [...fonts.value, created]
    resetUploadForm()
    uploadStatus.value = `Шрифт «${created.name}» загружен`
  } catch (error) {
    uploadError.value = storefrontAdminErrorMessage(error, 'Не удалось загрузить шрифт')
  } finally {
    uploading.value = false
  }
}

const updateFont = async (fontId: UUID, body: StorefrontFontMetadataWriteRequest) => {
  updatingId.value = fontId
  operationErrors[fontId] = ''
  try {
    const saved = await api.updateFont(fontId, body)
    const index = fonts.value.findIndex(font => font.id === saved.id)
    if (index >= 0) fonts.value[index] = saved
    dirtyItems.value = new Set([...dirtyItems.value].filter(id => id !== fontId))
    catalogStatus.value = `Шрифт «${saved.name}» обновлён`
  } catch (error) {
    operationErrors[fontId] = storefrontAdminErrorMessage(error, 'Не удалось обновить шрифт')
  } finally {
    updatingId.value = null
  }
}

const deleteFont = async (fontId: UUID) => {
  deletingId.value = fontId
  operationErrors[fontId] = ''
  const removed = fonts.value.find(font => font.id === fontId)
  try {
    await api.removeFont(fontId)
    fonts.value = fonts.value.filter(font => font.id !== fontId)
    dirtyItems.value = new Set([...dirtyItems.value].filter(id => id !== fontId))
    catalogStatus.value = removed ? `Шрифт «${removed.name}» удалён` : 'Шрифт удалён'
  } catch (error) {
    operationErrors[fontId] = storefrontAdminErrorMessage(error, 'Не удалось удалить шрифт. Повторите попытку.')
  } finally {
    deletingId.value = null
  }
}

const updateItemDirty = (fontId: UUID, value: boolean) => {
  const next = new Set(dirtyItems.value)
  if (value) next.add(fontId)
  else next.delete(fontId)
  dirtyItems.value = next
}

const focusUploadForm = () => nameInput.value?.focus()
const discardChanges = () => {
  resetUploadForm()
  dirtyItems.value = new Set()
  itemsRevision.value += 1
}

watch(isDirty, (value) => {
  emit('dirtyChange', value)
  if (value) uploadStatus.value = ''
}, { immediate: true })
onMounted(loadFonts)
defineExpose({ discardChanges })
</script>
