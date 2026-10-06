<template>
  <main ref="workspaceContent" class="monetization monetization-workspace">
    <nav v-if="view === 'list'" class="registry-tabs workspace-tabs" role="tablist" aria-label="Разделы монетизации">
      <button v-for="item in tabs" :id="'monetization-' + item.id + '-tab'" :key="item.id" ref="tabButtons" type="button" role="tab" :aria-controls="'monetization-' + item.id + '-panel'" :aria-selected="tab === item.id" :tabindex="tab === item.id ? 0 : -1" @click="switchTab(item.id)" @keydown="handleTabKeydown($event, item.id)">{{ item.label }}</button>
    </nav>
    <ProgramEditor v-if="view === 'create' && admin" :api="api" @cancel="showList" @saved="created" />
    <ProgramDetail v-else-if="view === 'program' && selectedProgram" :key="selectedProgram.id" :program="selectedProgram" :api="api" :admin="role === 'carcraft_employee'" @close="showList" />
    <section v-else-if="view === 'requests' && selectedApplicationId && requestRole">
      <div class="actions registry-back"><button type="button" class="btn-secondary" @click="closeRequests">К запросам комиссии</button></div>
      <ConditionRequests :key="selectedApplicationId" :api="api" :application-id="selectedApplicationId" :role="requestRole" />
    </section>
    <section v-else-if="view === 'list' && tab === 'requests' && requestRole" id="monetization-requests-panel" role="tabpanel" aria-labelledby="monetization-requests-tab">
      <ConditionRequestsInbox :api="api" @open="navigateApplication" />
    </section>
    <section v-else :id="'monetization-' + tab + '-panel'" class="registry-panel" :class="{ 'registry-programs': tab === 'programs' }" role="tabpanel" :aria-labelledby="'monetization-' + tab + '-tab'">
      <header class="registry-heading">
        <div><h2>{{ tab === 'programs' ? 'Условия монетизации сделок' : 'Сделки монетизации' }}</h2><p>{{ tab === 'programs' ? 'Правила: кто из участников несёт расход по сделке и кто получает доход, в каких суммах/процентах.' : 'Внутренние расчёты и подтверждения участников сделки.' }}</p></div>
        <button v-if="tab === 'programs' && admin" type="button" class="btn-primary" @click="startCreate">Создать условия монетизации</button>
      </header>
      <div class="registry-filters">
        <CompanyPicker v-if="tab === 'programs'" :model-value="leasing" :api="api" kind="leasing" label="ЛИЗИНГОВАЯ КОМПАНИЯ" placeholder="Все ЛК" @update:model-value="updateLeasing" />
        <CompanyPicker v-else :model-value="client" :api="api" kind="client" label="КЛИЕНТ" placeholder="Название или ИНН" @update:model-value="updateClient" />
        <SearchableDropdown :anchor-to-control="true" :model-value="source || null" :items="availableSources" label="ИСТОЧНИК ЗАЯВКИ" placeholder="Все источники" clear-label="Все источники" label-key="label" value-key="value" :searchable="false" @update:model-value="updateSource" />
        <CatalogMarkPicker :model-value="brand" :api="api" label="МАРКА" @update:model-value="updateBrand" />
        <SearchableDropdown :anchor-to-control="true" :model-value="status || null" :items="statusOptions" label="СТАТУС" placeholder="Все статусы" clear-label="Все статусы" label-key="name" value-key="id" :searchable="false" @update:model-value="updateStatus" />
      </div>
      <div v-if="dealError" class="registry-deal-error" role="alert"><p>{{ dealError }}</p><div><button type="button" class="btn-primary" @click="retryDeal">Попробовать снова</button><button type="button" class="btn-secondary" @click="closeDeal">Закрыть</button></div></div>
      <div class="registry-results" :aria-busy="loading">
        <div v-if="loading" class="registry-state" role="status"><span class="registry-spinner" aria-hidden="true"></span><p>{{ tab === 'programs' ? 'Загружаем условия монетизации…' : 'Загружаем сделки…' }}</p></div>
        <div v-else-if="error" class="registry-state registry-error" role="alert"><p>{{ error }}</p><button type="button" class="btn-primary" @click="retry">Попробовать снова</button></div>
        <div v-else-if="!(tab === 'programs' ? programs.length : deals.length)" class="registry-state" role="status">
          <svg class="registry-empty-icon" aria-hidden="true" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
          <p>{{ tab === 'programs' ? 'Условия монетизации не найдены' : 'Сделки монетизации не найдены' }}</p>
        </div>
        <div v-else class="registry-table-scroll" tabindex="0" :aria-label="tab === 'programs' ? 'Таблица условий монетизации' : 'Таблица сделок монетизации'">
        <table v-if="tab === 'programs'" class="programs-table"><thead><tr><th>Название</th><th>Марка</th><th>Участники</th><th>Период действия</th><th>Статус</th><th>Действия</th></tr></thead><tbody><tr v-for="item in programs" :key="item.id"><td><strong>{{ item.name }}</strong></td><td>{{ item.brand || 'Все марки' }}</td><td><ParticipantList :participants="[...item.expense_participants, ...item.income_participants]" wildcard /></td><td>{{ formatDate(item.period_start) }} → {{ item.period_end ? formatDate(item.period_end) : 'бессрочно' }}</td><td><span class="badge" :class="item.status">{{ item.status === 'active' ? 'Активна' : 'Неактивна' }}</span></td><td><button class="link" @click="openProgram(item.id)">Карточка</button></td></tr></tbody></table>
        <table v-else class="deals-table"><thead><tr><th>Заявка</th><th>Источник заявки</th><th>Марка</th><th>Дилер / клиент</th><th>Стоимость имущества</th><th>Участники расхода</th><th>Участники дохода</th><th>Подтверждения</th><th>Статус</th><th>Действия</th></tr></thead><tbody><tr v-for="item in deals" :key="item.id"><td><strong>{{ dealNumber(item) }}</strong><p v-if="item.created_at" class="registry-date">{{ formatCreatedAt(item.created_at) }}</p></td><td><span class="source-pill"><ApplicationSourceBadge v-if="applicationSourceOf(item.source_type)" :source="applicationSourceOf(item.source_type)" /><template v-else>{{ sourceLabel(item.source_type) }}</template></span><p v-if="isFastDealSource(item.source_type)" class="muted">{{ fastDealOriginLabel }}</p></td><td>{{ item.brand || '—' }}<p v-if="item.leasing_company" class="muted">ЛК: {{ item.leasing_company.name }}</p></td><td>{{ item.dealer_company?.name || '—' }}<p class="muted">{{ item.client_company?.name || '—' }}</p></td><td :title="'Сумма без НДС: ' + formatMoney(item.base_amount)">{{ formatMoney(item.base_amount) }}</td><td><ParticipantList :participants="item.expense_participants" /></td><td><ParticipantList :participants="item.income_participants" /></td><td><template v-for="party in confirmationParties" :key="party"><p v-if="item.confirmations[party].applicable" :title="item.confirmations[party].confirmed_at ? (item.confirmations[party].confirmed_by_name || 'Пользователь') : undefined"><span class="badge" :class="{ active: !!item.confirmations[party].confirmed_at }">{{ party === 'leasing' ? 'ЛК' : participantLabels[party] }} {{ item.confirmations[party].confirmed_at ? '✓' : '· ожидается' }}</span></p></template></td><td><span class="badge" :class="item.status">{{ item.status === 'paid' ? 'Оплачена' : 'Ожидает подтверждения' }}</span></td><td><button class="link" @click="navigateDeal(item.id)">Просмотр</button></td></tr></tbody></table>
        </div>
        <footer v-if="totalPages > 1 && !loading && !error" class="registry-pagination">
          <span>Показаны {{ (page - 1) * pageSize + 1 }}–{{ Math.min(page * pageSize, total) }} из {{ total }}</span>
          <div><button type="button" class="btn-secondary" :disabled="page <= 1" @click="changePage(page - 1)">Предыдущая</button><button type="button" class="btn-secondary" :disabled="page >= totalPages" @click="changePage(page + 1)">Следующая</button></div>
        </footer>
      </div>
    </section>
    <p v-if="dealLoading" class="registry-detail-loading" role="status">Открываем сделку…</p>
    <DealDetail v-if="selectedDeal && view === 'list' && tab === 'deals'" :key="selectedDeal.id" :deal="selectedDeal" :api="api" :role="role" @close="closeDeal" @updated="updateDeal" />
  </main>
