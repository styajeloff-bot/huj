<template>
  <RegistryModal :title="heading" :busy="busy" wide @close="emit('close')">
    <form class="dr-form" @submit.prevent.stop="save">
      <p v-if="monetization" class="dr-notice">Документ сохранится в справочнике сразу. Отмена условий монетизации не удалит его.</p>
      <p v-if="groupId && mode === 'create'" class="dr-notice">Новый документ в существующей связке. Связанные компании наследуются по каждой незаполненной роли; показаны значения главного документа.</p>
      <p v-if="mode === 'edit'" class="dr-notice">Сохранение создаст новую версию. Предыдущие данные и файлы останутся в истории. Сохранённые файлы можно оставить, добавить или убрать из новой версии.</p>
      <div class="dr-grid dr-grid-three">
        <label>Тип документа<select v-model="draft.document_type" class="select-field" :disabled="mode === 'edit'" required><option v-for="item in types" :key="item.code" :value="item.code">{{ item.name }}</option></select></label>
        <label>Номер документа<input v-model="draft.contract_number" :disabled="mode === 'edit'" maxlength="100" required @blur="checkNumber" /><small>Номер нельзя изменить после сохранения.</small><small v-if="numberCheck === 'pending'" role="status">Проверяем номер…</small><small v-if="numberError" class="dr-error">{{ numberError }}</small><button v-if="numberCheck === 'error'" type="button" class="dr-link" @click="checkNumber">Повторить проверку номера</button></label>
        <label>Название<input v-model="draft.name" maxlength="255" required /></label>
      </div>
      <fieldset v-if="mode === 'create' && !groupId"><legend>Участники связки</legend>
        <RegistryCompaniesEditor :api="api" :model-value="participants" @update:model-value="updateParticipants" />
        <div class="dr-grid dr-grid-two"><label>Марка<select v-model="participants.mark_id" class="select-field" @change="loadModels(true)"><option :value="null">Все марки</option><option v-for="item in marks" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label>Модель<select v-model="participants.model_id" class="select-field" :disabled="!participants.mark_id"><option :value="null">Все модели</option><option v-for="item in models" :key="item.id" :value="item.id">{{ item.name }}</option></select></label></div>
        <small>Заполните хотя бы одного участника или марку. Состав связки после сохранения неизменяем.</small>
      </fieldset>
      <fieldset><legend>Связанные компании</legend><RegistryCompaniesEditor :model-value="related" :api="api" @update:model-value="updateRelated" /><small>Получат доступ к этому документу. В подборе условий используются участники связки.</small></fieldset>
      <div class="dr-grid dr-grid-two"><label>Действует с<input v-model="draft.valid_from" type="date" required /></label><label>Действует по<input v-model="draft.valid_to" type="date" :min="draft.valid_from" /><small>Пустое поле — бессрочно.</small></label></div>
      <label class="dr-upload">Файлы<input type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg" @change="chooseFiles" /><small>От 1 до 10 файлов, каждый до 20 МиБ. PDF, Word, Excel, PNG, JPEG.</small></label>
      <ul v-if="retainedFiles.length" class="dr-file-selection" aria-label="Сохранённые файлы"><li v-for="file in retainedFiles" :key="file.id">{{ file.name }} <small>{{ Math.ceil(file.size / 1024) }} КБ · Сохранённый файл</small><button type="button" :aria-label="'Убрать файл ' + file.name" @click="retainedFiles = retainedFiles.filter(item => item.id !== file.id)">×</button></li></ul>
      <ul v-if="files.length" class="dr-file-selection" aria-label="Новые файлы"><li v-for="(file, index) in files" :key="index">{{ file.name }} <small>{{ Math.ceil(file.size / 1024) }} КБ</small><button type="button" :aria-label="'Убрать файл ' + file.name" @click="files.splice(index, 1)">×</button></li></ul>
      <p v-if="error" class="dr-error" role="alert">{{ error }}</p>
      <footer class="dr-actions"><button type="button" class="dr-secondary" :disabled="busy" @click="emit('close')">Отмена</button><button type="submit" class="dr-primary" :disabled="busy || (mode === 'create' && numberCheck !== 'available')">{{ busy ? 'Сохранение…' : 'Сохранить документ' }}</button></footer>
    </form>
  </RegistryModal>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { DocumentRegistryApi } from '../api'
