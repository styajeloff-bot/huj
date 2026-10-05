<template>
  <div id="main-content" class="mx-auto max-w-[1600px]" tabindex="-1">
    <header class="flex flex-col gap-4 border-b border-gray-200 pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p class="text-sm font-bold text-blue-800">Каталог транспортных средств и специальной техники</p>
        <h1 class="mt-2 text-3xl font-bold tracking-tight text-gray-950 sm:text-4xl">Импорт из Excel</h1>
        <p class="mt-3 max-w-3xl text-base leading-relaxed text-gray-600">Загрузите заполненный шаблон, проверьте найденные изменения и примените их к каталогу спецтехники.</p>
      </div>
      <div class="flex flex-col gap-2 sm:flex-row">
        <button type="button" class="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 text-sm font-bold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" @click="historyOpen = !historyOpen"><ClockIcon class="h-5 w-5" aria-hidden="true" />История</button>
        <button v-if="flow.job.value" type="button" class="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-blue-700 px-4 text-sm font-bold text-white hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2" @click="flow.startNewImport"><PlusIcon class="h-5 w-5" aria-hidden="true" />Новый импорт</button>
      </div>
    </header>

    <div v-if="historyOpen" class="mt-6 rounded-xl border border-gray-200 bg-white p-5 sm:p-6">
      <div class="flex items-center justify-between gap-3"><div><h2 class="text-xl font-bold text-gray-950">История импортов</h2><p class="mt-1 text-sm text-gray-600">Незавершённый импорт можно открыть после перезагрузки страницы.</p></div><button type="button" class="min-h-10 rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" :disabled="historyLoading" @click="loadHistory">{{ historyLoading ? 'Обновляем…' : 'Обновить' }}</button></div>
      <div v-if="historyLoading && history.length === 0" class="mt-4 h-32 animate-pulse rounded-lg bg-gray-200 motion-reduce:animate-none" />
      <div v-else-if="historyError" class="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{{ historyError }}</div>
      <div v-else-if="history.length === 0" class="mt-4 rounded-lg bg-gray-50 p-5 text-sm leading-relaxed text-gray-600">Импортов пока нет. Загрузите первый файл ниже.</div>
      <div v-else class="mt-4 overflow-x-auto rounded-lg border border-gray-200">
        <table class="min-w-full text-sm"><thead class="sticky top-0 bg-gray-50 text-left text-gray-600"><tr><th class="px-3 py-3 font-semibold">Файл</th><th class="px-3 py-3 font-semibold">Режим</th><th class="px-3 py-3 font-semibold">Статус</th><th class="px-3 py-3 font-semibold">Создан</th><th class="px-3 py-3"><span class="sr-only">Действие</span></th></tr></thead><tbody class="divide-y divide-gray-100"><tr v-for="item in history" :key="item.id" :class="flow.job.value?.id === item.id ? 'bg-blue-50' : ''"><td class="max-w-80 truncate px-3 py-3 font-semibold text-gray-900">{{ item.filename }}</td><td class="whitespace-nowrap px-3 py-3 text-gray-700">{{ modeLabel(item.mode) }}</td><td class="whitespace-nowrap px-3 py-3"><span class="inline-flex rounded-full px-2.5 py-1 text-xs font-bold" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span></td><td class="whitespace-nowrap px-3 py-3 text-gray-600">{{ formatDateTime(item.createdAt) }}</td><td class="px-3 py-3 text-right"><button type="button" class="min-h-10 rounded-lg px-3 text-sm font-bold text-blue-800 hover:bg-blue-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" @click="openHistoryJob(item.id)">Открыть</button></td></tr></tbody></table>
      </div>
    </div>

    <div class="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div class="flex min-w-0 flex-col gap-6">
        <SpecialEquipmentImportUpload
          v-if="!flow.job.value || flow.job.value.status === 'awaiting_upload'"
          :template-url="flow.api.templateContentUrl"
          :job="flow.job.value"
          :file="flow.selectedFile.value"
          :recovery="flow.recovery.value"
          :requires-file-reselection="flow.requiresFileReselection.value"
          :uploading="flow.uploading.value"
          :paused="flow.paused.value"
          :upload-error="flow.uploadError.value"
          :uploaded-bytes="flow.uploadedBytes.value"
          :upload-speed-bytes="flow.uploadSpeedBytes.value"
          :progress-percent="flow.progressPercent.value"
          :eta-seconds="flow.etaSeconds.value"
          :warehouses="warehouses"
          :warehouses-loading="warehousesLoading"
          :warehouses-error="warehousesError"
          @file="flow.selectFile"
          @recovery-file="flow.attachRecoveryFile"
          @start="flow.createAndUpload"
          @pause="flow.pauseUpload"
          @resume="flow.resumeUpload"
          @retry-warehouses="loadWarehouses"
        />

        <section v-if="flow.job.value && flow.job.value.status !== 'awaiting_upload'" class="rounded-xl border border-gray-200 bg-white p-5 sm:p-6" aria-labelledby="processing-title">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div><h2 id="processing-title" class="text-xl font-bold text-gray-950">2. Проверка и обработка</h2><p class="mt-2 text-sm leading-relaxed text-gray-600">Файл загружен. Система проверяет структуру, данные и связи между объектами каталога.</p></div>
            <span class="inline-flex w-fit rounded-full px-3 py-1.5 text-sm font-bold" :class="statusClass(flow.job.value.status)">{{ statusLabel(flow.job.value.status) }}</span>
          </div>

          <ol class="mt-6 grid gap-3 sm:grid-cols-3" aria-label="Этапы обработки">
            <li v-for="phase in phases" :key="phase.key" class="rounded-lg border p-4" :class="phaseState(phase.key).className"><div class="flex items-center gap-2"><CheckCircleIcon v-if="phaseState(phase.key).state === 'done'" class="h-5 w-5 text-emerald-700" aria-hidden="true" /><ArrowPathIcon v-else-if="phaseState(phase.key).state === 'active'" class="h-5 w-5 animate-spin text-blue-700 motion-reduce:animate-none" aria-hidden="true" /><span v-else class="h-5 w-5 rounded-full border-2 border-gray-300" aria-hidden="true" /><span class="text-sm font-bold text-gray-900">{{ phase.label }}</span></div><p class="mt-2 text-sm leading-relaxed text-gray-600">{{ phase.description }}</p></li>
          </ol>

          <div class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div v-for="counter in visibleCounters" :key="counter.unit" class="rounded-lg bg-gray-50 p-4"><p class="text-sm font-semibold text-gray-600">{{ counterLabel(counter.unit) }}</p><p class="mt-2 text-xl font-bold tabular-nums text-gray-950">{{ formatCount(counter.done) }}<template v-if="counter.total !== null"> / {{ formatCount(counter.total) }}</template></p><div v-if="counter.total !== null && counter.total > 0" class="mt-3 h-2 overflow-hidden rounded-full bg-gray-200"><div class="h-full rounded-full bg-blue-700" :style="{ width: `${Math.min(100, (counter.done / counter.total) * 100)}%` }" /></div><p v-else class="mt-2 text-xs text-gray-500">Общий объём пока определяется</p></div>
          </div>

          <div v-if="localizedError" class="mt-5 rounded-xl border border-red-200 bg-red-50 p-5" role="alert">
            <div class="flex items-start gap-3.5">
              <ExclamationCircleIcon class="mt-0.5 h-6 w-6 shrink-0 text-red-700" aria-hidden="true" />
              <div class="flex-1 min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="text-base font-bold text-red-950">{{ localizedError.title }}</h3>
                  <span
                    v-if="localizedError.code"
                    class="inline-flex items-center rounded border border-red-200 bg-red-100 px-2 py-0.5 font-mono text-xs font-semibold text-red-800"
                  >
                    {{ localizedError.code }}
                  </span>
                </div>
                <p class="mt-1.5 text-sm leading-relaxed text-red-900">{{ localizedError.description }}</p>

                <div
                  v-if="localizedError.hint"
                  class="mt-3 rounded-lg border border-red-100 bg-white/80 p-3.5 text-sm text-red-900 shadow-sm"
                >
                  <div class="flex items-start gap-2">
                    <InformationCircleIcon class="mt-0.5 h-4 w-4 shrink-0 text-blue-700" aria-hidden="true" />
                    <div class="leading-relaxed">
                      <span class="font-bold text-gray-900">Рекомендация: </span>
                      <span>{{ localizedError.hint }}</span>
                    </div>
                  </div>
                </div>

                <div class="mt-4 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    class="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-red-700 px-4 text-sm font-bold text-white hover:bg-red-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600"
                    @click="flow.startNewImport"
                  >
                    <ArrowPathIcon class="h-4 w-4" aria-hidden="true" />
                    Выбрать другой файл
                  </button>
                  <a
                    v-if="flow.api.templateContentUrl"
                    :href="flow.api.templateContentUrl"
                    class="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-red-300 bg-white px-4 text-sm font-semibold text-red-900 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600"
                    download
                  >
                    <ArrowDownTrayIcon class="h-4 w-4" aria-hidden="true" />
                    Скачать актуальный шаблон v6
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        <SpecialEquipmentImportReview
          v-if="flow.job.value && reviewStatuses.includes(flow.job.value.status)"
          :job="flow.job.value"
          @apply="flow.applyImport"
        />

        <section v-if="flow.job.value && terminalSuccessStatuses.includes(flow.job.value.status)" class="rounded-xl border border-emerald-200 bg-emerald-50 p-6" aria-labelledby="success-title">
          <CheckCircleIcon class="h-12 w-12 text-emerald-700" aria-hidden="true" />
          <h2 id="success-title" class="mt-4 text-2xl font-bold text-gray-950">Каталог обновлён</h2>
          <p class="mt-2 max-w-2xl text-base leading-relaxed text-gray-700">{{ completionMessage(flow.job.value) }} Версия каталога: <span class="font-bold tabular-nums">{{ flow.job.value.appliedRevision ?? '—' }}</span>. Каталог готов к использованию.</p>
          <div class="mt-5 flex flex-col gap-3 sm:flex-row"><NuxtLink to="/special-equipment" class="inline-flex min-h-11 items-center justify-center rounded-lg bg-blue-700 px-5 text-sm font-bold text-white hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">Открыть каталог</NuxtLink><button type="button" class="min-h-11 rounded-lg border border-emerald-700 px-5 text-sm font-bold text-emerald-900 hover:bg-emerald-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700" @click="flow.startNewImport">Загрузить ещё файл</button></div>
        </section>

        <div v-if="flow.actionError.value" class="rounded-lg border border-red-200 bg-red-50 p-4" role="alert"><p class="flex items-center gap-2 font-bold text-red-800"><ExclamationCircleIcon class="h-5 w-5" aria-hidden="true" />Операция не выполнена</p><p class="mt-1 text-sm leading-relaxed text-red-800">{{ flow.actionError.value }}</p></div>
        <div v-if="flow.actionMessage.value" class="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm leading-relaxed text-emerald-900" role="status">{{ flow.actionMessage.value }}</div>
      </div>

      <aside v-if="flow.job.value" class="h-fit rounded-xl border border-gray-200 bg-white p-5 xl:sticky xl:top-6" aria-labelledby="job-title">
        <h2 id="job-title" class="text-lg font-bold text-gray-950">Текущий импорт</h2>
        <dl class="mt-5 flex flex-col gap-4 text-sm">
          <div><dt class="text-gray-600">Файл</dt><dd class="mt-1 break-words font-semibold text-gray-950">{{ flow.job.value.filename }}</dd></div>
          <div><dt class="text-gray-600">Номер импорта</dt><dd class="mt-1 break-all font-mono text-gray-800">{{ flow.job.value.id }}</dd></div>
          <div><dt class="text-gray-600">Режим</dt><dd class="mt-1 font-semibold text-gray-950">{{ modeLabel(flow.job.value.mode) }}</dd></div>
          <div v-if="flow.job.value.targetWarehouse"><dt class="text-gray-600">Склад назначения</dt><dd class="mt-1 font-semibold text-gray-950">{{ warehouseLabel(flow.job.value.targetWarehouse) }}</dd></div>
          <div v-if="flow.job.value.catalogRevision !== null"><dt class="text-gray-600">Проверенная версия каталога</dt><dd class="mt-1 font-semibold tabular-nums text-gray-950">{{ flow.job.value.catalogRevision }}</dd></div>
          <div><dt class="text-gray-600">Обновлён</dt><dd class="mt-1 font-semibold text-gray-950">{{ formatDateTime(flow.job.value.updatedAt) }}</dd></div>
        </dl>
        <div class="mt-6 flex flex-col gap-2">
          <a v-if="flow.job.value.status !== 'awaiting_upload'" :href="flow.api.sourceContentUrl(flow.job.value.id)" class="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" download><ArrowDownTrayIcon class="h-5 w-5" aria-hidden="true" />Скачать исходный файл</a>
          <button v-if="flow.job.value.canCancel && !showCancelConfirmation" type="button" class="min-h-11 rounded-lg border border-red-300 px-4 text-sm font-bold text-red-800 hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600" @click="showCancelConfirmation = true">Отменить импорт</button>
          <div v-if="showCancelConfirmation" class="rounded-lg border border-red-200 bg-red-50 p-4"><p class="text-sm leading-relaxed text-red-900">Загрузка и обработка будут остановлены. Каталог не изменится, если применение ещё не завершено.</p><div class="mt-3 flex flex-col gap-2"><button type="button" class="min-h-10 rounded-lg bg-red-700 px-4 text-sm font-bold text-white hover:bg-red-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600" @click="confirmCancel">Подтвердить отмену</button><button type="button" class="min-h-10 rounded-lg border border-gray-300 bg-white px-4 text-sm font-semibold text-gray-800 hover:bg-gray-50" @click="showCancelConfirmation = false">Не отменять</button></div></div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationCircleIcon,
  InformationCircleIcon,
  PlusIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import { useSpecialEquipmentImport } from '../composables/useSpecialEquipmentImport'
