<template>
  <section class="rounded-xl border border-gray-200 bg-white p-5 sm:p-6" aria-labelledby="review-title">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h2 id="review-title" class="text-xl font-bold text-gray-950">3. Предварительная проверка</h2>
        <p class="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600">До подтверждения каталог не изменяется. Проверьте сводку, примеры изменений и отчёт об ошибках.</p>
      </div>
      <a v-if="showReportLink" :href="api.reportContentUrl(job.id)" class="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-gray-300 px-4 text-sm font-bold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" download><ArrowDownTrayIcon class="h-5 w-5" aria-hidden="true" />Отчёт валидации</a>
    </div>

    <div v-if="loadingPreview" class="mt-6 grid gap-3 sm:grid-cols-3" aria-label="Загрузка результата проверки"><div v-for="index in 3" :key="index" class="h-24 animate-pulse rounded-lg bg-gray-200 motion-reduce:animate-none" /></div>
    <div v-else-if="previewError" class="mt-6 rounded-xl border border-red-200 bg-red-50 p-5" role="alert">
      <div class="flex items-start gap-3">
        <ExclamationCircleIcon class="mt-0.5 h-5 w-5 shrink-0 text-red-700" aria-hidden="true" />
        <div class="flex-1 min-w-0">
          <p class="font-bold text-red-950">Результат проверки недоступен</p>
          <p class="mt-1 text-sm leading-relaxed text-red-800">{{ previewError }}</p>
          <button type="button" class="mt-3 inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-red-300 bg-white px-4 text-sm font-semibold text-red-800 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600" @click="loadPreview">
            <ArrowPathIcon class="h-4 w-4" aria-hidden="true" />Повторить
          </button>
        </div>
      </div>
    </div>

    <template v-else-if="preview">
      <div v-if="preview.targetWarehouse ?? job.targetWarehouse" class="mt-6 rounded-lg bg-blue-50 p-4 text-sm text-blue-950"><span class="font-semibold">Склад назначения:</span> {{ warehouseLabel(preview.targetWarehouse ?? job.targetWarehouse) }}</div>
      <div class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-lg bg-emerald-50 p-4"><p class="text-sm font-semibold text-emerald-900">Создать</p><p class="mt-2 text-2xl font-bold tabular-nums text-emerald-950">{{ totals.create }}</p></div>
        <div class="rounded-lg bg-blue-50 p-4"><p class="text-sm font-semibold text-blue-900">Изменить</p><p class="mt-2 text-2xl font-bold tabular-nums text-blue-950">{{ totals.update }}</p></div>
        <div class="rounded-lg bg-amber-50 p-4"><p class="text-sm font-semibold text-amber-900">Архивировать / удалить связь</p><p class="mt-2 text-2xl font-bold tabular-nums text-amber-950">{{ totals.archive + totals.remove }}</p></div>
        <div class="rounded-lg bg-gray-100 p-4"><p class="text-sm font-semibold text-gray-700">Без изменений</p><p class="mt-2 text-2xl font-bold tabular-nums text-gray-950">{{ totals.noop }}</p></div>
      </div>

      <div class="mt-6 grid gap-6 xl:grid-cols-2">
        <div>
          <h3 class="text-base font-bold text-gray-950">По сущностям</h3>
          <div class="mt-3 overflow-x-auto rounded-lg border border-gray-200">
            <table class="min-w-full text-sm">
              <thead class="bg-gray-50 text-left text-gray-600"><tr><th class="px-3 py-3 font-semibold">Сущность</th><th class="px-3 py-3 text-right font-semibold">Создать</th><th class="px-3 py-3 text-right font-semibold">Изменить</th><th class="px-3 py-3 text-right font-semibold">Удалить/архив</th><th class="px-3 py-3 text-right font-semibold">Ошибки</th></tr></thead>
              <tbody class="divide-y divide-gray-100"><tr v-for="row in countRows" :key="row.entity"><td class="px-3 py-3 font-semibold text-gray-900">{{ entityLabel(row.entity) }}</td><td class="px-3 py-3 text-right tabular-nums">{{ row.counts.create }}</td><td class="px-3 py-3 text-right tabular-nums">{{ row.counts.update }}</td><td class="px-3 py-3 text-right tabular-nums">{{ row.counts.archive + row.counts.remove }}</td><td class="px-3 py-3 text-right tabular-nums">{{ row.counts.rejected }}</td></tr></tbody>
            </table>
          </div>
        </div>

        <div>
          <h3 class="text-base font-bold text-gray-950">Влияние на операции пользователей</h3>
          <dl v-if="commerceRows.length" class="mt-3 grid gap-3 sm:grid-cols-2">
            <div v-for="row in commerceRows" :key="row.key" class="rounded-lg bg-gray-50 p-4"><dt class="text-sm leading-relaxed text-gray-600">{{ commerceLabel(row.key) }}</dt><dd class="mt-1 text-xl font-bold tabular-nums text-gray-950">{{ row.value }}</dd></div>
          </dl>
          <div v-else class="mt-3 rounded-lg bg-gray-50 p-5 text-sm leading-relaxed text-gray-600">Затронутых избранных, корзин, заявок или активных заказов не обнаружено.</div>
          <p class="mt-3 text-sm leading-relaxed text-gray-600">Исторические snapshots заявок и заказов импорт не переписывает.</p>
        </div>
      </div>

      <div class="mt-6">
        <h3 class="text-base font-bold text-gray-950">Примеры изменений</h3>
        <div v-if="preview.changes.length" class="mt-3 overflow-x-auto rounded-lg border border-gray-200">
          <table class="min-w-full text-sm"><thead class="bg-gray-50 text-left text-gray-600"><tr><th class="px-3 py-3 font-semibold">Код объекта</th><th class="px-3 py-3 font-semibold">Действие</th><th class="px-3 py-3 font-semibold">Поле</th><th class="px-3 py-3 font-semibold">До</th><th class="px-3 py-3 font-semibold">После</th></tr></thead><tbody class="divide-y divide-gray-100"><tr v-for="(change, index) in preview.changes" :key="`${change.entityCode}-${change.field}-${index}`"><td class="max-w-52 break-all px-3 py-3 font-mono text-gray-900">{{ change.entityCode }}</td><td class="px-3 py-3 font-semibold text-gray-800">{{ actionLabel(change.operation) }}</td><td class="px-3 py-3 text-gray-700">{{ change.field ?? '—' }}</td><td class="max-w-64 break-words px-3 py-3 text-gray-600">{{ displayScalar(change.before) }}</td><td class="max-w-64 break-words px-3 py-3 font-semibold text-gray-900">{{ displayScalar(change.after) }}</td></tr></tbody></table>
        </div>
        <p v-else class="mt-3 rounded-lg bg-gray-50 p-4 text-sm text-gray-600">Изменений нет: данные в файле совпадают с каталогом.</p>
        <p v-if="preview.changesTruncated" class="mt-3 text-sm leading-relaxed text-gray-600">Показано {{ preview.changesStored }} из {{ preview.changesTotal }} изменений. Сводные счётчики выше рассчитаны по всему файлу.</p>
      </div>
    </template>

    <div v-else-if="isValidationFailed" class="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-950">
      <div class="flex items-start gap-2.5">
        <InformationCircleIcon class="mt-0.5 h-5 w-5 shrink-0 text-amber-700" aria-hidden="true" />
        <div>
          <p class="font-bold">Предварительный просмотр изменений не сформирован</p>
          <p class="mt-1 text-amber-900">При проверке книги Excel были обнаружены ошибки. Сводка изменений (создать / изменить / удалить) формируется только при успешной валидации. Подробный список найденных проблем приведён в таблице ниже.</p>
        </div>
      </div>
    </div>

    <div class="mt-8 border-t border-gray-200 pt-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div><h3 class="text-lg font-bold text-gray-950">Ошибки и предупреждения</h3><p class="mt-1 text-sm text-gray-600">Отфильтруйте отчёт по типу проблемы или названию листа.</p></div>
        <p class="text-sm font-semibold tabular-nums text-gray-700">На экране: {{ issues.items.length }} · всего в файле: {{ issues.total }}</p>
      </div>
      <form class="mt-4 grid gap-3 sm:grid-cols-[10rem_12rem_auto]" @submit.prevent="resetAndLoadIssues">
        <div><label for="issue-severity" class="block text-sm font-semibold text-gray-800">Тип</label><select id="issue-severity" v-model="severity" class="mt-1 min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"><option value="">Все</option><option value="error">Ошибки</option><option value="warning">Предупреждения</option></select></div>
        <div><label for="issue-sheet" class="block text-sm font-semibold text-gray-800">Лист</label><input id="issue-sheet" v-model.trim="sheet" type="text" class="mt-1 min-h-11 w-full rounded-lg border border-gray-300 px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" placeholder="Объявления"></div>
        <button type="submit" class="min-h-11 self-end rounded-lg border border-gray-300 px-4 text-sm font-bold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">Применить</button>
      </form>

      <div v-if="issuesLoading" class="mt-4 h-32 animate-pulse rounded-lg bg-gray-200 motion-reduce:animate-none" />
      <div v-else-if="issuesError" class="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">{{ issuesError }}</div>
      <div v-else-if="issues.items.length" class="mt-4 overflow-x-auto rounded-lg border border-gray-200">
        <table class="min-w-full text-sm"><thead class="sticky top-0 bg-gray-50 text-left text-gray-600"><tr><th class="px-3 py-3 font-semibold">Тип</th><th class="px-3 py-3 font-semibold">Лист / строка</th><th class="px-3 py-3 font-semibold">Код ошибки</th><th class="px-3 py-3 font-semibold">Описание</th><th class="px-3 py-3 font-semibold">Код объекта</th></tr></thead><tbody class="divide-y divide-gray-100"><tr v-for="issue in issues.items" :key="issue.sequence"><td class="px-3 py-3"><span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold" :class="issue.severity === 'error' ? 'bg-red-100 text-red-900' : 'bg-amber-100 text-amber-900'"><ExclamationCircleIcon class="h-4 w-4" aria-hidden="true" />{{ issue.severity === 'error' ? 'Ошибка' : 'Предупреждение' }}</span></td><td class="whitespace-nowrap px-3 py-3 text-gray-700">{{ localizeSheetName(issue.sheetCode) }}<template v-if="issue.rowNumber">:{{ issue.rowNumber }}</template><template v-if="issue.columnName"> · {{ issue.columnName }}</template></td><td class="px-3 py-3 font-mono text-gray-800">{{ issue.code }}</td><td class="max-w-xl px-3 py-3 leading-relaxed text-gray-800"><div>{{ localizeImportIssue(issue.code, issue.message, { sheetCode: issue.sheetCode, rowNumber: issue.rowNumber, columnName: issue.columnName }).message }}</div><p v-if="localizeImportIssue(issue.code, issue.message, { sheetCode: issue.sheetCode, rowNumber: issue.rowNumber, columnName: issue.columnName }).hint" class="mt-1 text-xs text-gray-500"><span class="font-semibold text-gray-700">Рекомендация:</span> {{ localizeImportIssue(issue.code, issue.message, { sheetCode: issue.sheetCode, rowNumber: issue.rowNumber, columnName: issue.columnName }).hint }}</p></td><td class="max-w-56 break-all px-3 py-3 font-mono text-gray-700">{{ issue.entityCode ?? '—' }}</td></tr></tbody></table>
      </div>
      <div v-else class="mt-4 rounded-lg bg-emerald-50 p-5 text-sm leading-relaxed text-emerald-900"><span class="font-bold">Ошибок по текущему фильтру нет.</span> Можно продолжать проверку.</div>
      <p v-if="issues.truncated" class="mt-3 text-sm leading-relaxed text-amber-900">Всего найдено {{ issues.total }} проблем; сохранены первые {{ issues.stored }}. Сводные счётчики рассчитаны по всему файлу.</p>
      <div v-if="issues.nextCursor" class="mt-4"><button type="button" class="min-h-10 rounded-lg border border-gray-300 px-4 text-sm font-semibold text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" @click="loadMoreIssues">Показать ещё</button></div>
    </div>

    <div v-if="job.status === 'preview_ready' && preview" class="mt-8 border-t border-gray-200 pt-6">
      <h3 class="text-lg font-bold text-gray-950">4. Подтверждение применения</h3>
      <p class="mt-2 max-w-2xl text-sm leading-relaxed text-gray-600">Перед применением система ещё раз проверит, что каталог не был изменён после предварительной проверки.</p>
      <div v-if="requiresDestructiveConfirmation" class="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
        <p v-if="preview.destructiveCount > 0" class="font-bold text-amber-950">Будут архивированы товары или удалены дочерние связи: {{ preview.destructiveCount }} ({{ preview.destructivePercent }}%).</p>
        <p v-else class="font-bold text-amber-950">Полный снимок требует явного подтверждения перед применением.</p>
        <label for="destructive-confirmation" class="mt-3 block text-sm font-semibold text-amber-950">Введите «{{ confirmationPhrase }}»</label>
        <input id="destructive-confirmation" v-model="destructiveConfirmation" type="text" autocomplete="off" class="mt-2 min-h-11 w-full max-w-xl rounded-lg border border-amber-400 bg-white px-3 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-700">
      </div>
      <div v-if="preview.blockingIssues > 0" class="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm leading-relaxed text-red-800" role="alert">Исправьте {{ preview.blockingIssues }} блокирующих ошибок и загрузите новый файл. Эти изменения применить нельзя.</div>
      <div v-else-if="job.mode !== 'FULL_SNAPSHOT' && preview.warnings > 0" class="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm leading-relaxed text-amber-950" role="status">Корректные записи можно применить. Конфликтные агрегаты будут пропущены и останутся в отчёте.</div>
      <button type="button" class="mt-5 inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-blue-700 px-5 text-base font-bold text-white hover:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-600" :disabled="!canApply" @click="emitApply"><CheckCircleIcon class="h-5 w-5" aria-hidden="true" />Применить изменения</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ArrowDownTrayIcon, ArrowPathIcon, CheckCircleIcon, ExclamationCircleIcon, InformationCircleIcon } from '@heroicons/vue/24/outline'