import { registryError } from '../api'
import { companyPayload, emptyCompanies, emptyParticipants, type CatalogItem, type CompanySelection, type Participants, type ReferenceDocument, type RegistryFile, type RegistryType } from '../types'
import RegistryModal from './RegistryModal.vue'
import RegistryCompaniesEditor from './RegistryCompaniesEditor.vue'
const props = withDefaults(defineProps<{ api: DocumentRegistryApi; mode?: 'create' | 'edit'; document?: ReferenceDocument; groupId?: string; preset?: Participants; inherited?: CompanySelection; monetization?: boolean }>(), { mode: 'create' })
const emit = defineEmits<{ close: []; saved: [document: ReferenceDocument] }>()
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const participants = ref<Participants>(copy(props.preset ?? emptyParticipants()))
const related = ref<CompanySelection>(copy(props.document?.related_companies ?? props.inherited ?? emptyCompanies()))
const draft = reactive({ document_type: props.document?.document_type ?? 'contract', contract_number: props.document?.contract_number ?? '', name: props.document?.name ?? '', valid_from: props.document?.current_version.valid_from ?? '', valid_to: props.document?.current_version.valid_to ?? '' })
const types = ref<RegistryType[]>([]); const marks = ref<CatalogItem[]>([]); const models = ref<CatalogItem[]>([])
const retainedFiles = ref<RegistryFile[]>(props.mode === 'edit' ? [...(props.document?.current_version.files ?? [])] : [])
const files = ref<File[]>([]); const busy = ref(false); const error = ref(''); const numberError = ref('')
const numberCheck = ref<'idle' | 'pending' | 'available' | 'taken' | 'error'>('idle')
let numberGeneration = 0
let numberPromise: Promise<boolean> | null = null
let checkedNumber = ''
const heading = computed(() => props.mode === 'edit' ? 'Редактировать документ' : 'Добавить документ')
function updateParticipants(value: CompanySelection) { participants.value = { ...participants.value, ...value } }
function updateRelated(value: CompanySelection) {
  if (props.mode === 'create' && props.groupId && props.inherited) {
    const inherited = props.inherited
    for (const [key, role] of [['leasing_company_ids', 'leasing_company'], ['dealer_company_ids', 'dealer'], ['distributor_company_ids', 'distributor']] as const) if (!value[key].length) {
      value[key] = [...inherited[key]]
      value.companies = [...(value.companies ?? []).filter(item => item.role !== role), ...(inherited.companies ?? []).filter(item => item.role === role)]
    }
  }
  related.value = value
}
async function loadModels(reset = false) {
  if (reset) participants.value.model_id = null
  const id = participants.value.mark_id; models.value = []
  if (!id) return
  try { const result = await props.api.catalog(id); if (id === participants.value.mark_id) models.value = result.items } catch (failure) { error.value = registryError(failure) }
}
function chooseFiles(event: Event) { const input = event.target as HTMLInputElement; files.value.push(...Array.from(input.files ?? [])); input.value = '' }
async function checkNumber(): Promise<boolean> {
  if (props.mode !== 'create') return true
  const number = draft.contract_number
  if (!number.trim()) return false
  if (checkedNumber === number) {
    if (numberCheck.value === 'available') return true
    if (numberCheck.value === 'taken') return false
    if (numberPromise) return numberPromise
  }
  const token = ++numberGeneration
  checkedNumber = number
  numberCheck.value = 'pending'; numberError.value = ''
  numberPromise = (async () => {
    try {
      const result = await props.api.checkNumber(number)
      if (token !== numberGeneration || draft.contract_number !== number) return false
      numberCheck.value = result.available ? 'available' : 'taken'
      numberError.value = result.available ? '' : 'Номер используется'
      return result.available
    } catch (failure) {
      if (token === numberGeneration) {
        numberCheck.value = 'error'; numberError.value = registryError(failure)
      }
      return false
    } finally {
      if (token === numberGeneration) numberPromise = null
    }
  })()
  return numberPromise
}
watch(() => draft.contract_number, () => {
  ++numberGeneration; checkedNumber = ''; numberPromise = null
  numberCheck.value = 'idle'; numberError.value = ''
}, { flush: 'sync' })
onBeforeUnmount(() => { ++numberGeneration })
async function save() {
  if (busy.value || !await checkNumber() || busy.value) return
  error.value = ''
  if (retainedFiles.value.length + files.value.length < 1 || retainedFiles.value.length + files.value.length > 10 || files.value.some(file => !file.size || file.size > 20 * 1024 * 1024 || !/\.(pdf|docx?|xlsx?|png|jpe?g)$/i.test(file.name))) { error.value = 'Выберите от 1 до 10 непустых файлов разрешённых форматов, до 20 МиБ каждый.'; return }
  if (draft.valid_to && draft.valid_to < draft.valid_from) { error.value = 'Окончание не может быть раньше начала.'; return }
  const p = participants.value
  if (props.mode === 'create' && !props.groupId && !p.platform_ml && !p.mark_id && !p.leasing_company_ids.length && !p.dealer_company_ids.length && !p.distributor_company_ids.length) { error.value = 'Укажите участников или марку связки.'; return }
  busy.value = true
  try {
    let result: ReferenceDocument
    if (props.mode === 'edit' && props.document) result = await props.api.newVersion(props.document.id, { expected_current_version_id: props.document.current_version.id, name: draft.name.trim(), related_companies: companyPayload(related.value), valid_from: draft.valid_from, valid_to: draft.valid_to || null, retained_file_ids: retainedFiles.value.map(file => file.id) }, files.value)
    else result = await props.api.create({ ...draft, name: draft.name.trim(), valid_to: draft.valid_to || null, related_companies: companyPayload(related.value), ...(!props.groupId ? { participants: { ...companyPayload(p), mark_id: p.mark_id, model_id: p.model_id } } : {}) }, files.value, props.groupId)
    emit('saved', result)
  } catch (failure) { error.value = registryError(failure) } finally { busy.value = false }
}
onMounted(async () => {
  try { const [typeResult, markResult] = await Promise.all([props.api.types(), props.api.catalog()]); types.value = typeResult.items; marks.value = markResult.items; await loadModels() }
  catch (failure) { error.value = registryError(failure) }
})
</script>
