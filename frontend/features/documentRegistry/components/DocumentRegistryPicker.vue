<template>
  <section class="dr-picker">
    <div class="contract-heading">
      <h3>{{ canManage ? 'Приложить договор' : 'Документы из справочника' }}</h3>
      <span v-if="loading" class="dr-meta" role="status">Загрузка…</span>
    </div>
    <p v-if="error" class="dr-error" role="alert">{{ error }}</p>
    <p v-if="selectionNotice" class="dr-notice" role="status">{{ selectionNotice }}</p>
    <nav v-if="canManage" class="workspace-tabs" aria-label="Приложить договор" role="tablist">
      <button
        :id="`${tabId}-registry-tab`" ref="registryTab" type="button" role="tab"
        :aria-controls="`${tabId}-registry-panel`" :aria-selected="activeTab === 'registry'"
        :tabindex="activeTab === 'registry' ? 0 : -1"
        @click="selectTab('registry')" @keydown="handleTabKeydown($event, 'registry')"
      >Из справочника документов</button>
      <button
        :id="`${tabId}-upload-tab`" ref="uploadTab" type="button" role="tab"
        :aria-controls="`${tabId}-upload-panel`" :aria-selected="activeTab === 'upload'"
        :tabindex="activeTab === 'upload' ? 0 : -1"
        @click="selectTab('upload')" @keydown="handleTabKeydown($event, 'upload')"
      >Загрузить новый файл</button>
    </nav>
    <div
      v-show="!canManage || activeTab === 'registry'" :id="`${tabId}-registry-panel`"
      :role="canManage ? 'tabpanel' : undefined" :aria-labelledby="canManage ? `${tabId}-registry-tab` : undefined"
      :tabindex="canManage ? 0 : undefined"
    >
      <p v-if="canManage" class="contract-hint">
        {{ canSelect ? 'Для подбора достаточно одного совпадения: ЛК, дилера, дистрибьютора, марки, модели или участия Платформы МЛ.' : 'Выберите лизинговую компанию для подбора и загрузки документов.' }}
      </p>
      <p v-if="candidatesLoading" class="dr-meta" role="status">Подбор документов…</p>
      <div v-if="candidateError" class="dr-error" role="alert">
        {{ candidateError }}
        <button type="button" class="dr-link" :disabled="candidatesLoading" @click="loadCandidates">Повторить подбор</button>
      </div>
      <div class="contract-list">
        <div
          v-for="document in visibleDocuments" :key="document.id" class="contract-row"
          :class="{ 'contract-row-selected': canManage && selectedIds.includes(document.id), 'contract-row-readonly': !canManage }"
          :data-document-id="document.id" :data-selected="selectedIds.includes(document.id)"
        >
          <input
            v-if="canManage" type="checkbox" class="contract-checkbox" :checked="selectedIds.includes(document.id)"
            :aria-label="'Выбрать ' + document.name" :disabled="loading || saving || (candidatesLoading && !savedIds.includes(document.id))"
            @change="toggleDocument(document.id)"
          />
          <div class="contract-details">
            <div class="contract-title">
              <span class="contract-type">{{ typeLabels[document.document_type] }}</span>
              <NuxtLink :to="documentLink(document.id)" target="_blank" rel="noopener">{{ document.name }} №{{ document.contract_number }}</NuxtLink>
            </div>
            <p class="contract-period">
              {{ dateLabel(document.current_version.valid_from) }} → {{ dateLabel(document.current_version.valid_to) }} · Версия {{ document.current_version.version_number }}
              <span v-if="document.status !== 'active'" class="dr-status" :class="document.status">{{ statusLabels[document.status] }}</span>
            </p>
          </div>
          <div class="contract-files">
            <button v-for="file in document.current_version.files" :key="file.id" type="button" class="dr-file" @click="download(file)">{{ file.name }}</button>
            <button v-if="document.version_count > 1" type="button" class="dr-link" @click="history = document">История версий</button>
          </div>
        </div>
      </div>
      <p v-if="!loading && !candidatesLoading && !candidateError && !visibleDocuments.length" class="contract-hint">
        {{ canManage && canSelect ? 'Нет документов, подходящих участникам и автомобилю условия.' : 'Документы не выбраны.' }}
      </p>
      <template v-if="canManage && canSelect">
        <p class="contract-hint">Не тот документ? Переключитесь на «Загрузить новый файл» — он попадёт в справочник по этой привязке.</p>
        <p class="contract-hint">Будущие договоры доступны для выбора. Истёкшие и деактивированные сохраняются в уже созданных связях.</p>
      </template>
    </div>
    <div
      v-if="canManage" v-show="activeTab === 'upload'" :id="`${tabId}-upload-panel`" role="tabpanel"
      :aria-labelledby="`${tabId}-upload-tab`" tabindex="0" class="contract-upload"
    >
      <p class="contract-hint">{{ canSelect ? 'Загрузите документ в подходящую или новую связку. После сохранения подходящий документ будет выбран для этого условия.' : 'Выберите лизинговую компанию для подбора и загрузки документов.' }}</p>
      <button type="button" class="dr-secondary" :disabled="!canSelect || loading || saving" @click="openUpload">Загрузить документ</button>
      <p class="contract-hint">Загруженный документ останется в справочнике, даже если вы отмените создание или изменение условий.</p>
    </div>
    <div v-if="canManage && programId && dirty" class="dr-actions">
      <button type="button" class="dr-secondary" :disabled="saving" @click="resetSelection">Отменить изменения</button>
      <button type="button" class="dr-primary" :disabled="saving" @click="saveLinks">{{ saving ? 'Сохранение…' : 'Сохранить связи' }}</button>
    </div>
    <RegistryModal v-if="uploadChoice" title="Загрузить документ" @close="uploadChoice = false">
      <div class="dr-upload-choice">
        <p class="dr-notice">После загрузки документ останется в справочнике, даже если вы отмените создание или изменение условий.</p>
        <label>Связка<select v-model="uploadGroupId" class="select-field"><option value="">Создать новую связку с участниками условия</option><option v-for="group in availableGroups" :key="group.id" :value="group.id">{{ group.label }}</option></select></label>
        <p v-if="candidateError" class="dr-error" role="alert">{{ candidateError }}</p>
        <footer class="dr-actions"><button type="button" class="dr-secondary" @click="uploadChoice = false">Отмена</button><button type="button" class="dr-primary" :disabled="candidatesLoading || preparingUpload" @click="prepareUpload">{{ preparingUpload ? 'Подготовка…' : 'Продолжить' }}</button></footer>
      </div>
    </RegistryModal>
    <RegistryDocumentForm v-if="uploadForm" :api="api" :preset="uploadPreset" :group-id="uploadGroupId || undefined" :inherited="inherited" monetization @close="uploadForm = false" @saved="uploaded" />
    <RegistryHistory v-if="history" :api="api" :document="history" :can-manage="canManage" @changed="versionChanged" @close="history = null" />
  </section>
