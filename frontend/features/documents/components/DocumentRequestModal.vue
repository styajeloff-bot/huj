<template>
  <Modal :show="show" title="Запросить документы" size="xl" :close-on-overlay="!submitting" :closable="!submitting" @close="emit('close')">
    <form data-storefront-block="client.cabinet" class="space-y-5" @submit.prevent="submitRequest">
      <fieldset :disabled="submitting">
        <legend class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">Документы</legend>
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Добавьте от 1 до 10 документов, которые должен предоставить клиент.</p>
        <p v-if="catalogLoading" class="mt-3 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Загружаем типы документов…</p>
        <div v-else-if="catalogError" role="alert" class="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {{ catalogError }} <button type="button" class="underline" @click="loadCatalog">Повторить</button>
        </div>
        <div class="mt-4 space-y-4">
          <div v-for="(row, index) in rows" :key="row.key" class="flex items-start gap-2">
            <div class="min-w-0 flex-1 space-y-2">
              <label :for="`document-request-type-${row.key}`" class="block text-sm font-medium">Документ {{ index + 1 }}</label>
              <select :id="`document-request-type-${row.key}`" v-model="row.source" class="storefront-control block w-full rounded-md border px-3 py-2 text-sm" @change="changeSource(row)">
                <option value="">Выберите тип документа</option>
                <option v-for="type in catalog" :key="type.type_code" :value="type.type_code">{{ type.display_name }}</option>
                <option value="custom">Произвольный документ</option>
              </select>
              <label :for="`document-request-name-${row.key}`" class="block text-sm font-medium">Отображаемое название</label>
              <input :id="`document-request-name-${row.key}`" v-model="row.displayName" type="text" maxlength="255" autocomplete="off" class="storefront-control block w-full rounded-md border px-3 py-2 text-sm" :aria-invalid="Boolean(fieldErrors[row.key])" :placeholder="row.source === 'custom' ? 'Введите название документа' : 'Название документа'" @input="clearFieldError(row.key)">
              <p v-if="row.source && row.source !== 'custom'" class="text-xs text-amber-800">Тип документа и состав обязательных полей сохраняются</p>
              <p v-if="fieldErrors[row.key]" role="alert" class="text-sm text-red-700">{{ fieldErrors[row.key] }}</p>
            </div>
            <button v-if="rows.length > 1" type="button" class="storefront-action-ghost mt-7 rounded-md p-2 text-red-700" :aria-label="`Удалить документ ${index + 1}`" @click="removeRow(index)"><TrashIcon class="h-5 w-5" /></button>
          </div>
        </div>
        <button v-if="rows.length < MAX_DOCUMENTS" type="button" class="storefront-action-ghost mt-3 inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-blue-700" @click="addRow"><PlusIcon class="h-5 w-5" />Добавить документ</button>
      </fieldset>
      <div><label for="document-request-comment" class="mb-1 block text-sm font-medium">Комментарий для клиента <span class="font-normal text-gray-500">(необязательно)</span></label><textarea id="document-request-comment" v-model="comments" :disabled="submitting" rows="3" class="storefront-control block w-full rounded-md border px-3 py-2 text-sm" placeholder="Уточните требования к документам" /></div>
      <div v-if="submitError" role="alert" class="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ submitError }}</div>
      <div class="flex justify-end gap-2 border-t pt-4"><button type="button" class="btn-secondary" :disabled="submitting" @click="emit('close')">Отмена</button><button type="submit" class="btn-primary" :disabled="submitting || catalogLoading"><ArrowPathIcon v-if="submitting" class="h-4 w-4 animate-spin" />{{ submitting ? 'Отправляем…' : 'Запросить документы' }}</button></div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import { ArrowPathIcon, PlusIcon, TrashIcon } from '@heroicons/vue/24/outline'
import Modal from '~/components/ui/Modal.vue'
import { createDocumentsApi, type DocumentType } from '~/features/documents/api/documentsApi'
import { createLeasingApi, type RequestedDocumentInput } from '~/features/leasing/api/leasingApi'
import type { UUID } from '~/types/ids'

interface DocumentRow { key: string; source: string; displayName: string }
const MAX_DOCUMENTS = 10
const props = defineProps<{ show: boolean; applicationId: UUID }>()
const emit = defineEmits<{ close: []; success: [] }>()
const config = useRuntimeConfig()
const route = useRoute()
const documentsApi = createDocumentsApi(config, () => route.query.leasing_company_id)
const leasingApi = createLeasingApi(config, () => route.query.leasing_company_id)
let sequence = 0
const newRow = (): DocumentRow => ({ key: `row-${++sequence}`, source: '', displayName: '' })
const rows = ref<DocumentRow[]>([newRow()])
const catalog = ref<DocumentType[]>([])
const catalogLoading = ref(false)
const catalogError = ref('')
const comments = ref('')
const submitting = ref(false)
const submitError = ref('')
const fieldErrors = ref<Record<string, string>>({})
const errorMessage = (error: unknown, fallback: string) => typeof (error as { data?: { detail?: unknown } }).data?.detail === 'string' ? (error as { data: { detail: string } }).data.detail : fallback
const loadCatalog = async () => { catalogLoading.value = true; catalogError.value = ''; try { catalog.value = (await documentsApi.getDocumentTypes()).types } catch (error) { catalogError.value = errorMessage(error, 'Не удалось загрузить типы документов.') } finally { catalogLoading.value = false } }
const changeSource = (row: DocumentRow) => { const type = catalog.value.find(item => item.type_code === row.source); row.displayName = type?.display_name ?? ''; clearFieldError(row.key) }
const addRow = () => { if (rows.value.length < MAX_DOCUMENTS) rows.value.push(newRow()) }
const removeRow = (index: number) => { if (rows.value.length > 1) rows.value.splice(index, 1) }
const clearFieldError = (key: string) => { delete fieldErrors.value[key]; submitError.value = '' }
const validate = () => { const errors: Record<string, string> = {}; for (const row of rows.value) { if (!row.source) errors[row.key] = 'Выберите тип документа'; else if (!row.displayName.trim()) errors[row.key] = 'Введите отображаемое название документа' }; fieldErrors.value = errors; return Object.keys(errors).length === 0 }
const submitRequest = async () => { if (submitting.value || !validate()) return; submitting.value = true; submitError.value = ''; try { const requestedDocuments: RequestedDocumentInput[] = rows.value.map(row => row.source === 'custom' ? { source: 'custom', display_name: row.displayName.trim() } : { source: 'catalog', document_type: row.source, display_name: row.displayName.trim() }); await leasingApi.requestDocuments(props.applicationId, requestedDocuments, comments.value.trim() || null); emit('success') } catch (error) { submitError.value = errorMessage(error, 'Не удалось отправить запрос. Попробуйте ещё раз.') } finally { submitting.value = false } }
watch(() => props.show, visible => { if (visible) { rows.value = [newRow()]; comments.value = ''; submitError.value = ''; fieldErrors.value = {}; loadCatalog() } })
</script>