import type { SpecialEquipmentImportJob, SpecialEquipmentImportStatus, SpecialEquipmentImportWarehouse, SpecialEquipmentImportWarehouseAssignment } from '../types'
import { localizeImportError } from '../utils/importErrors'
import SpecialEquipmentImportReview from './SpecialEquipmentImportReview.vue'
import SpecialEquipmentImportUpload from './SpecialEquipmentImportUpload.vue'

const flow = useSpecialEquipmentImport()
const localizedError = computed(() => {
  const job = flow.job.value
  if (!job) return null
  const code = job.errorCode
  const detail = job.errorDetail
  if (!code && !detail) return null
  return localizeImportError(code, detail)
})
const history = ref<SpecialEquipmentImportJob[]>([])
const historyOpen = ref(false)
const historyLoading = ref(false)
const historyError = ref('')
const showCancelConfirmation = ref(false)
const warehouses = ref<SpecialEquipmentImportWarehouse[]>([])
const warehousesLoading = ref(false)
const warehousesError = ref('')

const reviewStatuses: SpecialEquipmentImportStatus[] = ['preview_ready', 'validation_failed', 'applying', 'preview_stale', 'completed', 'completed_with_warnings', 'failed']
const terminalSuccessStatuses: SpecialEquipmentImportStatus[] = ['completed', 'completed_with_warnings']
const phases = [
  { key: 'validating_file', label: 'Структура файла', description: 'Проверка формата, листов, колонок и размера файла.' },
  { key: 'validating_data', label: 'Данные и связи', description: 'Проверка значений, кодов, категорий и характеристик.' },
  { key: 'preview_ready', label: 'Предварительная проверка', description: 'Сводка изменений и отчёт об ошибках.' },
] as const
const phaseOrder = phases.map((phase) => phase.key)