</template>

<script setup lang="ts">
import '~/assets/css/workspace-tabs.css'
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import { createDocumentRegistryApi, registryError } from '../api'
import { dateLabel, emptyParticipants, statusLabels, typeLabels, type CompanySelection, type DocumentGroup, type MonetizationDocumentContext, type Participants, type ReferenceDocument, type RegistryFile } from '../types'
import RegistryModal from './RegistryModal.vue'
import RegistryDocumentForm from './RegistryDocumentForm.vue'
import RegistryHistory from './RegistryHistory.vue'
import '../registry.css'

const props = withDefaults(defineProps<{ modelValue?: string[]; programId?: string; context?: MonetizationDocumentContext; preset?: Participants; catalogNames?: { mark: string | null; model: string | null }; canManage?: boolean }>(), { modelValue: () => [], canManage: true })
const emit = defineEmits<{ 'update:modelValue': [ids: string[]]; changed: [] }>()
const route = useRoute()
const api = createDocumentRegistryApi(useRuntimeConfig(), () => route.query.notification_company_id)
const documentLink = (id: string) => ({ path: '/workspace/document-registry', query: { notification_company_id: route.query.notification_company_id, document: id } })
const tabId = useId()
const activeTab = ref<'registry' | 'upload'>('registry')
const registryTab = ref<HTMLButtonElement | null>(null)
const uploadTab = ref<HTMLButtonElement | null>(null)
const selectedIds = ref<string[]>([...props.modelValue])
const knownDocuments = ref<ReferenceDocument[]>([])
const savedIds = ref<string[]>([])
const selectedDocuments = computed(() => selectedIds.value.map(id => knownDocuments.value.find(item => item.id === id)).filter((item): item is ReferenceDocument => !!item))
const dirty = computed(() => [...selectedIds.value].sort().join(',') !== [...savedIds.value].sort().join(','))
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const selectionNotice = ref('')
let generation = 0
let candidateGeneration = 0
const candidateGroups = ref<DocumentGroup[]>([])
const candidates = ref<ReferenceDocument[]>([])
const candidatesLoading = ref(false)
const candidateError = ref('')
const uploadChoice = ref(false)
const uploadForm = ref(false)
const preparingUpload = ref(false)
const uploadGroupId = ref('')
const uploadPreset = ref<Participants>(emptyParticipants())
const inherited = ref<CompanySelection | undefined>()
const history = ref<ReferenceDocument | null>(null)
const contextKey = computed(() => JSON.stringify([
  props.context?.leasing_company_id ?? null,
  props.context?.dealer_company_id ?? null,
  props.context?.distributor_company_id ?? null,
  props.context?.mark_id ?? null,
  props.context?.model_id ?? null,
  props.context?.platform_ml ?? false,
]))
const canSelect = computed(() => !!(props.programId || props.context?.leasing_company_id))
const availableGroups = computed(() => candidateGroups.value.map(group => ({ id: group.group_id, label: 'Связка: ' + group.display_document.name + ' №' + group.display_document.contract_number })))
const visibleDocuments = computed(() => {
  if (!props.canManage) return selectedDocuments.value
  // Existing links remain selectable even when their document is no longer a candidate.
  const documents = [...candidates.value, ...knownDocuments.value.filter(item => savedIds.value.includes(item.id)), ...selectedDocuments.value]
  return [...new Map(documents.map(document => [document.id, document])).values()]
})

