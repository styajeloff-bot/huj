<template>
  <div v-if="authStore.isCarCraftEmployee" class="w-full">
    <div class="flex flex-wrap justify-end gap-3">
      <button type="button" class="btn-secondary min-h-11 focus-visible:ring-2 focus-visible:ring-blue-600" :disabled="disabled || exporting || importing" @click="exportSettings">
        {{ exporting ? 'Экспортируем…' : 'Экспорт JSON' }}
      </button>
      <button ref="importToggle" type="button" class="btn-secondary min-h-11 focus-visible:ring-2 focus-visible:ring-blue-600" :aria-expanded="expanded" :aria-controls="panelId" :disabled="disabled || importing" @click="togglePanel">Импорт JSON</button>
    </div>
    <p v-if="hasUnsavedChanges" class="mt-2 text-sm text-amber-800">Экспорт включает только сохранённые настройки. В форме есть несохранённые изменения.</p>
    <p v-if="exportMessage" class="mt-3 text-sm text-green-800" role="status">{{ exportMessage }}</p>
    <p v-if="exportError" class="mt-3 text-sm text-red-800" role="alert">{{ exportError }}</p>
    <section v-if="expanded" :id="panelId" class="mt-4 rounded-xl border border-gray-200 bg-gray-50 p-5" :aria-busy="previewing || importing" :aria-labelledby="`${panelId}-heading`">
      <h2 :id="`${panelId}-heading`" class="text-lg font-semibold text-gray-950">Импорт настроек витрин</h2>
      <p class="mt-2 text-sm leading-6 text-gray-600">Выберите JSON до 20 МиБ. Верхний уровень — словарь slug; «/» обозначает основной сайт. Переносятся настройки и логотипы. Склады и шрифты не переносятся.</p>
      <p class="mt-1 text-sm leading-6 text-gray-600">Существующие витрины из файла будут обновлены. Остальные сохранятся. Новые будут выключены, без складов, с системным шрифтом: перед публикацией нужно выбрать склады.</p>
      <label :for="`${panelId}-file`" class="mt-4 block text-sm font-medium text-gray-800">Файл настроек</label>
      <input :id="`${panelId}-file`" type="file" accept=".json,application/json" class="mt-2 block w-full rounded-lg border border-gray-300 bg-white p-2 text-sm focus-visible:ring-2 focus-visible:ring-blue-600" :disabled="importing || disabled" @change="selectFile">
      <p v-if="file" class="mt-2 break-all text-sm text-gray-600">Выбран: {{ file.name }} ({{ (file.size / 1024 / 1024).toFixed(2) }} МиБ)</p>
      <p v-if="errorMessage" class="mt-3 text-sm text-red-800" role="alert">{{ errorMessage }}</p>
      <p v-if="previewing || importing" class="mt-3 text-sm text-gray-700" role="status">{{ importing ? 'Применяем настройки… Не закрывайте страницу.' : 'Проверяем файл…' }}</p>
      <div v-if="preview" class="mt-4">
        <p class="mb-2 text-sm text-gray-700" role="status">Витрин в файле: {{ preview.items.length }}. Проверьте изменения перед применением.</p>
        <div class="max-h-80 overflow-auto rounded-lg border border-gray-200 bg-white">
          <table class="w-full text-left text-sm">
            <caption class="sr-only">Предпросмотр импорта настроек витрин</caption>
            <thead class="sticky top-0 bg-gray-100 text-gray-700"><tr><th scope="col" class="p-3">Витрина</th><th scope="col" class="p-3">Действие</th><th scope="col" class="p-3">Предупреждения</th></tr></thead>
            <tbody><tr v-for="item in preview.items" :key="item.slug" class="border-t border-gray-200">
              <th scope="row" class="break-all p-3 font-medium text-gray-950">{{ item.slug === '/' ? 'Основной сайт (/)' : `/${item.slug}` }}</th>
              <td class="p-3">{{ item.action === 'create' ? 'Создать выключенную' : 'Обновить' }}</td>
              <td class="p-3"><ul v-if="item.warnings.length" class="space-y-1 text-amber-800"><li v-for="(warning, index) in item.warnings" :key="index">{{ warning }}</li></ul><span v-else class="text-gray-500">Нет</span></td>
            </tr></tbody>
          </table>
        </div>
        <label class="mt-4 flex items-start gap-3 text-sm text-gray-800"><input v-model="confirmed" type="checkbox" class="mt-0.5 h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-600" :disabled="importing"><span>Подтверждаю применение перечисленных изменений.</span></label>
        <label v-if="hasUnsavedChanges" class="mt-3 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><input v-model="discardConfirmed" type="checkbox" class="mt-0.5 h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-600" :disabled="importing"><span>После успешного импорта текущие несохранённые правки, включая логотип, оформление и видимость разделов, будут сброшены. Согласен продолжить.</span></label>
      </div>
      <div class="mt-5 flex flex-wrap justify-end gap-3">
        <button type="button" class="btn-secondary min-h-11 focus-visible:ring-2 focus-visible:ring-blue-600" :disabled="importing" @click="cancel">Отмена</button>
        <button type="button" class="btn-secondary min-h-11 focus-visible:ring-2 focus-visible:ring-blue-600" :disabled="!file || previewing || importing || disabled" @click="previewFile">{{ preview ? 'Повторить предпросмотр' : 'Предпросмотр' }}</button>
        <button type="button" class="btn-primary min-h-11 focus-visible:ring-2 focus-visible:ring-blue-600" :disabled="!canImport" @click="applyImport">{{ importing ? 'Применяем…' : 'Применить импорт' }}</button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { createStorefrontsAdminApi, type StorefrontSettingsPreview, type StorefrontSettingsImportResult } from '~/features/admin/storefronts/api/storefrontsAdminApi'
