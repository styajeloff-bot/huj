<template>
  <div data-storefront-block="client.cabinet" aria-live="polite">
    <div class="flex items-start justify-between gap-4"><div><h2 class="text-lg font-semibold">Запросы документов</h2><p v-if="allowUpload" class="mt-1 text-sm text-gray-600">Откройте запрос, заполните сведения и приложите документы, если они нужны для ответа.</p></div><button v-if="!loading && batches.length" type="button" class="storefront-action-ghost rounded p-2" :disabled="refreshing" aria-label="Обновить историю запросов" @click="loadHistory(true)"><ArrowPathIcon class="h-5 w-5" :class="refreshing ? 'animate-spin' : ''" /></button></div>
    <p v-if="loading" class="mt-4 text-sm text-gray-600" role="status">Загружаем историю запросов…</p>
    <div v-else-if="loadError" role="alert" class="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ loadError }} <button type="button" class="underline" @click="loadHistory()">Попробовать снова</button></div>
    <p v-else-if="!batches.length" class="mt-4 text-sm text-gray-600">Запросов документов пока нет.</p>
    <div v-else class="mt-4 space-y-5"><article v-for="batch in batches" :key="batch.request_batch_id" class="border-t pt-4 first:border-t-0 first:pt-0"><header class="flex justify-between gap-4"><div><h3 class="text-sm font-semibold">{{ batch.leasing_company.name }}</h3><p v-if="batch.requested_by" class="text-xs text-gray-600">Запросил: {{ batch.requested_by.name }}</p></div><time v-if="batch.requested_at" class="text-xs text-gray-600">{{ formatDate(batch.requested_at) }}</time></header><p v-if="batch.comments" class="mt-3 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-900">{{ batch.comments }}</p><ul class="mt-3 divide-y rounded-md border"><li v-for="item in batch.items" :key="item.id" class="p-4"><div class="flex items-start justify-between gap-4"><div class="min-w-0"><div class="flex flex-wrap items-center gap-2"><span class="font-medium">{{ item.display_name }}</span><span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs">{{ statusLabel(item.status) }}</span></div><ul v-if="attachmentsFor(item).length" class="mt-2 space-y-1 text-sm text-gray-600"><li v-for="attachment in attachmentsFor(item)" :key="attachment.id" class="flex flex-wrap items-center gap-x-3"><span>{{ attachment.file_name ?? 'Файл без названия' }}</span><span v-if="attachment.file_size !== null">{{ formatFileSize(attachment.file_size) }}</span><a v-if="attachment.download_url" :href="resolveDownloadUrl(attachment.download_url)" download class="text-blue-700 underline">Скачать</a></li></ul><dl v-if="item.form_data" class="mt-2 space-y-2 text-sm text-gray-700"><div v-for="entry in formDataEntries(item)" :key="entry.label" class="rounded bg-gray-50 p-2"><dt class="font-medium">{{ entry.label }}</dt><dd class="mt-1 whitespace-pre-line break-words">{{ entry.value }}</dd></div></dl></div><button v-if="allowUpload && item.status === 'requested'" type="button" class="btn-primary shrink-0" :disabled="sendingRequestId !== null" @click="openResponse(item, batch.comments)">Ответить на запрос</button></div></li></ul></article></div>
    <DocumentRequestResponseModal v-if="responseItem" :show="Boolean(responseItem)" :item="responseItem" :comments="responseComments" :sending="sendingRequestId === responseItem.id" :submit-error="responseError" @close="closeResponse" @submit="submitResponse" />
  </div>
</template>

<script setup lang="ts">
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import DocumentRequestResponseModal from '~/features/documents/components/DocumentRequestResponseModal.vue'
import { createDocumentsApi, type DocumentRequestBatch, type DocumentRequestHistoryItem, type DocumentRequestHistoryStatus, type DocumentRequestLinkedDocument } from '~/features/documents/api/documentsApi'
import type { UUID } from '~/types/ids'
import { useNotificationCompanyContext } from '~/features/notifications'