function selectTab(tab: 'registry' | 'upload', focus = false) {
  activeTab.value = tab
  if (focus) (tab === 'registry' ? registryTab.value : uploadTab.value)?.focus()
}
function handleTabKeydown(event: KeyboardEvent, tab: 'registry' | 'upload') {
  let next: 'registry' | 'upload'
  if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') next = tab === 'registry' ? 'upload' : 'registry'
  else if (event.key === 'Home') next = 'registry'
  else if (event.key === 'End') next = 'upload'
  else return
  event.preventDefault()
  selectTab(next, true)
}
function remember(documents: ReferenceDocument[]) {
  const byId = new Map(knownDocuments.value.map(item => [item.id, item]))
  documents.forEach(item => byId.set(item.id, item))
  knownDocuments.value = [...byId.values()]
}
function change(ids: string[]) { selectedIds.value = [...new Set(ids)]; emit('update:modelValue', selectedIds.value) }
function toggleDocument(id: string) { change(selectedIds.value.includes(id) ? selectedIds.value.filter(value => value !== id) : [...selectedIds.value, id]) }
function resetSelection() { change([...savedIds.value]) }
async function loadCandidates() {
  const token = ++candidateGeneration
  candidates.value = []
  candidateGroups.value = []
  candidateError.value = ''
  candidatesLoading.value = false
  const context = props.context
  if (!props.canManage || (!props.programId && !context?.leasing_company_id)) return false
  candidatesLoading.value = true
  try {
    const result = await api.candidates(props.programId ? { program_id: props.programId } : { context: context! })
    if (token === candidateGeneration) {
      candidates.value = result.items; candidateGroups.value = result.groups; remember(result.items)
      const allowed = new Set([...result.items.map(item => item.id), ...savedIds.value])
      const retained = selectedIds.value.filter(id => allowed.has(id))
      if (retained.length !== selectedIds.value.length) {
        change(retained); selectionNotice.value = 'Выбор обновлён: некоторые документы больше не подходят к условиям.'
      }
      return true
    }
  } catch (failure) {
    if (token === candidateGeneration) candidateError.value = registryError(failure)
  } finally {
    if (token === candidateGeneration) candidatesLoading.value = false
  }
}
async function openUpload() { uploadGroupId.value = ''; uploadChoice.value = true; await loadCandidates() }
async function prepareUpload() {
  preparingUpload.value = true; candidateError.value = ''; inherited.value = undefined
  try {
    uploadPreset.value = JSON.parse(JSON.stringify(props.preset ?? emptyParticipants()))
    if (!props.preset && props.context) {
      uploadPreset.value.leasing_company_ids = [props.context.leasing_company_id]
      uploadPreset.value.dealer_company_ids = props.context.dealer_company_id ? [props.context.dealer_company_id] : []
      uploadPreset.value.distributor_company_ids = props.context.distributor_company_id ? [props.context.distributor_company_id] : []
      uploadPreset.value.platform_ml = props.context.platform_ml
      uploadPreset.value.mark_id = props.context.mark_id ?? null
      uploadPreset.value.model_id = props.context.model_id ?? null
    }
    if (uploadGroupId.value) {
      const main = candidateGroups.value.find(group => group.group_id === uploadGroupId.value)?.main_document
      if (!main) throw new Error('Основной документ связки недоступен. Обновите подбор.')
      inherited.value = main.related_companies
    } else if (props.catalogNames?.mark) {
      const marks = (await api.catalog()).items.filter(item => item.name === props.catalogNames!.mark)
      if (marks.length !== 1) { candidateError.value = 'Нужно уточнить марку условия: точное соответствие в каталоге не найдено.'; return }
      uploadPreset.value.mark_id = marks[0]!.id
      if (props.catalogNames.model) {
        const models = (await api.catalog(marks[0]!.id)).items.filter(item => item.name === props.catalogNames!.model)
        if (models.length !== 1) { candidateError.value = 'Нужно уточнить модель условия: точное соответствие в каталоге не найдено.'; return }
        uploadPreset.value.model_id = models[0]!.id
      }
    }
    uploadChoice.value = false; uploadForm.value = true
  } catch (failure) {
    candidateError.value = failure instanceof Error && !('data' in failure) ? failure.message : registryError(failure)
  } finally { preparingUpload.value = false }
}
async function uploaded(document: ReferenceDocument) {
  remember([document]); uploadForm.value = false
  selectTab('registry', true)
  const checked = await loadCandidates()
  if (checked && candidates.value.some(item => item.id === document.id)) {
    change([...selectedIds.value, document.id]); selectionNotice.value = ''
  } else {
    selectionNotice.value = candidateError.value
      ? 'Документ сохранён в справочнике. Повторите подбор, чтобы проверить возможность его выбора.'
      : 'Документ сохранён в справочнике, но не подходит к условиям и не выбран. Проверьте его сроки и участников.'
  }
}
async function versionChanged(document: ReferenceDocument) {
  remember([document]); history.value = document; emit('changed')
  await loadCandidates()
}
async function saveLinks() {
  if (!props.programId || saving.value) return
  saving.value = true; error.value = ''
  try {
    const result = await api.setProgramDocuments(props.programId, selectedIds.value)
    remember(result.items); savedIds.value = result.items.map(item => item.id); change([...savedIds.value]); emit('changed')
  } catch (failure) { error.value = registryError(failure) }
  finally { saving.value = false }
}
async function download(file: RegistryFile) { try { await api.download(file) } catch (failure) { error.value = registryError(failure) } }
watch(() => [props.programId, route.query.notification_company_id] as const, async ([id]) => {
  const token = ++generation
  loading.value = false; error.value = ''; savedIds.value = []; knownDocuments.value = []
  selectedIds.value = id ? [] : [...props.modelValue]
  if (!id) return
  loading.value = true
  try {
    const result = await api.programDocuments(id)
    if (token === generation) { remember(result.items); savedIds.value = result.items.map(item => item.id); change([...savedIds.value]) }
  } catch (failure) { if (token === generation) error.value = registryError(failure) }
  finally { if (token === generation) loading.value = false }
}, { immediate: true })
watch(contextKey, () => {
  if (!props.programId && selectedIds.value.length) {
    change([]); selectionNotice.value = 'Участники или транспорт изменены. Выберите подходящие документы для новых условий.'
  }
})
watch(() => props.modelValue, ids => { if (!props.programId) selectedIds.value = [...ids] })
watch([() => props.programId, contextKey, () => props.canManage, () => route.query.notification_company_id], () => { void loadCandidates() }, { immediate: true })
onBeforeUnmount(() => { ++generation; ++candidateGeneration })
</script>