</template>
<script setup lang="ts">
import '~/assets/css/workspace-tabs.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
import type { CatalogMark, Company, Deal, DealSummary, Program, ProgramSummary, Role } from '../types'
import { participantLabels, sourceLabel, sourceOptions } from '../editor'
import { applicationSourceOf, dealNumber, fastDealOriginLabel, isFastDealSource } from '../dealSource'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import { formatMoney } from '../money'
import CompanyPicker from './CompanyPicker.vue'
import CatalogMarkPicker from './CatalogMarkPicker.vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import ParticipantList from './ParticipantList.vue'
import ProgramEditor from './ProgramEditor.vue'
import ProgramDetail from './ProgramDetail.vue'
import DealDetail from './DealDetail.vue'
import ConditionRequests from './ConditionRequests.vue'
import ConditionRequestsInbox from './ConditionRequestsInbox.vue'
import type { MonetizationTarget } from '../routes'
import '../monetization.css'
const props = defineProps<{ api: MonetizationApi; role: Role; target?: MonetizationTarget }>()
const emit = defineEmits<{ navigate: [target: MonetizationTarget] }>()
const workspaceContent = ref<HTMLElement | null>(null)
const requestRole = computed(() => props.role === 'dealer' || props.role === 'leasing_company' ? props.role : null)
const selectedApplicationId = ref<string | null>(null)
const canManagePrograms = ref(false)
const admin = computed(() => props.role === 'carcraft_employee' && canManagePrograms.value)
type Tab = 'programs' | 'deals' | 'requests'
const tab = ref<Tab>('programs')
const tabButtons = ref<HTMLButtonElement[]>([])
const tabs = computed<{ id: Tab; label: string }[]>(() => [
  { id: 'programs', label: 'Условия монетизации' },
  { id: 'deals', label: 'Сделки' },
  ...(requestRole.value ? [{ id: 'requests' as const, label: 'Запросы комиссии' }] : []),
])
const view = ref<'list' | 'create' | 'program' | 'requests'>('list')
const source = ref('')
const brand = ref<CatalogMark | null>(null)
const status = ref('')
const leasing = ref<Company | null>(null)
const client = ref<Company | null>(null)
const programs = ref<ProgramSummary[]>([])
const deals = ref<DealSummary[]>([])
const selectedProgram = ref<Program | null>(null)
const selectedDeal = ref<Deal | null>(null)
const dealLoading = ref(false)
const dealError = ref('')
const requestedDealId = ref<string | null>(null)
const loading = ref(false)
const error = ref('')
const pageSize = 20
const page = ref(1)
const total = ref(0)
const totalPages = ref(1)
const confirmationParties = ['leasing', 'dealer', 'distributor'] as const
const availableSources = sourceOptions.map(option => ({ ...option }))
const statusOptions = computed(() => tab.value === 'programs' ? [{ id: 'active', name: 'Активна' }, { id: 'inactive', name: 'Неактивна' }] : [{ id: 'pending_approval', name: 'Ожидает подтверждения' }, { id: 'paid', name: 'Оплачена' }])
const formatDate = (date: string) => date.split('-').reverse().join('.')
const formatCreatedAt = (value: string) => new Date(value).toLocaleDateString('ru-RU')
let generation = 0
let dealGeneration = 0
let listTab: Tab | null = null
let preserveListOnRouteClear = false
let previousTargetWasDeal = false
async function load() {
  if (tab.value === 'requests' || view.value !== 'list') return
  const requestedTab = tab.value
  listTab = requestedTab
  if (requestedTab === 'programs') canManagePrograms.value = false
  const token = ++generation
  loading.value = true; error.value = ''
  const query = { page: page.value, page_size: pageSize, source_type: source.value || undefined, brand: brand.value?.name, status: status.value || undefined, ...(tab.value === 'programs' ? { leasing_company_id: leasing.value?.id } : { client_company_id: client.value?.id }) }
  try {
    const result = requestedTab === 'programs' ? await props.api.programs(query) : await props.api.deals(query)
    if (token !== generation) return
    if (requestedTab === 'programs') {
      programs.value = result.items as ProgramSummary[]
      canManagePrograms.value = 'can_manage' in result && result.can_manage === true
    }
    else deals.value = result.items as DealSummary[]
    total.value = result.pagination.total
    totalPages.value = Math.max(1, result.pagination.total_pages)
  } catch (failure) { if (token === generation) error.value = errorMessage(failure) }
  finally { if (token === generation) loading.value = false }
}
function retry() { void load() }
function invalidateList() { ++generation; loading.value = false; error.value = '' }
function clearDeal() { ++dealGeneration; selectedDeal.value = null; dealLoading.value = false; dealError.value = ''; requestedDealId.value = null }
function clearRouteKeepingList() {
  if (!props.target) return
  preserveListOnRouteClear = true
  emit('navigate', null)
}
function applyFilters() {
  page.value = 1
  clearDeal()
  clearRouteKeepingList()
  void load()
}
function updateLeasing(value: Company | null) { leasing.value = value; applyFilters() }
function updateClient(value: Company | null) { client.value = value; applyFilters() }
function updateBrand(value: CatalogMark | null) { brand.value = value; applyFilters() }
function updateSource(value: unknown) { source.value = typeof value === 'string' ? value : ''; applyFilters() }
function updateStatus(value: unknown) { status.value = typeof value === 'string' ? value : ''; applyFilters() }
function clearFilters() { source.value = ''; brand.value = null; status.value = ''; leasing.value = null; client.value = null; page.value = 1 }
function changePage(next: number) {
  if (loading.value || next < 1 || next > totalPages.value) return
  page.value = next
  void load()
}
function switchTab(next: Tab) {
  if (next === 'requests' && !requestRole.value) return
  invalidateList(); clearDeal()
  tab.value = next; view.value = 'list'; clearFilters()
  if (next === 'requests') { if (props.target !== undefined) emit('navigate', { kind: 'requests' }); return }
  clearRouteKeepingList()
  void load()
}
function handleTabKeydown(event: KeyboardEvent, current: Tab) {
  const ids = tabs.value.map(item => item.id)
  const index = ids.indexOf(current)
  const next = event.key === 'Home' ? ids[0]
    : event.key === 'End' ? ids[ids.length - 1]
    : event.key === 'ArrowRight' ? ids[(index + 1) % ids.length]
    : event.key === 'ArrowLeft' ? ids[(index + ids.length - 1) % ids.length]
    : undefined
  if (!next) return
  event.preventDefault()
  switchTab(next)
  void nextTick(() => tabButtons.value.find(button => button.id === 'monetization-' + next + '-tab')?.focus())
}
function scrollContentToTop(expectedView: 'create' | 'program') {
  void nextTick(() => {
    if (view.value === expectedView) workspaceContent.value?.parentElement?.closest('main')?.scrollTo({ top: 0, behavior: 'auto' })
  })
}
function startCreate() { if (!admin.value) return; invalidateList(); clearDeal(); view.value = 'create'; scrollContentToTop('create') }
function showList() { ++generation; loading.value = false; error.value = ''; view.value = 'list'; if (props.target) emit('navigate', null); else void load() }
function created(program: Program) { selectedProgram.value = program; view.value = 'program'; scrollContentToTop('program') }
async function openProgram(id: string) {
  const token = ++generation
  loading.value = true; error.value = ''
  try {
    const program = await props.api.program(id)
    if (token !== generation) return
    selectedProgram.value = program; view.value = 'program'
    scrollContentToTop('program')
  } catch (failure) { if (token === generation) error.value = errorMessage(failure) }
  finally { if (token === generation) loading.value = false }
}
async function openDeal(id: string) {
  const needsList = tab.value !== 'deals' || listTab !== 'deals'
  if (tab.value !== 'deals') { invalidateList(); clearFilters() }
  tab.value = 'deals'; view.value = 'list'
  if (needsList) void load()
  const token = ++dealGeneration
  requestedDealId.value = id; selectedDeal.value = null; dealLoading.value = true; dealError.value = ''
  try {
    const result = await props.api.deal(id)
    if (token === dealGeneration) selectedDeal.value = result
  } catch (failure) { if (token === dealGeneration) dealError.value = errorMessage(failure) }
  finally { if (token === dealGeneration) dealLoading.value = false }
}
function retryDeal() { if (requestedDealId.value) void openDeal(requestedDealId.value) }
function closeDeal() { clearDeal(); clearRouteKeepingList() }
function updateDeal(value: Deal) {
  selectedDeal.value = value
  const index = deals.value.findIndex(item => item.id === value.id)
  if (index !== -1) deals.value[index] = { ...deals.value[index]!, status: value.status, confirmations: value.confirmations }
}
function navigateDeal(id: string) { if (props.target !== undefined) emit('navigate', { kind: 'deal', id }); else void openDeal(id) }
function navigateApplication(id: string) {
  if (props.target !== undefined) emit('navigate', { kind: 'application', id })
  else { selectedApplicationId.value = id; view.value = 'requests' }
}
function closeRequests() {
  if (props.target !== undefined) emit('navigate', { kind: 'requests' })
  else { view.value = 'list'; tab.value = 'requests' }
}
function applyTarget(target: MonetizationTarget | undefined) {
  const preserveList = preserveListOnRouteClear || previousTargetWasDeal
  preserveListOnRouteClear = false
  previousTargetWasDeal = target?.kind === 'deal'
  if (target?.kind === 'deal') { void openDeal(target.id); return }
  clearDeal()
  if (target?.kind === 'application' && requestRole.value) { invalidateList(); selectedApplicationId.value = target.id; tab.value = 'requests'; view.value = 'requests'; return }
  if (target?.kind === 'requests' && requestRole.value) { invalidateList(); tab.value = 'requests'; view.value = 'list'; return }
  if (preserveList && view.value === 'list') return
  invalidateList(); view.value = 'list'
  if (tab.value === 'requests') tab.value = 'programs'
  void load()
}
watch(() => props.target, applyTarget)
onMounted(() => applyTarget(props.target))
onBeforeUnmount(() => { ++generation; ++dealGeneration })
</script>