const props = withDefaults(defineProps<{ applicationId: UUID; allowUpload?: boolean; refreshKey?: number; leasingCompanyId?: UUID }>(), { allowUpload: false, refreshKey: 0 })
const config = useRuntimeConfig(); const notificationCompanyContext = useNotificationCompanyContext(); const api = createDocumentsApi(config, () => props.leasingCompanyId, notificationCompanyContext)
const batches = ref<DocumentRequestBatch[]>([]); const loading = ref(true); const refreshing = ref(false); const loadError = ref(''); const responseItem = ref<DocumentRequestHistoryItem | null>(null); const responseComments = ref<string | null>(null); const responseError = ref(''); const responseIdempotencyKey = ref<string | null>(null); const sendingRequestId = ref<UUID | null>(null)
const statusLabels: Record<DocumentRequestHistoryStatus, string> = { requested: 'Ожидается', provided: 'Загружен', under_review: 'На проверке', approved: 'Одобрен', rejected: 'Отклонён', superseded: 'Заменён новым запросом' }
const statusLabel = (status: DocumentRequestHistoryStatus) => statusLabels[status] ?? status
const formatDate = (raw: string) => { const date = new Date(raw); return Number.isNaN(date.getTime()) ? raw : new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(date) }
const formatFileSize = (bytes: number) => bytes < 1024 ? `${bytes} Б` : bytes < 1024 ** 2 ? `${(bytes / 1024).toFixed(1)} КБ` : `${(bytes / 1024 ** 2).toFixed(1)} МБ`
const resolveDownloadUrl = (path: string) => api.downloadUrl(path)
const attachmentsFor = (item: DocumentRequestHistoryItem): DocumentRequestLinkedDocument[] => item.attachments?.length ? item.attachments : item.attachment ? [item.attachment] : item.document ? [item.document] : []
const errorMessage = (error: unknown, fallback: string) => typeof (error as { data?: { detail?: unknown } }).data?.detail === 'string' ? (error as { data: { detail: string } }).data.detail : fallback
const errorStatus = (error: unknown) => (error as { status?: number; statusCode?: number }).status ?? (error as { statusCode?: number }).statusCode
const bankAccountHistory = (item: DocumentRequestHistoryItem, data: Record<string, unknown>): string => {
  const version = item.form_schema?.schema_version
  if (version !== 1 && version !== 2) return 'Неподдерживаемая версия формы расчётных счетов'
  if (!Array.isArray(data.accounts)) return '—'
  return data.accounts.map((entry, index) => {
    const row = entry as Record<string, unknown>
    if (version === 1) {
      const bank = row.bank as Record<string, unknown> | undefined
      return `${index + 1}. ${String(bank?.name ?? '—')}; БИК ${String(bank?.bik ?? '—')}; счёт ${String(row.acc_number ?? '—')}`
    }
    return `${index + 1}. ${String(row.bank ?? '—')}; БИК ${String(row.bik ?? '—')}; счёт ${String(row.acc_number ?? '—')}; корр. счёт ${String(row.correspondent_account ?? '—')}`
  }).join('\n')
}
const counterpartyHistory = (data: Record<string, unknown>): string => {
  if (!Array.isArray(data.counterparties)) return '—'
  return data.counterparties.map((entry, index) => {
    const row = entry as Record<string, unknown>
    const identity = `${index + 1}. ${String(row.name ?? '—')} — ИНН ${String(row.inn ?? '—')}`
    return typeof row.comment === 'string' && row.comment.trim()
      ? `${identity}\nКомментарий: ${row.comment}`
      : identity
  }).join('\n')
}
const formDataEntries = (item: DocumentRequestHistoryItem): Array<{ label: string; value: string }> => { const data = item.form_data as Record<string, unknown>; if (item.document_type === 'main_counterparties') return [{ label: 'Контрагенты', value: counterpartyHistory(data) }]; if (item.document_type === 'open_bank_accounts') return [{ label: 'Расчётные счета', value: bankAccountHistory(item, data) }]; if (item.document_type === 'snils') { const number = String(data.number ?? '').replace(/\D/g, ''); return [{ label: 'СНИЛС', value: number.length === 11 ? `${number.slice(0, 3)}-${number.slice(3, 6)}-${number.slice(6, 9)} ${number.slice(9)}` : '—' }] }; if (item.document_type === 'beneficial_owner') return [{ label: 'ФИО выгодоприобретателя', value: String(data.fio ?? '—') }]; return Object.entries(data).map(([key, value]) => ({ label: formLabel(key), value: formatFormValue(value) })) }
const formatFormValue = (value: unknown) => Array.isArray(value) ? value.map(entry => typeof entry === 'object' && entry ? Object.values(entry as Record<string, unknown>).map(String).join(', ') : String(entry)).join('; ') : String(value ?? '—')
const formLabel = (key: string) => ({ counterparties: 'Контрагенты', accounts: 'Счета', number: 'СНИЛС', fio: 'Выгодоприобретатель' }[key] ?? key)
let historyRequest = 0
const loadHistory = async (silent = false) => { const request = ++historyRequest; if (silent) refreshing.value = true; else { loading.value = true; batches.value = [] }; loadError.value = ''; try { const response = await api.getDocumentRequestHistory(props.applicationId); if (request === historyRequest) batches.value = response.batches } catch (error) { if (request === historyRequest) loadError.value = errorMessage(error, 'Не удалось загрузить историю запросов.') } finally { if (request === historyRequest) { loading.value = false; refreshing.value = false } } }
const openResponse = (item: DocumentRequestHistoryItem, comments: string | null) => { responseItem.value = item; responseComments.value = comments; responseError.value = ''; responseIdempotencyKey.value = crypto.randomUUID() }
const closeResponse = () => { if (sendingRequestId.value === null) { responseItem.value = null; responseComments.value = null; responseError.value = ''; responseIdempotencyKey.value = null } }
const submitResponse = async (files: File[], formData?: Record<string, unknown>, userTitles?: string[]) => { const item = responseItem.value; const idempotencyKey = responseIdempotencyKey.value; if (!item || !idempotencyKey || sendingRequestId.value) return; sendingRequestId.value = item.id; responseError.value = ''; let submitted = false; try { await api.uploadRequestedDocument(files, props.applicationId, item.id, formData, idempotencyKey, userTitles); await loadHistory(true); submitted = true } catch (error) { if (errorStatus(error) === 409) { await loadHistory(true); responseError.value = 'Ответ уже отправлен. История запросов обновлена.' } else responseError.value = errorMessage(error, 'Не удалось отправить ответ. Проверьте данные и попробуйте ещё раз.') } finally { sendingRequestId.value = null; if (submitted) closeResponse() } }
watch(() => [props.applicationId, props.refreshKey, props.leasingCompanyId, notificationCompanyContext()] as const, () => loadHistory(), { immediate: true })
defineExpose({ reload: loadHistory })
</script>
