<template>
  <div class="analytics-dashboard">
    <!-- Compact Filter Bar -->
    <div class="filter-bar">
      <div class="filter-bar-inner">
        <div class="filter-group">
          <label class="filter-label">Дата заявки</label>
          <div class="filter-date-range">
            <input
              v-model="filters.period_from"
              type="date"
              class="filter-date-input"
              placeholder="ДД.ММ.ГГГГ"
            />
            <span class="filter-date-sep">—</span>
            <input
              v-model="filters.period_to"
              type="date"
              class="filter-date-input"
              placeholder="ДД.ММ.ГГГГ"
            />
          </div>
        </div>

        <div class="filter-group">
          <label class="filter-label">Статусы</label>
          <div class="relative">
            <button class="filter-select filter-select_button" @click="statusDropdownOpen = !statusDropdownOpen">
              <span class="truncate">
                {{ (filters.statuses || []).length ? `${(filters.statuses || []).length} выбрано` : 'Все статусы' }}
              </span>
              <svg class="w-4 h-4 text-gray-400 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            <div
              v-if="statusDropdownOpen"
              class="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-60 overflow-auto"
            >
              <div
                v-for="opt in STATUS_OPTIONS"
                :key="opt.value"
                class="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer"
                @click="toggleStatus(opt.value as string)"
              >
                <input
                  type="checkbox"
                  :checked="(filters.statuses || []).includes(opt.value as string)"
                  class="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                  @click.stop
                />
                <span class="ml-2 text-sm">{{ opt.label }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="filter-actions">
          <button class="filter-btn filter-btn_reset" @click="resetFilters">
            Сбросить
          </button>
          <button class="filter-btn filter-btn_apply" @click="applyFilters">
            Применить
          </button>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tabs-bar">
      <nav class="tabs-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-button"
          :class="{ active: activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>

    <!-- Loading Skeleton -->
    <div v-if="isLoading" class="dash-grid">
      <div v-for="i in 4" :key="i" class="kpi-span-3">
        <div class="bg-white rounded p-4 animate-pulse h-24" />
      </div>
      <div class="chart-wide">
        <div class="bg-white rounded p-4 animate-pulse h-80" />
      </div>
      <div class="chart-half">
        <div class="bg-white rounded p-4 animate-pulse h-72" />
      </div>
      <div class="chart-half">
        <div class="bg-white rounded p-4 animate-pulse h-72" />
      </div>
    </div>

    <!-- Error Banner -->
    <div
      v-if="error && !isLoading"
      class="bg-yellow-50 border border-yellow-200 rounded p-3 mb-4 flex items-center justify-between"
    >
      <div class="flex items-center text-sm text-yellow-800">
        <svg class="w-4 h-4 mr-2 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <span>Не удалось загрузить аналитику. Попробуйте повторить запрос.</span>
      </div>
      <button
        class="text-sm text-yellow-700 hover:text-yellow-900 font-medium underline"
        @click="refresh"
      >
        Повторить
      </button>
    </div>

    <!-- Tab Content -->
    <div v-if="!isLoading">
      <OverviewTab v-if="activeTab === 'overview'" :data="displayData" />
      <ApplicationsTab
        v-else-if="activeTab === 'applications'"
        :data="displayData"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <ProposalsTab
        v-else-if="activeTab === 'proposals'"
        :data="displayData"
        :loading="isLoading"
        @page-change="onPageChange"
      />
      <FinancialsTab
        v-else-if="activeTab === 'financials'"
        :data="displayData"
        :loading="isLoading"
        @page-change="onPageChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'nuxt/app'
import {
  useLkDashboard,
  STATUS_OPTIONS,
  type LkDashboardTab,
  type LkDashboardFilters,
  type LkDashboardResponse,
} from '../api/analytics'
import OverviewTab from './OverviewTab.vue'
import ApplicationsTab from './ApplicationsTab.vue'
import ProposalsTab from './ProposalsTab.vue'
import FinancialsTab from './FinancialsTab.vue'

const props = defineProps<{ disableUrlSync?: boolean }>()

const route = useRoute()
const router = useRouter()

const tabs: { key: LkDashboardTab; label: string }[] = [
  { key: 'overview', label: 'Заявки' },
  { key: 'applications', label: 'Лизинговые сделки' },
  { key: 'proposals', label: 'Страхование' },
  { key: 'financials', label: 'Финансы' },
]

const activeTab = ref<LkDashboardTab>('overview')
const statusDropdownOpen = ref(false)
const currentOffset = ref(0)
const pageLimit = ref(20)

const filters = ref<LkDashboardFilters>({
  period_from: '',
  period_to: '',
  statuses: [],
  dealers: [],
  marks: [],
})

function buildFilters(): LkDashboardFilters {
  const f: LkDashboardFilters = {}
  if (filters.value.period_from) f.period_from = filters.value.period_from
  if (filters.value.period_to) f.period_to = filters.value.period_to
  if ((filters.value.statuses || []).length) f.statuses = filters.value.statuses
  return f
}

// API
const { data, isLoading, error, refresh, execute } = useLkDashboard<LkDashboardResponse>({ immediate: false })

const displayData = computed<LkDashboardResponse | null>(() => {
  return data.value || null
})

function loadData() {
  execute({
    tab: activeTab.value,
    filters: buildFilters(),
    limit: pageLimit.value,
    offset: currentOffset.value,
  })
}

function switchTab(tab: LkDashboardTab) {
  activeTab.value = tab
  currentOffset.value = 0
  syncUrl()
  loadData()
}

function onPageChange(offset: number) {
  currentOffset.value = offset
  loadData()
}

function applyFilters() {
  currentOffset.value = 0
  syncUrl()
  loadData()
}

function resetFilters() {
  filters.value = { period_from: '', period_to: '', statuses: [], dealers: [], marks: [] }
  currentOffset.value = 0
  syncUrl()
  loadData()
}

function toggleStatus(status: string) {
  const list = filters.value.statuses || []
  const idx = list.indexOf(status)
  if (idx > -1) {
    list.splice(idx, 1)
  } else {
    list.push(status)
  }
}

// URL sync
function syncUrl() {
  if (props.disableUrlSync) return
  const query: Record<string, string | string[]> = {}
  if (activeTab.value !== 'overview') query.tab = activeTab.value
  if (filters.value.period_from) query.period_from = filters.value.period_from
  if (filters.value.period_to) query.period_to = filters.value.period_to
  if ((filters.value.statuses || []).length) query.statuses = filters.value.statuses || []
  if (currentOffset.value > 0) query.offset = String(currentOffset.value)

  router.replace({ query })
}

function restoreFromUrl() {
  if (props.disableUrlSync) return
  const q = route.query
  if (q.tab && tabs.some(t => t.key === q.tab)) {
    activeTab.value = q.tab as LkDashboardTab
  }
  if (q.period_from) filters.value.period_from = String(q.period_from)
  if (q.period_to) filters.value.period_to = String(q.period_to)
  if (q.statuses) {
    filters.value.statuses = Array.isArray(q.statuses)
      ? q.statuses.filter(Boolean) as string[]
      : [String(q.statuses)]
  }
  if (q.offset) currentOffset.value = Number(q.offset) || 0
}

// Close dropdown on outside click
function onClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.relative')) {
    statusDropdownOpen.value = false
  }
}