import { createSpecialEquipmentImportApi } from '../api/specialEquipmentImportApi'
import type { SpecialEquipmentImportApplyRequest, SpecialEquipmentImportIssuesResponse, SpecialEquipmentImportJob, SpecialEquipmentImportOperationCounts, SpecialEquipmentImportPreview, SpecialEquipmentImportWarehouseAssignment } from '../types'
import { localizeImportIssue, localizeSheetName } from '../utils/importErrors'

const props = defineProps<{ job: SpecialEquipmentImportJob }>()
const emit = defineEmits<{ apply: [request: SpecialEquipmentImportApplyRequest] }>()
const api = createSpecialEquipmentImportApi(useRuntimeConfig())

const preview = ref<SpecialEquipmentImportPreview | null>(null)
const loadingPreview = ref(false)
const previewError = ref('')
const issues = ref<SpecialEquipmentImportIssuesResponse>({ items: [], total: 0, stored: 0, truncated: false, nextCursor: null })
const issuesLoading = ref(false)
const issuesError = ref('')
const severity = ref<'' | 'error' | 'warning'>('')
const sheet = ref('')
const destructiveConfirmation = ref('')

const emptyCounts = (): SpecialEquipmentImportOperationCounts => ({ create: 0, update: 0, archive: 0, remove: 0, noop: 0, rejected: 0 })
const countRows = computed(() => Object.entries(preview.value?.counts ?? {}).map(([entity, counts]) => ({ entity, counts })))
const totals = computed(() => countRows.value.reduce((sum, row) => ({
  create: sum.create + row.counts.create, update: sum.update + row.counts.update, archive: sum.archive + row.counts.archive,
  remove: sum.remove + row.counts.remove, noop: sum.noop + row.counts.noop, rejected: sum.rejected + row.counts.rejected,
}), emptyCounts()))
const commerceRows = computed(() => Object.entries(preview.value?.commerceImpact ?? {}).filter(([, value]) => value > 0).map(([key, value]) => ({ key, value })))
const requiresDestructiveConfirmation = computed(() => props.job.mode === 'FULL_SNAPSHOT'
  || preview.value?.requiresDestructiveConfirmation === true
  || (preview.value?.destructiveCount ?? 0) > 0)
