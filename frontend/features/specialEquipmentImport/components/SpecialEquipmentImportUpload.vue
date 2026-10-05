<template>
  <section class="rounded-xl border border-gray-200 bg-white p-5 sm:p-6" aria-labelledby="upload-title">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 id="upload-title" class="text-xl font-bold text-gray-950">1. Файл и режим</h2>
        <p class="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600">Русский XLSX управляет марками, моделями, модификациями, категориями, характеристиками и объявлениями. Изображения загружаются отдельно в карточке объявления.</p>
      </div>
      <a :href="templateDownloadUrl" class="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-blue-700 px-4 text-sm font-bold text-blue-800 hover:bg-blue-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" download>
        <ArrowDownTrayIcon class="h-5 w-5" aria-hidden="true" />Скачать шаблон
      </a>
    </div>

    <template v-if="!job">
      <fieldset class="mt-6">
        <legend class="text-sm font-bold text-gray-900">Режим изменений</legend>
        <div class="mt-3 grid gap-3 lg:grid-cols-3">
          <label v-for="item in modes" :key="item.value" class="flex cursor-pointer items-start gap-3 rounded-lg border p-4 focus-within:ring-2 focus-within:ring-blue-600" :class="mode === item.value ? 'border-blue-700 bg-blue-50' : 'border-gray-300'">
            <input v-model="mode" type="radio" name="import-mode" :value="item.value" class="mt-1 h-4 w-4 accent-blue-700">
            <span><span class="block text-sm font-bold text-gray-950">{{ item.label }}</span><span class="mt-1 block text-sm leading-relaxed text-gray-600">{{ item.description }}</span></span>
          </label>
        </div>
      </fieldset>

      <p class="mt-5 rounded-lg bg-blue-50 p-4 text-sm leading-relaxed text-blue-950">
        <span class="font-bold">{{ modePolicyLabel }}</span>
        Политика ошибок определяется режимом автоматически и не требует отдельной настройки.
      </p>
      <label class="mt-5 flex items-start gap-3 rounded-lg border border-gray-200 p-4">
        <input v-model="inStock" type="checkbox" class="mt-1 h-4 w-4 accent-blue-700">
        <span><span class="block text-sm font-bold text-gray-950">В наличии</span><span class="mt-1 block text-sm text-gray-600">Назначьте активный склад для импортируемой техники.</span></span>
      </label>
      <label v-if="inStock" class="mt-4 block text-sm font-semibold text-gray-800">
        Склад <span aria-hidden="true">*</span>
        <select v-model="targetWarehouseId" class="mt-1 min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm" :disabled="warehousesLoading || Boolean(warehousesError)" required>
          <option value="">{{ warehousesLoading ? 'Загрузка складов…' : 'Выберите склад' }}</option>
          <option v-for="warehouse in warehouses" :key="warehouse.id" :value="warehouse.id">{{ warehouse.address }}{{ warehouse.city_name ? `, ${warehouse.city_name}` : '' }}</option>
        </select>
        <span v-if="warehousesError" class="mt-2 block rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">{{ warehousesError }} Сначала загрузите список активных складов. <button type="button" class="font-bold underline" @click="emit('retry-warehouses')">Повторить</button></span>
      </label>
    </template>

    <div v-if="requiresFileReselection" class="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4" role="status">
      <p class="font-bold text-amber-950">Найдена незавершённая загрузка</p>
      <p class="mt-1 text-sm leading-relaxed text-amber-900">Выберите исходный файл «{{ recovery?.filename }}» повторно. Уже принятые части не будут отправлены заново.</p>
    </div>

    <div
      v-if="!job || job.status === 'awaiting_upload'"
      class="mt-6 rounded-xl border-2 border-dashed p-6 text-center transition-colors duration-200 motion-reduce:transition-none"
      :class="dragging ? 'border-blue-700 bg-blue-50' : 'border-gray-300 bg-gray-50'"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="handleDrop"
    >
      <DocumentArrowUpIcon class="mx-auto h-10 w-10 text-gray-500" aria-hidden="true" />
      <p class="mt-3 font-bold text-gray-950">Перетащите один XLSX сюда</p>
      <p class="mt-1 text-sm text-gray-600">или выберите файл до 2 ГБ</p>
      <label class="mt-4 inline-flex min-h-11 cursor-pointer items-center rounded-lg border border-gray-300 bg-white px-4 text-sm font-bold text-gray-800 hover:bg-gray-50 focus-within:ring-2 focus-within:ring-blue-600">
        Выбрать файл
        <input ref="fileInput" type="file" class="sr-only" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" @change="handleFileInput">
      </label>
    </div>

    <div v-if="file" class="mt-5 flex flex-col gap-4 rounded-lg border border-gray-200 bg-gray-50 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <p class="truncate font-bold text-gray-950">{{ file.name }}</p>
        <p class="mt-1 text-sm text-gray-600">{{ formatBytes(file.size) }} · изменён {{ formatDate(file.lastModified) }}</p>
      </div>
      <button v-if="!job" type="button" class="min-h-11 rounded-lg border border-gray-300 bg-white px-4 text-sm font-semibold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" @click="emit('file', null)">Выбрать другой</button>
    </div>

    <div v-if="job?.status === 'awaiting_upload'" class="mt-6" aria-live="polite">
      <div class="flex items-end justify-between gap-4 text-sm"><span class="font-semibold text-gray-800">Загрузка файла</span><span class="font-bold tabular-nums text-gray-950">{{ progressPercent }}%</span></div>
      <div class="mt-2 h-3 overflow-hidden rounded-full bg-gray-200" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100"><div class="h-full rounded-full bg-blue-700 transition-transform duration-200 motion-reduce:transition-none" :style="{ transform: `scaleX(${progressPercent / 100})`, transformOrigin: 'left' }" /></div>
      <div class="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-gray-600">
        <span>{{ formatBytes(uploadedBytes) }} / {{ formatBytes(job.source?.bytesTotal ?? file?.size ?? 0) }}</span>
        <span v-if="uploadSpeedBytes > 0">{{ formatBytes(uploadSpeedBytes) }}/с</span>
        <span v-if="etaSeconds !== null">Осталось примерно {{ formatDuration(etaSeconds) }}</span>
      </div>
    </div>

    <div v-if="uploadError" class="mt-5 rounded-lg border border-red-200 bg-red-50 p-4" role="alert"><p class="flex items-center gap-2 font-bold text-red-800"><ExclamationCircleIcon class="h-5 w-5" aria-hidden="true" />Загрузка не завершена</p><p class="mt-1 text-sm leading-relaxed text-red-800">{{ uploadError }}</p></div>

    <div class="mt-6 flex flex-col gap-3 sm:flex-row">
      <button v-if="!job" type="button" class="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-blue-700 px-5 text-base font-bold text-white hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50" :disabled="!file || (inStock && (!targetWarehouseId || warehousesLoading || Boolean(warehousesError)))" @click="start"><ArrowUpTrayIcon class="h-5 w-5" aria-hidden="true" />Создать и загрузить</button>
      <button v-else-if="uploading" type="button" class="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-gray-300 px-5 text-sm font-bold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" @click="emit('pause')"><PauseIcon class="h-5 w-5" aria-hidden="true" />Пауза</button>
      <button v-else-if="job.status === 'awaiting_upload' && file" type="button" class="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-blue-700 px-5 text-sm font-bold text-white hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2" @click="emit('resume')"><ArrowPathIcon class="h-5 w-5" aria-hidden="true" />{{ paused ? 'Продолжить' : 'Повторить загрузку' }}</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ArrowUpTrayIcon,
  DocumentArrowUpIcon,
  ExclamationCircleIcon,
  PauseIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type { SpecialEquipmentImportJob, SpecialEquipmentImportMode, SpecialEquipmentImportWarehouse } from '../types'

