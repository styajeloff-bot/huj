<template>
  <form class="program-editor" @submit.prevent="save">
    <header class="program-editor-heading"><button type="button" class="back-button" aria-label="К списку условий" @click="$emit('cancel')">←</button><h2>Создание условий монетизации</h2></header><div class="program-editor-body">
    <p class="muted program-intro">Выберите участников и источники заявки. В каждой связке распределите расход одного плательщика между получателями дохода.</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="program-details">
      <label><span>Название *</span><input class="input-field" v-model="draft.name" required maxlength="255" placeholder="Например, «Базовые условия по легковым»" /></label>
      <div class="program-grid program-grid-three">
        <CompanyPicker v-model="leasing" :api="api" kind="leasing" label="Лизинговая компания *" placeholder="Выбрать ЛК" />
        <CompanyPicker v-model="distributor" :api="api" kind="distributor" :dealer-company-id="dealer?.id" label="Дистрибьютор (опционально)" placeholder="Любой дистрибьютор" />
        <CompanyPicker v-model="dealer" :api="api" kind="dealer" :distributor-company-id="distributor?.id" label="Дилер (опционально)" placeholder="Любой дилер" />
      </div>
      <div class="program-grid program-grid-two">
        <div>
          <SearchableDropdown :anchor-to-control="true" :model-value="draft.support_program_id" :items="supportOptions" label="Программа стимулирования (опционально)" placeholder="Не выбрана" clear-label="Не выбрана" label-key="name" value-key="id" search-placeholder="Найти программу..." :remote="true" :loading="supportsLoading" :disabled="hasExchange" :empty-label="distributor ? 'У дистрибьютора нет доступных программ' : 'Нет доступных программ'" :error="!!supportSearchError" @search="findSupports" @update:model-value="selectSupport" />
          <p v-if="supportsLoading" class="muted" role="status">Загрузка программ…</p>
          <p v-if="supportSearchError" class="error" role="alert">{{ supportSearchError }}</p>
          <p v-if="hasExchange" class="notice">Для условий с источником «Биржа ТС» программа стимулирования не применяется.</p>
        </div>
        <div v-if="selectedSupport && !hasExchange">
          <p class="field-label">Совместимые программы</p><p class="muted">Справочно, не влияют на подбор условий.</p>

          <div v-if="support?.compatible_programs.length" class="compatibility-tags"><span v-for="item in support.compatible_programs" :key="item.id" class="badge">{{ item.name }}</span></div>
          <p v-else-if="!supportLoading" class="muted">Совместимость не задана.</p>
        </div>
      </div>
      <div v-if="selectedSupport && !hasExchange">
        <p class="field-label">Документы программы стимулирования (только просмотр)</p>
        <p v-if="supportLoading" class="muted" role="status">Загрузка документов и совместимых программ…</p>
        <p v-if="supportDetailError" class="error" role="alert">{{ supportDetailError }} <button type="button" class="link" @click="loadSupport">Повторить</button></p>
        <FileList v-if="support" :files="support.documents" :api="api" />
        <p v-if="support && !support.documents.length" class="muted">У выбранной программы стимулирования нет загруженных документов.</p>
      </div>
      <div>


        <div class="program-grid program-grid-five">
          <CatalogMarkPicker :model-value="mark" :api="api" @update:model-value="selectMark" />
          <SearchableDropdown :anchor-to-control="true" :model-value="modelId" :items="modelOptions" label="Модель" placeholder="Все модели" clear-label="Все модели" label-key="name" value-key="id" search-placeholder="Найти модель..." :loading="modelsLoading" :disabled="!mark || modelsLoading" :error="!!modelsError" @update:model-value="selectModel" />
          <SearchableDropdown :anchor-to-control="true" :model-value="modificationId" :items="modificationOptions" label="Модификация" placeholder="Все модификации" clear-label="Все модификации" label-key="name" value-key="id" search-placeholder="Найти модификацию..." :loading="modificationsLoading" :disabled="!modelId || modificationsLoading" :error="!!modificationsError" @update:model-value="selectModification" />
          <SearchableDropdown :anchor-to-control="true" :model-value="trimId" :items="trimOptions" label="Комплектация" placeholder="Все комплектации" clear-label="Все комплектации" label-key="trim_name" value-key="id" search-placeholder="Найти комплектацию..." :loading="trimsLoading" :disabled="!modificationId || trimsLoading" :error="!!trimsError" @update:model-value="selectTrim" />
          <label><span>VIN</span><input class="input-field" v-model="draft.vin" maxlength="17" placeholder="VIN (разовые условия)" /></label>
        </div>
        <p class="muted">Марка, модель, модификация, комплектация и VIN необязательны — они сужают условия до точного совпадения.</p>
        <p v-if="modelsLoading || modificationsLoading || trimsLoading" class="muted" role="status">Загрузка {{ modelsLoading ? 'моделей' : modificationsLoading ? 'модификаций' : 'комплектаций' }}…</p>
        <p v-if="modelsError" class="error" role="alert">{{ modelsError }} <button type="button" class="link" @click="loadModels">Повторить</button></p>
        <p v-if="modificationsError" class="error" role="alert">{{ modificationsError }} <button type="button" class="link" @click="loadModifications">Повторить</button></p>
        <p v-if="trimsError" class="error" role="alert">{{ trimsError }} <button type="button" class="link" @click="loadTrims">Повторить</button></p>
        <p v-if="draft.vin" class="notice">Указан VIN — условия разовые, действуют только на одну сделку с этим VIN.</p>
      </div>
      <div class="program-grid program-grid-three">
        <label><span>Дата начала *</span><input class="input-field" v-model="draft.period_start" type="date" required /></label>
        <label><span>Дата окончания</span><input class="input-field" v-model="draft.period_end" type="date" :min="draft.period_start" /><small class="muted">Пустое поле — бессрочно</small></label>
        <fieldset class="status-field"><legend class="field-label">Статус</legend><div class="status-options"><label><input v-model="draft.status" type="radio" value="active" /> Активна</label><label><input v-model="draft.status" type="radio" value="inactive" /> Неактивна</label></div></fieldset>
      </div>
    </div>
    <h3 class="sources-heading">Источники заявки и расчёт</h3>
    <p class="muted sources-intro">Каждый источник содержит свои связки. Каждая связка — один плательщик и его получатели дохода.</p>
    <section v-for="block in draft.sources" :key="block.local_id" class="source-card">
      <label class="source-field"><span>Источник заявки</span><select class="select-field" v-model="block.source_type"><optgroup label="Заявки"><option v-for="option in applicationSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option></optgroup><optgroup :label="fastDealOriginLabel"><option v-for="option in fastDealSourceOptions" :key="option.value" :value="option.value">{{ option.label }}</option></optgroup></select></label>
      <div v-for="(pair, pairIndex) in block.pairs" :key="pair.local_id" class="condition-pair">
        <div class="pair-heading"><h4>Связка #{{ pairIndex + 1 }}</h4><button v-if="block.pairs.length > 1" type="button" class="remove-link" @click="block.pairs.splice(pairIndex, 1)">Удалить связку</button></div>
        <div class="condition-columns">
          <ConditionRowEditor :model-value="pair.expense" :income="false" @update:model-value="updateExpense(pair, $event)" />
          <div class="pair-incomes">
            <section v-for="(income, incomeIndex) in pair.incomes" :key="income.local_id" class="pair-income">
              <div class="pair-heading"><h4>Получатель #{{ incomeIndex + 1 }}</h4><button type="button" class="remove-link" :aria-label="'Удалить доход ' + (incomeIndex + 1) + ' из связки ' + (pairIndex + 1)" @click="pair.incomes.splice(incomeIndex, 1)">Удалить доход</button></div>
              <ConditionRowEditor :model-value="income" :income="true" :expense="pair.expense" @update:model-value="updateIncome(pair, incomeIndex, $event)" />
            </section>
            <p v-if="!pair.incomes.length" class="muted">Доходы не добавлены. Расход можно сохранить без получателей.</p>
            <button type="button" class="link add-income" :disabled="pairBudget(pair).exhausted" @click="addIncome(pair)">+ Добавить доход</button>
            <p v-if="pairBudget(pair).exhausted" class="muted">Расход полностью распределён. Чтобы добавить доход, уменьшите другой доход или увеличьте расход.</p>
          </div>
        </div>
        <p v-if="budgetMessages[pair.local_id]" class="notice" role="status">{{ budgetMessages[pair.local_id] }}</p>
        <p v-if="pairBudget(pair).error" class="error" role="alert">{{ pairBudget(pair).error }}</p>
        <p v-else-if="pairBudget(pair).deferred" class="muted budget-deferred">Для этого сочетания баз, сумм или ограничений окончательная проверка доходов выполняется при расчёте сделки по фактической стоимости имущества.</p>
      </div>
      <button type="button" class="link add-pair" @click="block.pairs.push(newPair(id(), id(), id()))">+ Добавить связку</button>
    </section>
    <button type="button" class="link add-pair" @click="draft.sources.push(newPairedBlock(id(), id(), id(), id()))">+ Добавить источник</button>
    <section class="program-contracts"><DocumentRegistryPicker v-model="referenceDocumentIds" :context="documentContext" :preset="documentParticipants" /></section>
    <footer class="program-actions"><button type="button" class="btn-secondary" :disabled="saving" @click="$emit('cancel')">Отмена</button><button type="submit" class="btn-primary" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить условия' }}</button></footer>
    </div>
  </form>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