const confirmationPhrase = computed(() => props.job.mode === 'FULL_SNAPSHOT' ? 'ПОЛНАЯ ЗАМЕНА' : 'ПОДТВЕРЖДАЮ ИЗМЕНЕНИЯ')
const canApply = computed(() => Boolean(
  props.job.canApply && preview.value && preview.value.blockingIssues === 0
  && (!requiresDestructiveConfirmation.value || destructiveConfirmation.value === confirmationPhrase.value),
))
const showReportLink = computed(() => ['preview_ready', 'validation_failed', 'completed', 'completed_with_warnings', 'failed'].includes(props.job.status))
const isValidationFailed = computed(() => ['validation_failed', 'failed'].includes(props.job.status) || !props.job.previewHash)

const loadPreview = async () => {
  if (!['preview_ready', 'applying', 'completed', 'completed_with_warnings'].includes(props.job.status)) return
  if (!props.job.previewHash) return
  loadingPreview.value = true
  previewError.value = ''
  try { preview.value = await api.getPreview(props.job.id) }
  catch (error: unknown) {
    const msg = error instanceof Error ? error.message : ''
    if (msg.includes('409') || msg.includes('Preview is not ready')) {
      previewError.value = 'Результат предварительной проверки пока недоступен. Дождитесь завершения обработки.'
    } else {
      previewError.value = msg || 'Не удалось загрузить результат проверки.'
    }
  }
  finally { loadingPreview.value = false }
}