const props = defineProps<{
  templateUrl: string
  job: SpecialEquipmentImportJob | null
  file: File | null
  recovery: { filename: string; size: number; lastModified: number } | null
  requiresFileReselection: boolean
  uploading: boolean
  paused: boolean
  uploadError: string
  uploadedBytes: number
  uploadSpeedBytes: number
  progressPercent: number
  etaSeconds: number | null
  warehouses: SpecialEquipmentImportWarehouse[]
  warehousesLoading: boolean
  warehousesError: string
}>()

const emit = defineEmits<{
  file: [file: File | null]
  recoveryFile: [file: File]
  start: [request: { mode: SpecialEquipmentImportMode; templateVersion: 9; target_warehouse_id?: UUID }]
  'retry-warehouses': []
  pause: []
  resume: []
}>()

const mode = ref<SpecialEquipmentImportMode>('PATCH')
const inStock = ref(false)
const targetWarehouseId = ref<UUID | ''>('')
const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const templateDownloadUrl = computed(() => props.templateUrl)
const modePolicyLabel = computed(() => mode.value === 'FULL_SNAPSHOT'
  ? 'Полная замена применяется целиком: при любой ошибке данные не изменятся.'
  : 'Корректные независимые записи будут применены, конфликтные попадут в отчёт.')

const modes: Array<{ value: SpecialEquipmentImportMode; label: string; description: string }> = [
  { value: 'PATCH', label: 'Добавление и изменение', description: 'Добавляет новые и меняет существующие записи. Конфликтные независимые записи пропускаются.' },
  { value: 'APPEND', label: 'Только добавление', description: 'Добавляет только новые записи. Уже существующие коды попадут в отчёт.' },
  { value: 'FULL_SNAPSHOT', label: 'Полная замена', description: 'Полностью заменяет каталог. Любая ошибка отменяет все изменения.' },
]

const acceptFile = (file: File | null) => {
  if (!file) return
  if (props.requiresFileReselection) emit('recoveryFile', file)
  else emit('file', file)
}
const handleDrop = (event: DragEvent) => { dragging.value = false; acceptFile(event.dataTransfer?.files.item(0) ?? null) }
const handleFileInput = (event: Event) => { acceptFile((event.target as HTMLInputElement).files?.item(0) ?? null) }
const start = () => emit('start', {
  mode: mode.value,
  templateVersion: 9,
  ...(inStock.value && targetWarehouseId.value ? { target_warehouse_id: targetWarehouseId.value } : {}),
})

const formatBytes = (value: number) => {
  if (value < 1024) return `${value} Б`
  const units = ['КБ', 'МБ', 'ГБ']
  let amount = value / 1024
  let index = 0
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1 }
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[index]}`
}
const formatDuration = (seconds: number) => seconds < 60 ? `${seconds} сек.` : `${Math.ceil(seconds / 60)} мин.`
const formatDate = (timestamp: number) => new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(timestamp))
</script>
