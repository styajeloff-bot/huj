<template>
  <section class="dr-workspace">
    <header class="dr-header"><div><h1>Справочник документов</h1><p>Договоры и файлы, привязанные к ЛК, дилерам, дистрибьюторам и маркам — для выбора в условиях монетизации.<br />Документы программ стимулирования доступны в разделе программ стимулирования.</p></div><button v-if="canManage" type="button" class="dr-primary" @click="form = { mode: 'create' }">Добавить документ</button></header>
    <form class="dr-filters" @submit.prevent="applyFilters">
      <div class="dr-grid dr-grid-three"><RegistryCompanyPicker v-for="role in roles" :key="role" :api="api" :role="role" :label="companyNames[role]" :selected-ids="filters[companyKeys[role]] ? [filters[companyKeys[role]]] : []" :companies="filterCompanies[role]" single @change="(ids, companies) => setCompany(role, ids, companies)" /></div>
      <div class="dr-grid dr-grid-four"><label>Область поиска компаний<select v-model="filters.participant_scope" class="select-field"><option value="participants">Участники</option><option value="related">Связанные компании</option></select></label><label>Тип документа<select v-model="filters.document_type" class="select-field"><option value="">Все типы</option><option v-for="(name, code) in typeLabels" :key="code" :value="code">{{ name }}</option></select></label><label>Марка<select v-model="filters.mark_id" class="select-field"><option value="">Все марки</option><option v-for="mark in marks" :key="mark.id" :value="mark.id">{{ mark.name }}</option></select></label><label>Модель<select v-model="filters.model_id" class="select-field" :disabled="!filters.mark_id"><option value="">Все модели</option><option v-for="model in models" :key="model.id" :value="model.id">{{ model.name }}</option></select></label></div>
      <div class="dr-grid dr-grid-four"><label>Название или номер<input v-model="filters.search" placeholder="Поиск документов" /></label><label>Статус<select v-model="filters.status" class="select-field"><option value="">Все статусы</option><option v-for="(name, status) in statusLabels" :key="status" :value="status">{{ name }}</option></select></label><label>Начало не раньше<input v-model="filters.valid_from" type="date" /></label><label>Окончание не позже<input v-model="filters.valid_to" type="date" :min="filters.valid_from" /></label></div>
      <div class="dr-filter-footer"><small>Каждое условие может выполняться на разных документах одной связки. Период — полное попадание.</small><div class="dr-actions"><button type="button" class="dr-link" @click="resetFilters">Сбросить</button><button type="submit" class="dr-secondary">Применить</button></div></div>
    </form>
    <div class="dr-toolbar"><div class="dr-view-switch" aria-label="Вид справочника"><button type="button" :aria-pressed="view === 'cards'" @click="switchView('cards')">Карточки</button><button type="button" :aria-pressed="view === 'table'" @click="switchView('table')">Таблица</button></div><button type="button" class="dr-secondary" :disabled="exporting || loading || filtersPending || !hasResult" @click="exportExcel">{{ exporting ? 'Выгрузка…' : 'Скачать Excel' }}</button></div>
    <p v-if="error" class="dr-error" role="alert">{{ error }} <button type="button" class="dr-link" @click="load()">Повторить</button></p><div v-if="loading && !rows.length && !groups.length" class="dr-empty" role="status">Загрузка документов…</div>
    <template v-if="view === 'cards'"><RegistryGroupCard v-for="group in groups" :key="group.group_id" :group="group" :api="api" :busy="busy" @add="addChild" @history="history = $event" @edit="edit" @activate="activate" @remove="prepareDelete" /><div v-if="total > 20" class="dr-pagination"><button type="button" class="dr-secondary" :disabled="page === 1 || loading || filtersPending" @click="changePage(-1)">Назад</button><span>Страница {{ page }} из {{ Math.ceil(total / 20) }}</span><button type="button" class="dr-secondary" :disabled="page * 20 >= total || loading || filtersPending" @click="changePage(1)">Вперёд</button></div></template>
    <template v-else><div v-if="rows.length" class="dr-table-scroll"><table class="dr-table"><thead><tr><th v-for="name in columns" :key="name">{{ name }}</th></tr></thead><tbody><tr v-for="row in rows" :key="row.group_id"><td>{{ typeLabels[row.display_document.document_type] }}</td><td><button type="button" class="dr-link" @click="emit('open', row.display_document.id)">{{ row.display_document.contract_number }}</button></td><td>{{ row.display_document.name }}</td><td><div v-for="line in companyLines(row.participants)" :key="line">{{ line }}</div><template v-if="!companyLines(row.participants).length">—</template></td><td><div v-for="line in companyLines(row.display_document.related_companies)" :key="line">{{ line }}</div><template v-if="!companyLines(row.display_document.related_companies).length">—</template></td><td><template v-for="(related, index) in row.related_documents" :key="related.id"><span v-if="index"> + </span><NuxtLink :to="documentLink(related.id)" class="dr-link">{{ related.label }}</NuxtLink></template><template v-if="!row.related_documents.length">—</template></td><td>{{ row.participants.mark_name || '—' }}</td><td>{{ row.participants.model_name || '—' }}</td><td>{{ dateLabel(row.display_document.current_version.valid_from) }}</td><td>{{ row.display_document.current_version.valid_to ? dateLabel(row.display_document.current_version.valid_to) : '—' }}</td><td><span class="dr-status" :class="row.display_document.status">{{ statusLabels[row.display_document.status] }}</span></td><td>{{ row.display_document.current_version.files.length }}</td></tr></tbody></table></div><div v-if="hasMore" class="dr-center"><button type="button" class="dr-secondary" :disabled="loading" @click="load(true)">{{ loading ? 'Загрузка…' : 'Показать ещё 10' }}</button></div></template>
    <p v-if="!loading && !error && !(view === 'cards' ? groups.length : rows.length)" class="dr-empty">Документы не найдены. Измените фильтры или добавьте документ.</p>
    <RegistryModal v-if="documentId" title="Просмотр документа" wide @close="emit('closeDocument')"><p v-if="detailLoading" role="status">Загрузка документа…</p><p v-if="detailError" class="dr-error" role="alert">{{ detailError }}</p><p v-if="error" class="dr-error" role="alert">{{ error }}</p><RegistryDocumentCard v-if="selected" :api="api" :document="selected" :can-manage="canManage" :busy="busy" @history="history = $event" @edit="edit" @activate="activate" @remove="prepareDelete" /></RegistryModal>
    <RegistryDocumentForm v-if="form" :api="api" :mode="form.mode" :document="form.document" :group-id="form.groupId" :inherited="form.inherited" @close="form = null" @saved="saved" />
    <RegistryHistory v-if="history" :api="api" :document="history" :can-manage="canManage" @changed="versionChanged" @close="history = null" />
    <RegistryModal v-if="deleteTarget" title="Удаление документа" :busy="busy" @close="deleteTarget = null"><p>Удалить «{{ deleteTarget.name }}» №{{ deleteTarget.contract_number }}{{ deleteTarget.is_main ? ' и все документы связки' : '' }}?</p><p v-if="!usages && !deleteError" role="status">Проверка связанных условий…</p><template v-if="usages"><p>Документов будет удалено: {{ usages.document_ids.length }}. Файлы станут недоступны пользователям.</p><p v-if="usages.programs.length">Связи будут сняты со следующих условий. Сами условия сохранятся:</p><ul><li v-for="program in usages.programs" :key="program.id">{{ program.name }}</li></ul><p v-if="!usages.programs.length" class="dr-meta">Связанных условий монетизации нет.</p></template><p v-if="deleteError" class="dr-error" role="alert">{{ deleteError }}</p><footer class="dr-actions"><button type="button" class="dr-secondary" :disabled="busy" @click="deleteTarget = null">Отмена</button><button type="button" class="dr-delete-button" :disabled="busy || !usages" @click="confirmDelete">{{ busy ? 'Удаление…' : 'Удалить' }}</button></footer></RegistryModal>
  </section>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { isUuid } from '~/types/ids'