import { storefrontAdminErrorMessage } from '~/features/admin/storefronts/errorMessage'

const props = defineProps<{ disabled: boolean; hasUnsavedChanges: boolean }>()
const emit = defineEmits<{ imported: [result: StorefrontSettingsImportResult]; busyChange: [busy: boolean] }>()
const authStore = useAuthStore()
const api = createStorefrontsAdminApi(useRuntimeConfig())
const panelId = `storefront-settings-import-${useId()}`
const expanded = ref(false)
const importToggle = ref<HTMLButtonElement | null>(null)
const file = shallowRef<File | null>(null)
const preview = shallowRef<StorefrontSettingsPreview | null>(null)
const previewedFile = shallowRef<File | null>(null)
const confirmed = ref(false)
const discardConfirmed = ref(false)
const previewing = ref(false)
const importing = ref(false)
const exporting = ref(false)
const errorMessage = ref('')
const exportError = ref('')
const exportMessage = ref('')
let previewVersion = 0
const canImport = computed(() => authStore.isCarCraftEmployee && !props.disabled && !importing.value && !previewing.value && !!preview.value?.preview_token && file.value === previewedFile.value && confirmed.value && (!props.hasUnsavedChanges || discardConfirmed.value))

const resetPreview = () => {
  ++previewVersion
  preview.value = null
  previewedFile.value = null
  confirmed.value = false
  discardConfirmed.value = false
  previewing.value = false
}
const cancel = () => {
  if (importing.value) return
  resetPreview()
  file.value = null
  errorMessage.value = ''
  expanded.value = false
  void nextTick(() => importToggle.value?.focus())
}
const togglePanel = () => {
  if (props.disabled || importing.value) return
  if (expanded.value) cancel()
  else expanded.value = true
}
const selectFile = (event: Event) => {
  resetPreview()
  errorMessage.value = ''
  const input = event.target as HTMLInputElement
  const selected = input.files?.[0] ?? null
  file.value = null
  if (!selected) return
  if (selected.size === 0 || selected.size > 20 * 1024 * 1024) {
    errorMessage.value = selected.size === 0 ? 'Файл пуст. Выберите JSON с настройками витрин.' : 'Размер файла превышает 20 МиБ.'
    input.value = ''
    return
  }
  file.value = selected
}
const previewFile = async () => {
  if (!authStore.isCarCraftEmployee || props.disabled || !file.value || previewing.value || importing.value) return
  resetPreview()
  const version = previewVersion
  const candidate = file.value
  previewing.value = true
  errorMessage.value = ''
  try {
    const response = await api.previewSettings(candidate)
    if (version !== previewVersion || candidate !== file.value) return
    preview.value = response
    previewedFile.value = candidate
  } catch (error) {
    if (version === previewVersion) errorMessage.value = storefrontAdminErrorMessage(error, 'Не удалось проверить файл. Повторите предпросмотр.')
  } finally {
    if (version === previewVersion) previewing.value = false
  }
}
const applyImport = async () => {
  if (!canImport.value || !previewedFile.value || !preview.value) return
  importing.value = true
  emit('busyChange', true)
  errorMessage.value = ''
  try {
    const result = await api.importSettings(previewedFile.value, preview.value.preview_token)
    resetPreview()
    file.value = null
    expanded.value = false
    emit('imported', result)
  } catch (error) {
    const response = error as { statusCode?: number; status?: number }
    resetPreview()
    errorMessage.value = (response.statusCode ?? response.status) === 409
      ? 'Файл или настройки изменились после предпросмотра. Выполните предпросмотр заново и подтвердите актуальные изменения.'
      : storefrontAdminErrorMessage(error, 'Не удалось импортировать настройки. Повторите предпросмотр перед новой попыткой.')
  } finally {
    importing.value = false
    emit('busyChange', false)
  }
}
const exportSettings = async () => {
  if (!authStore.isCarCraftEmployee || props.disabled || exporting.value || importing.value) return
  exporting.value = true
  exportError.value = ''
  exportMessage.value = ''
  try {
    const blob = await api.exportSettings()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `storefront-settings-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    exportMessage.value = 'JSON всех витрин подготовлен для скачивания.'
  } catch (error) {
    exportError.value = storefrontAdminErrorMessage(error, 'Не удалось экспортировать настройки. Повторите попытку.')
  } finally {
    exporting.value = false
  }
}
watch(() => props.hasUnsavedChanges, () => { discardConfirmed.value = false })
watch(() => authStore.isCarCraftEmployee, allowed => { if (!allowed) cancel() })
onBeforeUnmount(() => { ++previewVersion })
</script>
