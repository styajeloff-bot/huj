<template>
  <div
    v-if="builderStore.showPresetModal"
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-xs"
    @click.self="builderStore.showPresetModal = false"
  >
    <div class="flex max-h-[85vh] w-full max-w-xl flex-col rounded-2xl bg-white shadow-2xl overflow-hidden border border-slate-200">
      <!-- Modal Header -->
      <div class="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/70">
        <div>
          <h3 class="text-base font-semibold text-slate-900">Импорт и экспорт пресета страницы</h3>
          <p class="mt-0.5 text-xs text-slate-500">
            Перенос набранной структуры страницы в формате JSON.
          </p>
        </div>
        <button
          type="button"
          class="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
          @click="builderStore.showPresetModal = false"
        >
          <XMarkIcon class="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      <!-- Tabs Header -->
      <nav class="flex border-b border-slate-200 bg-slate-50 text-xs font-medium" aria-label="Режим пресетов">
        <button
          type="button"
          class="flex-1 py-2.5 text-center transition-colors border-b-2"
          :class="activeTab === 'export' ? 'border-blue-600 bg-white text-blue-700 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          @click="activeTab = 'export'"
        >
          Экспорт пресета (скачать JSON)
        </button>
        <button
          type="button"
          class="flex-1 py-2.5 text-center transition-colors border-b-2"
          :class="activeTab === 'import' ? 'border-blue-600 bg-white text-blue-700 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          @click="activeTab = 'import'"
        >
          Импорт пресета (загрузить JSON)
        </button>
      </nav>

      <!-- Tab Content -->
      <div class="flex-1 overflow-y-auto p-6 text-xs">
        <!-- 1. EXPORT -->
        <div v-show="activeTab === 'export'" class="space-y-4">
          <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <h4 class="font-semibold text-slate-900 mb-1">Экспорт текущего макета</h4>
            <p class="text-slate-500 leading-relaxed mb-4">
              Будет сформирован структурированный JSON-файл со всеми секциями ({{ sectionsCount }}), виджетами ({{ widgetsCount }}) и настройками страницы.
            </p>
            <button
              type="button"
              class="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-blue-500 transition-colors"
              @click="handleExport"
            >
              <ArrowDownTrayIcon class="h-4 w-4" aria-hidden="true" />
              Скачать JSON пресет
            </button>
          </div>
        </div>

        <!-- 2. IMPORT -->
        <div v-show="activeTab === 'import'" class="space-y-4">
          <div
            class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 p-8 text-center transition-colors hover:border-blue-500 bg-slate-50/50 cursor-pointer"
            @dragover.prevent
            @drop.prevent="handleFileDrop"
            @click="triggerFileInput"
          >
            <ArrowUpTrayIcon class="h-10 w-10 text-slate-400 mb-2" aria-hidden="true" />
            <p class="font-medium text-slate-800">Перетащите JSON-файл пресета сюда</p>
            <p class="text-slate-500 text-[11px] mt-1">или нажмите для выбора файла с компьютера</p>
            <input
              ref="fileInput"
              type="file"
              accept=".json,application/json"
              class="hidden"
              @change="handleFileSelect"
            >
          </div>

          <!-- Error Alert -->
          <div v-if="importError" class="rounded-lg bg-red-50 p-3 text-red-700 border border-red-200">
            {{ importError }}
          </div>

          <!-- Preview of parsed file -->
          <div v-if="parsedPreset" class="rounded-xl border border-green-200 bg-green-50/40 p-4 space-y-3">
            <div class="flex items-center gap-2 text-green-800 font-semibold">
              <CheckCircleIcon class="h-4 w-4 text-green-600" aria-hidden="true" />
              <span>Файл валиден и готов к применению</span>
            </div>
            <div class="grid grid-cols-2 gap-2 text-slate-600">
              <div>Секций в пресете: <strong class="text-slate-900">{{ parsedPreset.sections?.length || 0 }}</strong></div>
              <div>Версия схемы: <strong class="text-slate-900">{{ parsedPreset.schema_version || '1.0' }}</strong></div>
            </div>

            <div class="pt-3 border-t border-green-200 flex justify-end gap-2">
              <button
                type="button"
                class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-slate-700 hover:bg-slate-50"
                @click="parsedPreset = null"
              >
                Отмена
              </button>
              <button
                type="button"
                class="rounded-lg bg-green-600 px-4 py-1.5 font-semibold text-white hover:bg-green-500 shadow-xs"
                @click="applyImport"
              >
                Применить к черновику
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  XMarkIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  CheckCircleIcon,
} from '@heroicons/vue/24/outline'
import { useStorefrontBuilderStore } from '../store/storefrontBuilder'

const builderStore = useStorefrontBuilderStore()
const activeTab = ref<'export' | 'import'>('export')
const fileInput = ref<HTMLInputElement | null>(null)
const importError = ref<string | null>(null)
const parsedPreset = ref<any | null>(null)

const sectionsCount = computed(() => builderStore.layout?.sections?.length || 0)
const widgetsCount = computed(() => {
  let count = 0
  for (const s of builderStore.layout?.sections || []) {
    for (const c of s.columns || []) {
      count += c.widgets?.length || 0
    }
  }
  return count
})

function handleExport() {
  const exportData = {
    schema_version: '1.0',
    exported_at: new Date().toISOString(),
    page_key: builderStore.currentPage?.page_key || 'home',
    title: builderStore.currentPage?.title || 'Главная страница',
    layout: builderStore.layout,
  }

  const jsonStr = JSON.stringify(exportData, null, 2)
  const blob = new Blob([jsonStr], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `storefront-preset-${builderStore.currentPage?.page_key || 'page'}-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function triggerFileInput() {
  fileInput.value?.click()
}

function handleFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) readFile(file)
}

function handleFileDrop(e: DragEvent) {
  const file = e.dataTransfer?.files?.[0]
  if (file) readFile(file)
}

function readFile(file: File) {
  importError.value = null
  parsedPreset.value = null

  if (!file.name.endsWith('.json') && file.type !== 'application/json') {
    importError.value = 'Пожалуйста, выберите файл в формате JSON.'
    return
  }

  const reader = new FileReader()
  reader.onload = (event) => {
    try {
      const data = JSON.parse(event.target?.result as string)
      // Check if layout or sections exist
      const layoutData = data.layout || data
      if (!layoutData.sections || !Array.isArray(layoutData.sections)) {
        importError.value = 'Некорректный формат: в файле отсутствует массив sections.'
        return
      }
      parsedPreset.value = layoutData
    } catch {
      importError.value = 'Ошибка разбора JSON-файла.'
    }
  }
  reader.onerror = () => {
    importError.value = 'Не удалось прочитать файл.'
  }
  reader.readAsText(file)
}

function applyImport() {
  if (!parsedPreset.value) return
  if (confirm('Применить пресет? Текущие несохраненные изменения черновика будут заменены.')) {
    builderStore.importPreset(parsedPreset.value)
    builderStore.showPresetModal = false
  }
}
</script>
