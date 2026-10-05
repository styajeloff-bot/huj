<template>
  <Modal
    :show="true"
    :close-on-overlay="false"
    title="История изменений реквизитов компании"
    size="5xl"
    body-class="max-h-[calc(100dvh-10rem)] overflow-y-auto"
    @close="emit('close')"
  >
    <div class="space-y-5">
      <p class="text-sm text-gray-600">Выберите версию, чтобы посмотреть сохранённые реквизиты и изменения относительно более ранней версии.</p>

      <div v-if="loading" class="py-10 text-center text-sm text-gray-600" role="status">Загрузка истории изменений…</div>
      <div v-else-if="error" class="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
        <p>{{ error }}</p>
        <button type="button" class="btn-secondary mt-3" @click="loadInitial">Повторить</button>
      </div>
      <div v-else-if="records.length === 0" class="rounded-md border border-gray-200 bg-gray-50 p-5 text-sm text-gray-700">
        История изменений пока пуста. Новые записи появляются после включения этой функции.
      </div>
      <template v-else>
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <label class="block text-sm font-medium text-gray-700">
            Было
            <select v-model="baseId" class="select-field mt-1 w-full" :disabled="olderRecords.length === 0" @change="loadComparison">
              <option v-if="olderRecords.length === 0" value="">Нет более ранней версии</option>
              <option v-for="record in olderRecords" :key="record.id" :value="record.id">{{ versionLabel(record) }}</option>
            </select>
          </label>
          <label class="block text-sm font-medium text-gray-700">
            Стало
            <select v-model="targetId" class="select-field mt-1 w-full" @change="selectTarget">
              <option v-for="record in records" :key="record.id" :value="record.id">{{ versionLabel(record) }}</option>
            </select>
          </label>
        </div>

        <div v-if="comparisonLoading" class="py-4 text-center text-sm text-gray-600" role="status">Загрузка сравнения…</div>
        <div v-else-if="comparisonError" class="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
          {{ comparisonError }}
        </div>
        <section v-else-if="comparison" aria-labelledby="history-comparison-title">
          <h4 id="history-comparison-title" class="mb-3 text-base font-semibold text-gray-900">Изменения</h4>
          <div v-if="comparison.diffs.length === 0" class="rounded-md bg-gray-50 p-3 text-sm text-gray-600">Между выбранными версиями изменений нет.</div>
          <div v-else class="overflow-x-auto rounded-lg border border-gray-200">
            <table class="min-w-full table-fixed text-left text-sm">
              <thead class="bg-gray-50 text-gray-700"><tr><th class="w-1/4 px-3 py-2 font-medium">Поле</th><th class="w-3/8 px-3 py-2 font-medium">Было</th><th class="w-3/8 px-3 py-2 font-medium">Стало</th></tr></thead>
              <tbody class="divide-y divide-gray-200">
                <tr v-for="diff in comparison.diffs" :key="diff.field">
                  <td class="break-words px-3 py-3 font-medium text-gray-900">{{ fieldLabel(diff.field) }}</td>
                  <td class="whitespace-pre-wrap break-words px-3 py-3 text-gray-700">{{ displayValue(diff.field, diff.old_value) }}</td>
                  <td class="whitespace-pre-wrap break-words px-3 py-3 text-gray-700">{{ displayValue(diff.field, diff.new_value) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <p v-else class="rounded-md bg-gray-50 p-3 text-sm text-gray-600">Это первая сохранённая версия. Для неё доступен полный снимок реквизитов без сравнения.</p>

        <details v-if="selectedBase" class="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <summary class="cursor-pointer text-base font-semibold text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
            Полный снимок версии «Было»
          </summary>
          <div class="mt-3 flex flex-wrap items-baseline justify-between gap-2">
            <span class="text-sm text-gray-500">{{ versionLabel(selectedBase) }}</span>
          </div>
          <dl class="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-2">
            <div v-for="field in snapshotFields" :key="field" :class="field.includes('address') ? 'md:col-span-2' : ''">
              <dt class="text-sm font-medium text-gray-700">{{ fieldLabel(field) }}</dt>
              <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-gray-900">{{ displayValue(field, selectedBase.snapshot[field]) }}</dd>
            </div>
            <div v-if="hasSnapshotField(selectedBase, 'distributor_brands')" class="md:col-span-2">
              <dt class="text-sm font-medium text-gray-700">Марки дистрибьютора</dt>
              <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-gray-900">{{ displayValue('distributor_brands', selectedBase.snapshot.distributor_brands) }}</dd>
            </div>
            <div v-if="hasSnapshotField(selectedBase, 'leasing_contractors')" class="md:col-span-2">
              <dt class="text-sm font-medium text-gray-700">Связи с подрядчиками</dt>
              <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-gray-900">{{ displayValue('leasing_contractors', selectedBase.snapshot.leasing_contractors) }}</dd>
            </div>
          </dl>
        </details>

        <details class="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <summary class="cursor-pointer text-base font-semibold text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
            Полный снимок версии «Стало»
          </summary>
          <div class="mt-3 flex flex-wrap items-baseline justify-between gap-2">
            <span class="text-sm text-gray-500">{{ selectedTarget ? versionLabel(selectedTarget) : '' }}</span>
          </div>
          <dl v-if="selectedTarget" class="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-2">
            <div v-for="field in snapshotFields" :key="field" :class="field.includes('address') ? 'md:col-span-2' : ''">
              <dt class="text-sm font-medium text-gray-700">{{ fieldLabel(field) }}</dt>
              <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-gray-900">{{ displayValue(field, selectedTarget.snapshot[field]) }}</dd>
            </div>
            <div v-if="hasSnapshotField(selectedTarget, 'distributor_brands')" class="md:col-span-2">
              <dt class="text-sm font-medium text-gray-700">Марки дистрибьютора</dt>
              <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-gray-900">{{ displayValue('distributor_brands', selectedTarget.snapshot.distributor_brands) }}</dd>
            </div>
            <div v-if="hasSnapshotField(selectedTarget, 'leasing_contractors')" class="md:col-span-2">
              <dt class="text-sm font-medium text-gray-700">Связи с подрядчиками</dt>
              <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-gray-900">{{ displayValue('leasing_contractors', selectedTarget.snapshot.leasing_contractors) }}</dd>
            </div>
          </dl>
        </details>

        <button v-if="hasMore" type="button" class="btn-secondary" :disabled="loadingMore" @click="loadMore">{{ loadingMore ? 'Загрузка…' : 'Загрузить более ранние версии' }}</button>
        <p v-if="loadMoreError" class="text-sm text-red-700" role="alert">{{ loadMoreError }}</p>
      </template>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { createCompaniesAdminApi, type AdminCompanyChangeHistoryComparison, type AdminCompanyChangeHistoryRecord } from '~/features/admin/companies/manage/api/companiesAdminApi'
import type { UUID } from '~/types/ids'

const props = defineProps<{ companyId: UUID }>()
const emit = defineEmits<{ close: [] }>()
const api = createCompaniesAdminApi(useRuntimeConfig())
const snapshotFields = ['name', 'company_type', 'inn', 'kpp', 'ogrn', 'is_active', 'phone', 'email', 'website', 'legal_address', 'actual_address'] as const
const fieldLabels: Record<string, string> = { name: 'Название', company_type: 'Тип компании', inn: 'ИНН', kpp: 'КПП', ogrn: 'ОГРН', is_active: 'Статус', phone: 'Телефон', email: 'Email', website: 'Веб-сайт', legal_address: 'Юридический адрес', actual_address: 'Фактический адрес', distributor_brands: 'Марки дистрибьютора', leasing_contractors: 'Связи с подрядчиками' }
const actionLabels: Record<string, string> = { company_profile_saved: 'Реквизиты сохранены', company_status_changed: 'Статус изменён', distributor_brands_saved: 'Марки сохранены', leasing_contractors_saved: 'Связи с подрядчиками сохранены' }
const companyTypeLabels: Record<string, string> = { dealer: 'Дилер', leasing_company: 'Лизинговая компания', distributor: 'Дистрибьютор', other: 'Другое' }

const records = ref<AdminCompanyChangeHistoryRecord[]>([])
const nextCursor = ref<string | null>(null)
const hasMore = ref(false)
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')
const loadMoreError = ref('')
const targetId = ref('')
const baseId = ref('')
const comparison = ref<AdminCompanyChangeHistoryComparison | null>(null)
const comparisonLoading = ref(false)
const comparisonError = ref('')
let comparisonRequestId = 0
const selectedTarget = computed(() => records.value.find((record) => record.id === targetId.value) ?? null)
const targetIndex = computed(() => records.value.findIndex((record) => record.id === targetId.value))
const olderRecords = computed(() => targetIndex.value < 0 ? [] : records.value.slice(targetIndex.value + 1))
const selectedBase = computed(() => olderRecords.value.find((record) => record.id === baseId.value) ?? null)

function fieldLabel(field: string): string { return fieldLabels[field] ?? field }
function formatDate(value: string): string { return new Date(value).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow', dateStyle: 'medium', timeStyle: 'medium' }) }
function versionLabel(record: AdminCompanyChangeHistoryRecord): string { return `${formatDate(record.changed_at)} · ${record.actor_display_name} · ${actionLabels[record.action] ?? record.action}` }
function hasSnapshotField(record: AdminCompanyChangeHistoryRecord, field: string): boolean { return Object.prototype.hasOwnProperty.call(record.snapshot, field) }
function displayValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (field === 'company_type' && typeof value === 'string') return companyTypeLabels[value] ?? value
  if (typeof value === 'boolean') return value ? 'Активна' : 'Неактивна'
  if (Array.isArray(value)) return value.length === 0 ? '—' : value.map(displayListItem).join('\n')
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}
function displayListItem(value: unknown): string {
  if (value && typeof value === 'object') {
    const item = value as { name?: unknown; inn?: unknown }
    if (typeof item.name === 'string') return typeof item.inn === 'string' && item.inn ? `${item.name} (ИНН ${item.inn})` : item.name
    return JSON.stringify(value)
  }
  return String(value)
}
function responseError(): string { return 'Не удалось загрузить историю изменений. Проверьте подключение и попробуйте ещё раз.' }
function mergePage(items: AdminCompanyChangeHistoryRecord[]): void {
  const existing = new Set(records.value.map((record) => record.id))
  records.value.push(...items.filter((record) => !existing.has(record.id)))
}
async function loadInitial(): Promise<void> {
  loading.value = true; error.value = ''; loadMoreError.value = ''; comparison.value = null
  try {
    const response = await api.getCompanyChangeHistory(props.companyId)
    records.value = response.items
    nextCursor.value = response.pagination.next_cursor
    hasMore.value = response.pagination.has_more
    targetId.value = records.value[0]?.id ?? ''
    await selectTarget()
  } catch { error.value = responseError() } finally { loading.value = false }
}
async function loadMore(): Promise<void> {
  if (loadingMore.value || !hasMore.value || !nextCursor.value) return
  loadingMore.value = true; loadMoreError.value = ''
  try {
    const response = await api.getCompanyChangeHistory(props.companyId, nextCursor.value)
    mergePage(response.items)
    nextCursor.value = response.pagination.next_cursor
    hasMore.value = response.pagination.has_more
  } catch { loadMoreError.value = 'Не удалось загрузить более ранние версии. Попробуйте ещё раз.' } finally { loadingMore.value = false }
}
async function selectTarget(): Promise<void> {
  baseId.value = olderRecords.value[0]?.id ?? ''
  await loadComparison()
}
async function loadComparison(): Promise<void> {
  const requestId = ++comparisonRequestId
  comparison.value = null; comparisonError.value = ''
  if (!targetId.value || !baseId.value) return
  comparisonLoading.value = true
  try {
    const result = await api.compareCompanyChangeHistory(props.companyId, baseId.value, targetId.value)
    if (requestId === comparisonRequestId) comparison.value = result
  } catch {
    if (requestId === comparisonRequestId) comparisonError.value = 'Не удалось загрузить сравнение версий. Выберите версии ещё раз или повторите попытку.'
  } finally {
    if (requestId === comparisonRequestId) comparisonLoading.value = false
  }
}

void loadInitial()
</script>