onMounted(() => {
  restoreFromUrl()
  loadData()
  document.addEventListener('click', onClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
.analytics-dashboard {
  padding: 16px;
  background: #F0F2F5;
  min-height: 100vh;
}

/* Filter Bar */
.filter-bar {
  background: #ffffff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  margin-bottom: 16px;
  padding: 12px 16px;
}

.filter-bar-inner {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 140px;
  flex: 1 1 0;
}

.filter-label {
  font-size: 12px;
  font-weight: 500;
  color: #6b7280;
}

.filter-date-range {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-date-input {
  padding: 6px 8px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  color: #111827;
  background: #fff;
  min-width: 0;
  flex: 1 1 0;
}

.filter-date-sep {
  color: #9ca3af;
  font-size: 13px;
}

.filter-select {
  padding: 6px 24px 6px 8px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 13px;
  color: #111827;
  background: #fff;
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 6px center;
  background-repeat: no-repeat;
  background-size: 16px;
  min-width: 0;
}

.filter-select_button {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
  background-image: none;
}

.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
  padding-bottom: 1px;
}

.filter-btn {
  padding: 6px 14px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
}

.filter-btn_reset {
  background: transparent;
  color: #6b7280;
}

.filter-btn_reset:hover {
  color: #111827;
  background: #f3f4f6;
}

.filter-btn_apply {
  background: #0077CC;
  color: #fff;
}

.filter-btn_apply:hover {
  background: #005fa3;
}

/* Tabs */
.tabs-bar {
  background: #ffffff;
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  margin-bottom: 16px;
  overflow-x: auto;
}

.tabs-nav {
  display: flex;
  min-width: max-content;
}

.tab-button {
  flex-shrink: 0;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
  color: #6b7280;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  white-space: nowrap;
  background: none;
  border-top: none;
  border-left: none;
  border-right: none;
  cursor: pointer;
}

.tab-button:hover {
  color: #111827;
  background: #f9fafb;
}

.tab-button.active {
  color: #0077CC;
  border-bottom-color: #0077CC;
  background: #f0f9ff;
}

/* Dash Grid */
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 16px;
}

.kpi-span-3 {
  grid-column: span 3;
  padding: 16px;
}

.chart-wide {
  grid-column: span 12;
}

.chart-half {
  grid-column: span 6;
}

@media (max-width: 1024px) {
  .kpi-span-3 {
    grid-column: span 4;
  }
  .chart-half {
    grid-column: span 12;
  }
}

</style>