const loadIssues = async (cursor?: number, append = false) => {
  issuesLoading.value = true
  issuesError.value = ''
  try {
    const response = await api.getIssues(props.job.id, { severity: severity.value || undefined, sheet: sheet.value || undefined, cursor, limit: 25 })
    issues.value = append ? { ...response, items: [...issues.value.items, ...response.items] } : response
  } catch (error: unknown) { issuesError.value = error instanceof Error ? error.message : 'Не удалось загрузить ошибки.' }
  finally { issuesLoading.value = false }
}
const resetAndLoadIssues = () => { void loadIssues() }
const loadMoreIssues = () => { if (issues.value.nextCursor) void loadIssues(issues.value.nextCursor, true) }
const emitApply = () => emit('apply', { confirmDestructiveChanges: requiresDestructiveConfirmation.value })

const warehouseLabel = (warehouse: SpecialEquipmentImportWarehouseAssignment | null) => warehouse
  ? `${warehouse.address}${warehouse.city_name ? `, ${warehouse.city_name}` : ''}`
  : '—'
const entityLabel = (value: string) => ({
  marks: 'Марки',
  models: 'Модели',
  modifications: 'Модификации',
  modification_categories: 'Категории модификаций',
  modification_attribute_values: 'Характеристики модификаций',
  categories: 'Категории',
  category_relations: 'Связи категорий',
  attribute_groups: 'Группы характеристик',
  attributes: 'Характеристики',
  attribute_options: 'Варианты характеристик',
  category_attributes: 'Характеристики категорий',
  products: 'Объявления',
  product_categories: 'Категории объявлений',
}[value] ?? value)
const commerceLabel = (value: string) => ({ favorites: 'Позиций в избранном', cart_items: 'Позиций в корзинах', leasing_applications: 'Активных лизинговых заявок', purchase_orders: 'Активных заказов', reservations: 'Активных резервов' }[value] ?? value)
const actionLabel = (value: string) => ({ create: 'Добавить', update: 'Изменить', archive: 'Архивировать', remove: 'Удалить связь', noop: 'Без изменений', rejected: 'Пропустить' }[value.toLowerCase()] ?? value)
const displayScalar = (value: string | number | boolean | null) => value === null ? '—' : typeof value === 'boolean' ? (value ? 'Да' : 'Нет') : String(value)

watch(() => props.job.id, async () => { preview.value = null; await Promise.all([loadPreview(), loadIssues()]) }, { immediate: true })
watch(() => props.job.status, (status) => { if (status === 'preview_ready' || status === 'completed' || status === 'completed_with_warnings') void loadPreview() })
</script>