<style scoped>
.contract-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.contract-heading h3 { color: #6b7280; font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.contract-hint { margin: 12px 0; color: #6b7280; font-size: 12px; line-height: 1.5; }
.contract-list { display: grid; gap: 10px; }
.contract-row { display: grid; grid-template-columns: 18px minmax(0, 1fr) minmax(100px, auto); align-items: center; gap: 14px; padding: 16px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; }
.contract-row-selected { border-color: #93c5fd; background: #eff6ff; }
.contract-row-readonly { grid-template-columns: minmax(0, 1fr) minmax(100px, auto); }
.contract-checkbox { width: 16px; height: 16px; accent-color: #2563eb; cursor: pointer; }
.contract-details { min-width: 0; }
.contract-title { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-weight: 600; line-height: 1.5; }
.contract-title a { overflow-wrap: anywhere; color: #111827; }
.contract-title a:hover { color: #2563eb; text-decoration: underline; }
.contract-type { padding: 2px 8px; border-radius: 6px; color: #374151; background: #f3f4f6; font-size: 12px; font-weight: 500; }
.contract-period { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 6px 0 0; color: #6b7280; font-size: 12px; line-height: 1.5; }
.contract-files { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; max-width: 320px; }
.contract-files .dr-file { max-width: 100%; overflow-wrap: anywhere; text-align: left; }
.contract-files .dr-link { font-size: 12px; }
.contract-upload { padding-bottom: 4px; }
@media (min-width: 768px) and (max-width: 1100px) {
  .contract-row { grid-template-columns: 18px minmax(0, 1fr); }
  .contract-row-readonly { grid-template-columns: minmax(0, 1fr); }
  .contract-files { grid-column: 2; max-width: none; justify-content: flex-start; }
  .contract-row-readonly .contract-files { grid-column: 1; }
}
</style>