const visibleCounters = computed(() => flow.job.value?.counters.filter((counter) => !['bytes', 'images'].includes(counter.unit)) ?? [])
const phaseState = (key: typeof phases[number]['key']) => {
  const status = flow.job.value?.status
  const displayStatus = status === 'uploaded'
    ? 'validating_file'
    : status === 'transferring_images'
      ? 'validating_data'
      : status
  const current = phaseOrder.indexOf(displayStatus as typeof phases[number]['key'])
  const target = phaseOrder.indexOf(key)
  const previewOrLater = status && ['preview_ready', 'validation_failed', 'applying', 'completed', 'completed_with_warnings', 'preview_stale'].includes(status)
  if (previewOrLater || (current >= 0 && target < current)) return { state: 'done', className: 'border-emerald-200 bg-emerald-50' }
  if (target === current) return { state: 'active', className: 'border-blue-300 bg-blue-50' }
  return { state: 'pending', className: 'border-gray-200 bg-white' }
}

const loadHistory = async () => {
  historyLoading.value = true
  historyError.value = ''
  try { history.value = (await flow.api.listImports({ limit: 30 })).items }
  catch (error: unknown) { historyError.value = error instanceof Error ? error.message : 'Не удалось загрузить историю.' }
  finally { historyLoading.value = false }
}
const openHistoryJob = async (id: UUID) => { await flow.openJob(id); historyOpen.value = false; showCancelConfirmation.value = false }
const loadWarehouses = async () => {
  warehousesLoading.value = true
  warehousesError.value = ''
  try { warehouses.value = await flow.api.listActiveWarehouses() }
  catch { warehousesError.value = 'Не удалось загрузить список активных складов. Повторите попытку.' }
  finally { warehousesLoading.value = false }
}
const confirmCancel = async () => { await flow.cancelImport(); showCancelConfirmation.value = false; await loadHistory() }