import type { CatalogMark, CatalogModel, CatalogModification, CatalogTrim, Company, ConditionPair, ConditionRow, Program, ProgramDraft, ProgramEditorDraft, Support } from '../types'
import { newPair, newPairedBlock, newRow, sourceOptions, toProgramDraft, validateDraft } from '../editor'
import { fastDealOriginLabel, isFastDealSource } from '../dealSource'
import { capPairIncomes, pairBudget } from '../budget'
import CatalogMarkPicker from './CatalogMarkPicker.vue'
import CompanyPicker from './CompanyPicker.vue'
import ConditionRowEditor from './ConditionRowEditor.vue'
import FileList from './FileList.vue'
import { DocumentRegistryPicker, type MonetizationDocumentContext, type Participants } from '~/features/documentRegistry'
const props = defineProps<{ api: MonetizationApi }>()
const emit = defineEmits<{ cancel: []; saved: [program: Program] }>()
const applicationSourceOptions = sourceOptions.filter(option => !isFastDealSource(option.value))
const fastDealSourceOptions = sourceOptions.filter(option => isFastDealSource(option.value))
let sequence = 0
const id = () => `row-${++sequence}`
const draft = reactive<ProgramEditorDraft>({ name: '', leasing_company_id: null, dealer_company_id: null, distributor_company_id: null, support_program_id: null, brand: null, model: null, modification: null, trim: null, vin: null, period_start: '', period_end: null, status: 'active', sources: [newPairedBlock(id(), id(), id(), id())] })
const leasing = ref<Company | null>(null)
const dealer = ref<Company | null>(null)
const distributor = ref<Company | null>(null)
const referenceDocumentIds = ref<string[]>([])
const documentContext = computed<MonetizationDocumentContext | undefined>(() => leasing.value ? { leasing_company_id: leasing.value.id, dealer_company_id: dealer.value?.id ?? null, distributor_company_id: distributor.value?.id ?? null, mark_id: mark.value?.id ?? null, model_id: modelId.value, platform_ml: draft.sources.some(block => block.pairs.some(pair => pair.expense.participant_type === 'platform' || pair.incomes.some(row => row.participant_type === 'platform'))) } : undefined)
const documentParticipants = computed<Participants>(() => ({ platform_ml: documentContext.value?.platform_ml ?? false, leasing_company_ids: leasing.value ? [leasing.value.id] : [], dealer_company_ids: dealer.value ? [dealer.value.id] : [], distributor_company_ids: distributor.value ? [distributor.value.id] : [], mark_id: mark.value?.id ?? null, model_id: modelId.value, companies: [ ...(dealer.value ? [{ company_id: dealer.value.id, leasing_company_id: null, role: 'dealer' as const, name: dealer.value.name, inn: dealer.value.inn }] : []), ...(distributor.value ? [{ company_id: distributor.value.id, leasing_company_id: null, role: 'distributor' as const, name: distributor.value.name, inn: distributor.value.inn }] : [])] }))
const saving = ref(false)
const error = ref('')
const budgetMessages = reactive<Record<string, string>>({})
function applyBudget(pair: ConditionPair, editedId?: string) {
  budgetMessages[pair.local_id] = capPairIncomes(pair, editedId)
    ? 'Доход ограничен доступным остатком расхода. Проверьте распределение; строки с нулём нужно удалить или изменить.' : ''
}
function updateExpense(pair: ConditionPair, row: ConditionRow) {
  pair.expense = row
  applyBudget(pair)
}
function updateIncome(pair: ConditionPair, index: number, row: ConditionRow) {
  pair.incomes[index] = { ...row, expense_ref: pair.expense.local_id }
  applyBudget(pair, row.local_id)
}
function addIncome(pair: ConditionPair) {
  if (pairBudget(pair).exhausted) return
  pair.incomes.push({ ...newRow(id()), participant_type: 'dealer', expense_ref: pair.expense.local_id })
  budgetMessages[pair.local_id] = ''
}
const supports = ref<Pick<Support, 'id' | 'name'>[]>([])
const selectedSupport = ref<Pick<Support, 'id' | 'name'> | null>(null)
const support = ref<Support | null>(null)
const supportsLoading = ref(false)
const supportLoading = ref(false)
const supportSearchError = ref('')
const supportDetailError = ref('')
const supportOptions = computed(() => {
  const items = selectedSupport.value && !supports.value.some(item => item.id === selectedSupport.value?.id) ? [selectedSupport.value, ...supports.value] : supports.value
  return items.map(item => ({ ...item }))
})
const hasExchange = computed(() => draft.sources.some(block => block.source_type === 'exchange'))
let supportGeneration = 0
let supportDetailGeneration = 0
function resetSupport() {
  ++supportGeneration; ++supportDetailGeneration
  draft.support_program_id = null; selectedSupport.value = null; support.value = null; supports.value = []
  supportsLoading.value = false; supportLoading.value = false; supportSearchError.value = ''; supportDetailError.value = ''
}
watch(hasExchange, yes => { if (yes) resetSupport() })
watch(() => distributor.value?.id, distributorId => {
  if (distributorId) { resetSupport(); return }
  ++supportGeneration
  supports.value = []; supportsLoading.value = false; supportSearchError.value = ''
})
async function findSupports(query: string) {
  if (hasExchange.value) return
  const token = ++supportGeneration
  supportsLoading.value = true; supportSearchError.value = ''; supports.value = []
  try { const result = await props.api.supports(query.trim(), distributor.value?.id); if (token === supportGeneration) supports.value = result.items }
  catch (failure) { if (token === supportGeneration) supportSearchError.value = errorMessage(failure) }
  finally { if (token === supportGeneration) supportsLoading.value = false }
}
function selectSupport(value: unknown) {
  if (hasExchange.value) return
  const selected = value === null ? null : supportOptions.value.find(item => item.id === value)
  if (selected === undefined) return
  selectedSupport.value = selected
  draft.support_program_id = selected?.id ?? null
  void loadSupport()
}
async function loadSupport() {
  const token = ++supportDetailGeneration
  support.value = null; supportDetailError.value = ''; supportLoading.value = false
  const selected = draft.support_program_id
  if (!selected || hasExchange.value) return
  supportLoading.value = true
  try { const result = await props.api.support(selected); if (token === supportDetailGeneration) support.value = result }
  catch (failure) { if (token === supportDetailGeneration) supportDetailError.value = errorMessage(failure) }
  finally { if (token === supportDetailGeneration) supportLoading.value = false }
}
const mark = ref<CatalogMark | null>(null)
const modelId = ref<string | null>(null)
const modificationId = ref<string | null>(null)
const trimId = ref<string | null>(null)
const models = ref<CatalogModel[]>([])
const modifications = ref<CatalogModification[]>([])
const trims = ref<CatalogTrim[]>([])
const modelsLoading = ref(false)
const modificationsLoading = ref(false)
const trimsLoading = ref(false)
const modelsError = ref('')
const modificationsError = ref('')
const trimsError = ref('')
const modelOptions = computed(() => models.value.filter(item => item.name?.trim()).map(item => ({ ...item })))
const modificationOptions = computed(() => modifications.value.filter(item => item.name?.trim()).map(item => ({ ...item })))
const trimOptions = computed(() => trims.value.filter(item => item.trim_name?.trim()).map(item => ({ ...item })))
let modelGeneration = 0
let modificationGeneration = 0
let trimGeneration = 0
function resetModification() { ++modificationGeneration; modificationId.value = null; draft.modification = null; modifications.value = []; modificationsError.value = ''; modificationsLoading.value = false }
function resetTrim() { ++trimGeneration; trimId.value = null; draft.trim = null; trims.value = []; trimsError.value = ''; trimsLoading.value = false }
function selectMark(value: CatalogMark | null) {
  ++modelGeneration
  mark.value = value; draft.brand = value?.name ?? null
  modelId.value = null; draft.model = null; models.value = []; modelsError.value = ''; modelsLoading.value = false
  resetModification()
  resetTrim()
  if (value) void loadModels()
}
async function loadModels() {
  const selected = mark.value
  if (!selected) return
  const token = ++modelGeneration
  modelsLoading.value = true; modelsError.value = ''
  try { const result = await props.api.models(selected.ids); if (token === modelGeneration) models.value = result.models }
  catch (failure) { if (token === modelGeneration) modelsError.value = errorMessage(failure) }
  finally { if (token === modelGeneration) modelsLoading.value = false }
}
function selectModel(value: unknown) {
  const selected = value === null ? null : models.value.find(item => item.id === value && item.name?.trim())
  if (selected === undefined) return
  modelId.value = selected?.id ?? null; draft.model = selected?.name ?? null
  resetModification()
  resetTrim()
  if (selected) void loadModifications()
}
async function loadModifications() {
  const selectedMark = mark.value
  const selectedModel = modelId.value
  if (!selectedMark || !selectedModel) return
  const token = ++modificationGeneration
  modificationsLoading.value = true; modificationsError.value = ''
  try { const result = await props.api.modifications(selectedMark.ids, selectedModel); if (token === modificationGeneration) modifications.value = result.modifications }
  catch (failure) { if (token === modificationGeneration) modificationsError.value = errorMessage(failure) }
  finally { if (token === modificationGeneration) modificationsLoading.value = false }
}
function selectModification(value: unknown) {
  const selected = value === null ? null : modifications.value.find(item => item.id === value && item.name?.trim())
  if (selected === undefined) return
  modificationId.value = selected?.id ?? null; draft.modification = selected?.name ?? null
  resetTrim()
  if (selected) void loadTrims()
}
async function loadTrims() {
  const selectedMark = mark.value
  const selectedModel = modelId.value
  const selectedModification = modificationId.value
  if (!selectedMark || !selectedModel || !selectedModification) return
  const token = ++trimGeneration
  trimsLoading.value = true; trimsError.value = ''
  try { const result = await props.api.trims(selectedMark.ids, selectedModel, selectedModification); if (token === trimGeneration) trims.value = result.trims }
  catch (failure) { if (token === trimGeneration) trimsError.value = errorMessage(failure) }
  finally { if (token === trimGeneration) trimsLoading.value = false }
}
function selectTrim(value: unknown) {
  const selected = value === null ? null : trims.value.find(item => item.id === value && item.trim_name?.trim())
  if (selected === undefined) return
  trimId.value = selected?.id ?? null; draft.trim = selected?.trim_name ?? null
}
onBeforeUnmount(() => { ++supportGeneration; ++supportDetailGeneration; ++modelGeneration; ++modificationGeneration; ++trimGeneration })
async function save() {
  if (saving.value) return
  draft.leasing_company_id = leasing.value?.id ?? null
  draft.dealer_company_id = dealer.value?.id ?? null
  draft.distributor_company_id = distributor.value?.id ?? null
  for (const block of draft.sources) for (const pair of block.pairs) {
    applyBudget(pair)
    const budgetError = pairBudget(pair).error
    if (budgetError) { error.value = budgetError; return }
  }
  const flattened = toProgramDraft(draft)
  error.value = validateDraft(flattened) ?? ''
  if (error.value) return
  saving.value = true
  try {
    const body: ProgramDraft = { ...flattened, reference_document_ids: referenceDocumentIds.value, name: draft.name.trim(), period_end: draft.period_end || null, brand: draft.brand?.trim() || null, model: draft.model?.trim() || null, modification: draft.modification?.trim() || null, trim: draft.trim?.trim() || null, vin: draft.vin?.trim() || null }
    const program = await props.api.createProgram(body)
    emit('saved', program)
  } catch (failure) { error.value = errorMessage(failure) } finally { saving.value = false }
}
</script>