import type { DocumentRegistryApi } from '../api'
import { registryError } from '../api'
import { companyLines, dateLabel, statusLabels, typeLabels, type CatalogItem, type CompanyRole, type CompanySelection, type DeletionUsages, type DocumentGroup, type ReferenceDocument, type RegistryCompany, type RegistryFilters, type TableRow } from '../types'
import RegistryCompanyPicker from './RegistryCompanyPicker.vue'
import RegistryGroupCard from './RegistryGroupCard.vue'
import RegistryDocumentCard from './RegistryDocumentCard.vue'
import RegistryDocumentForm from './RegistryDocumentForm.vue'
import RegistryHistory from './RegistryHistory.vue'
import RegistryModal from './RegistryModal.vue'
import '../registry.css'
const props = defineProps<{ api: DocumentRegistryApi; canManage: boolean; documentId?: string }>()
const emit = defineEmits<{ open: [id: string]; closeDocument: [] }>()
const route = useRoute()
const documentLink = (id: string) => ({ path: '/workspace/document-registry', query: { ...route.query, document: id } })
const defaults = (): RegistryFilters => ({ search: '', document_type: '', mark_id: '', model_id: '', valid_from: '', valid_to: '', status: '', leasing_company_id: '', dealer_company_id: '', distributor_company_id: '', participant_scope: 'participants' })
const filters = reactive(defaults()); let applied = defaults(); let displayedFilters = defaults()
const filtersPending = ref(false); const hasResult = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | undefined
let modelGeneration = 0
const roles = ['leasing_company', 'distributor', 'dealer'] as const
const companyKeys = { leasing_company: 'leasing_company_id', distributor: 'distributor_company_id', dealer: 'dealer_company_id' } as const
const companyNames = { leasing_company: 'Лизинговая компания', distributor: 'Дистрибьютор', dealer: 'Дилер' }
const filterCompanies = reactive<Record<CompanyRole, RegistryCompany[]>>({ leasing_company: [], dealer: [], distributor: [] })
const view = ref<'cards' | 'table'>('cards'); const groups = ref<DocumentGroup[]>([]); const rows = ref<TableRow[]>([]); const page = ref(1); const total = ref(0); const cursor = ref<string | null>(null); const hasMore = ref(false)
const loading = ref(false); const busy = ref(false); const exporting = ref(false); const error = ref(''); let generation = 0; let detailGeneration = 0
const marks = ref<CatalogItem[]>([]); const models = ref<CatalogItem[]>([])
const form = ref<{ mode: 'create' | 'edit'; document?: ReferenceDocument; groupId?: string; inherited?: CompanySelection } | null>(null)
const history = ref<ReferenceDocument | null>(null); const selected = ref<ReferenceDocument | null>(null); const detailLoading = ref(false); const detailError = ref('')
const deleteTarget = ref<ReferenceDocument | null>(null); const usages = ref<DeletionUsages | null>(null); const deleteError = ref('')
const columns = ['Тип документа', 'Номер', 'Название', 'Участники', 'Связанные компании', 'Связанные документы', 'Марка', 'Модель', 'Действует с', 'Действует по', 'Статус', 'Кол-во файлов']
function setCompany(role: CompanyRole, ids: string[], companies: RegistryCompany[]) { filters[companyKeys[role]] = ids[0] ?? ''; filterCompanies[role] = companies }
async function loadModels() { const token = ++modelGeneration; models.value = []; const id = filters.mark_id; if (!id) return; try { const result = await props.api.catalog(id); if (token === modelGeneration) models.value = result.items } catch (failure) { if (token === modelGeneration) error.value = registryError(failure) } }
async function load(append = false) {
  const token = ++generation; const query = { ...applied }; loading.value = true; error.value = ''
  try {
    if (view.value === 'cards') { const result = await props.api.groups(query, page.value); if (token === generation) { groups.value = result.items; total.value = result.pagination.total; displayedFilters = query; hasResult.value = true } }
    else { const result = await props.api.table(query, append ? cursor.value ?? undefined : undefined); if (token === generation) { rows.value = append ? [...rows.value, ...result.items] : result.items; cursor.value = result.pagination.next_cursor; hasMore.value = result.pagination.has_more; displayedFilters = query; hasResult.value = true } }
  } catch (failure) { if (token === generation) error.value = registryError(failure) } finally { if (token === generation) loading.value = false }
}
function applyFilters() {
  clearTimeout(searchTimer); filtersPending.value = false
  ++generation; loading.value = false; hasResult.value = false
  page.value = 1; total.value = 0; groups.value = []; rows.value = []; cursor.value = null; hasMore.value = false
  if (filters.valid_from && filters.valid_to && filters.valid_from > filters.valid_to) { error.value = 'Окончание периода не может быть раньше начала.'; return }
  applied = { ...filters }; void load()
}
function resetFilters() { Object.assign(filters, defaults()); for (const role of roles) filterCompanies[role] = []; models.value = []; applyFilters() }
function switchView(value: 'cards' | 'table') { if (view.value === value) return; view.value = value; applyFilters() }
watch(() => filters.mark_id, () => { filters.model_id = ''; void loadModels() }, { flush: 'sync' })
watch(() => [filters.document_type, filters.mark_id, filters.model_id, filters.valid_from, filters.valid_to, filters.status, filters.leasing_company_id, filters.dealer_company_id, filters.distributor_company_id, filters.participant_scope], applyFilters)
watch(() => filters.search, () => {
  clearTimeout(searchTimer); ++generation; loading.value = false; filtersPending.value = true
  searchTimer = setTimeout(applyFilters, 300)
})
function changePage(delta: number) { page.value += delta; void load() }
async function exportExcel() { if (loading.value || filtersPending.value || !hasResult.value) return; exporting.value = true; error.value = ''; try { await props.api.export(displayedFilters) } catch (failure) { error.value = registryError(failure) } finally { exporting.value = false } }
function addChild(group: DocumentGroup) { if (group.main_document) form.value = { mode: 'create', groupId: group.group_id, inherited: group.main_document.related_companies } }
function edit(document: ReferenceDocument) { form.value = { mode: 'edit', document } }
async function saved(document: ReferenceDocument) { form.value = null; if (selected.value?.id === document.id) selected.value = document; await load() }
async function versionChanged(document: ReferenceDocument) { history.value = document; if (selected.value?.id === document.id) selected.value = document; await load() }
async function activate(document: ReferenceDocument) { busy.value = true; error.value = ''; try { const result = await props.api.activate(document.id, !document.active); if (selected.value?.id === result.id) selected.value = result; await load() } catch (failure) { error.value = registryError(failure) } finally { busy.value = false } }
async function prepareDelete(document: ReferenceDocument) { deleteTarget.value = document; usages.value = null; deleteError.value = ''; try { const result = await props.api.usages(document.id); if (deleteTarget.value?.id === document.id) usages.value = result } catch (failure) { deleteError.value = registryError(failure) } }
async function confirmDelete() {
  const document = deleteTarget.value; const impact = usages.value; if (!document || !impact || busy.value) return
  busy.value = true; deleteError.value = ''
  try { await props.api.remove(document.id, impact.fingerprint); deleteTarget.value = null; if (selected.value && impact.document_ids.includes(selected.value.id)) emit('closeDocument'); await load() }
  catch (failure) { deleteError.value = registryError(failure); usages.value = null; try { usages.value = await props.api.usages(document.id) } catch { deleteError.value += ' Закройте окно и повторите проверку связей.' } }
  finally { busy.value = false }
}
watch(() => props.documentId, async id => { const token = ++detailGeneration; selected.value = null; detailError.value = ''; detailLoading.value = false; if (!id) return; if (!isUuid(id)) { detailError.value = 'Некорректная ссылка на документ.'; return } detailLoading.value = true; try { const result = await props.api.document(id); if (token === detailGeneration) selected.value = result } catch (failure) { if (token === detailGeneration) detailError.value = registryError(failure) } finally { if (token === detailGeneration) detailLoading.value = false } }, { immediate: true })
onMounted(async () => { await load(); try { marks.value = (await props.api.catalog()).items } catch (failure) { error.value = registryError(failure) } })
onBeforeUnmount(() => { clearTimeout(searchTimer); ++generation; ++detailGeneration; ++modelGeneration })
</script>