const statusLabel = (status: SpecialEquipmentImportStatus) => ({ awaiting_upload: 'Ожидает файл', uploaded: 'Файл загружен', validating_file: 'Проверка структуры', validating_data: 'Проверка данных', transferring_images: 'Проверка данных', preview_ready: 'Проверка завершена', validation_failed: 'Есть ошибки', applying: 'Применяется', preview_stale: 'Требуется повторная проверка', completed: 'Завершён', completed_with_warnings: 'Завершён с предупреждениями', failed: 'Ошибка', failed_retryable: 'Можно повторить', cancelled: 'Отменён' }[status])
const statusClass = (status: SpecialEquipmentImportStatus) => ({ awaiting_upload: 'bg-gray-100 text-gray-800', uploaded: 'bg-blue-100 text-blue-900', validating_file: 'bg-blue-100 text-blue-900', validating_data: 'bg-blue-100 text-blue-900', transferring_images: 'bg-blue-100 text-blue-900', preview_ready: 'bg-emerald-100 text-emerald-900', validation_failed: 'bg-red-100 text-red-900', applying: 'bg-blue-100 text-blue-900', preview_stale: 'bg-amber-100 text-amber-900', completed: 'bg-emerald-100 text-emerald-900', completed_with_warnings: 'bg-amber-100 text-amber-900', failed: 'bg-red-100 text-red-900', failed_retryable: 'bg-amber-100 text-amber-900', cancelled: 'bg-gray-200 text-gray-800' }[status])
const modeLabel = (mode: string) => ({ APPEND: 'Только добавление', PATCH: 'Добавление и изменение', FULL_SNAPSHOT: 'Полная замена' }[mode] ?? mode)
const warehouseLabel = (warehouse: SpecialEquipmentImportWarehouseAssignment) =>
  `${warehouse.address}${warehouse.city_name ? `, ${warehouse.city_name}` : ''}`
const counterLabel = (unit: string) => ({ rows: 'Строки', entities: 'Объекты', issues: 'Ошибки и предупреждения' }[unit] ?? unit)
const completionMessage = (job: SpecialEquipmentImportJob) => job.status === 'completed_with_warnings'
  ? 'Корректные объекты применены, конфликтные пропущены и добавлены в отчёт.'
  : 'Все проверенные изменения применены.'
const formatCount = (value: number) => new Intl.NumberFormat('ru-RU').format(value)
const formatDateTime = (value: string) => value ? new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'

onMounted(async () => { await Promise.all([flow.restore(), loadHistory(), loadWarehouses()]) })
useSeoMeta({ title: 'Импорт спецтехники — CarCraft', description: 'Загрузка русского XLSX-шаблона, предварительная проверка и применение изменений каталога спецтехники.' })
</script>