<style scoped>
.monetization-workspace { min-width:0; width:100%; }
.registry-panel { min-width:0; }
.registry-programs { max-width:1120px; }
.registry-heading { display:flex; align-items:center; justify-content:space-between; gap:20px; margin-bottom:24px; }
.registry-heading h2 { font-size:20px; font-weight:600; line-height:28px; color:#111827; margin:0; }
.registry-heading p { font-size:13px; line-height:20px; color:#6b7280; margin:4px 0 0; }
.registry-heading>button { flex-shrink:0; }
.registry-filters { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; padding:16px; margin-bottom:24px; border:1px solid #e5e7eb; border-radius:8px; background:#fff; }
.registry-filters>* { min-width:0; }
.registry-results { min-width:0; max-width:100%; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; background:#fff; }
.registry-state { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:160px; padding:32px 24px; color:#4b5563; text-align:center; }
.registry-state p { margin:8px 0 0; font-size:14px; }
.registry-state .btn-primary { margin-top:16px; }
.registry-error p { color:#dc2626; }
.registry-empty-icon { width:48px; height:48px; color:#9ca3af; margin-bottom:4px; }
.registry-spinner { width:32px; height:32px; border:2px solid #e5e7eb; border-bottom-color:#2563eb; border-radius:50%; animation:registry-spin .8s linear infinite; }
.registry-table-scroll { max-width:100%; overflow-x:auto; }
.registry-table-scroll:focus-visible { outline:2px solid #93c5fd; outline-offset:-2px; }
.registry-table-scroll table { border-collapse:collapse; width:100%; }
.registry-table-scroll .programs-table { min-width:800px; }
.registry-table-scroll .deals-table { min-width:1180px; }
.registry-table-scroll th { padding:12px 24px; background:#f9fafb; color:#6b7280; font-size:12px; font-weight:500; letter-spacing:.05em; border-bottom:1px solid #e5e7eb; }
.registry-table-scroll td { padding:16px 24px; border-top:1px solid #e5e7eb; color:#374151; font-size:14px; vertical-align:top; }
.registry-table-scroll tbody tr:hover { background:#f9fafb; }
.registry-table-scroll td strong { color:#111827; font-weight:500; }
.registry-table-scroll .deals-table th { white-space:normal; }
.registry-pagination { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; padding:12px 24px; border-top:1px solid #e5e7eb; background:#f9fafb; font-size:14px; color:#6b7280; }
.registry-pagination>div { display:flex; gap:8px; }
.registry-back { margin-bottom:20px; }
.registry-deal-error { padding:16px; margin-bottom:16px; border:1px solid #fecaca; border-radius:8px; background:#fef2f2; color:#991b1b; }
.registry-deal-error p { margin:0 0 12px; }
.registry-deal-error>div { display:flex; gap:8px; }
.registry-detail-loading { position:fixed; right:24px; top:88px; z-index:40; padding:10px 16px; border:1px solid #e5e7eb; border-radius:8px; background:#fff; color:#4b5563; box-shadow:0 4px 12px #00000012; }
.registry-date { font-size:12px; color:#6b7280; margin-top:2px; white-space:nowrap; }
@keyframes registry-spin { to { transform:rotate(360deg); } }
@media (min-width:768px) and (max-width:1100px) {
  .registry-heading { align-items:flex-start; flex-wrap:wrap; }
  .registry-filters { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
