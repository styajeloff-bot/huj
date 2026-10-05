<template>
  <section
    class="funnel-card"
    aria-labelledby="application-status-funnel-title"
    :aria-busy="isLoading"
  >
    <div class="funnel-heading">
      <div>
        <h2 id="application-status-funnel-title" class="funnel-title">
          Заявки по статусам
        </h2>
        <p class="funnel-subtitle">
          Отдельные направления заявок в лизинговые компании
        </p>
      </div>
      <p v-if="data && !isLoading" class="funnel-total">
        Выбрано: <strong>{{ formatCount(selectedCount) }}</strong>
      </p>
    </div>

    <fieldset class="funnel-filters">
      <legend class="sr-only">Параметры воронки заявок по статусам</legend>

      <div class="funnel-filter funnel-filter--period">
        <span class="funnel-label">Отчётный период</span>
        <div class="funnel-date-range">
          <label class="funnel-date-field">
            <span class="sr-only">Начало отчётного периода</span>
            <input
              v-model="periodFrom"
              type="date"
              class="funnel-control"
              :min="historyAvailableFrom || undefined"
              aria-label="Начало отчётного периода"
            >
          </label>
          <span class="funnel-date-separator" aria-hidden="true">—</span>
          <label class="funnel-date-field">
            <span class="sr-only">Конец отчётного периода</span>
            <input
              v-model="periodTo"
              type="date"
              class="funnel-control"
              :min="historyAvailableFrom || undefined"
              aria-label="Конец отчётного периода"
            >
          </label>
        </div>
        <p v-if="historyAvailableFrom" class="funnel-hint">
          История доступна с {{ formatDate(historyAvailableFrom) }} · Москва
        </p>
      </div>

      <div class="funnel-filter funnel-filter--mode">
        <div class="funnel-label-row">
          <label for="application-funnel-mode" class="funnel-label">Режим отбора</label>
          <span class="funnel-tooltip-wrap">
            <button
              type="button"
              class="funnel-tooltip-trigger"
              aria-label="Как работает режим отбора"
              aria-describedby="application-funnel-mode-help"
            >
              <InformationCircleIcon aria-hidden="true" />
            </button>
            <span
              id="application-funnel-mode-help"
              role="tooltip"
              class="funnel-tooltip funnel-tooltip--right"
            >
              «Созданные» учитывает новые направления в ЛК. «Активные» также показывает
              заявки, которые уже были в работе в выбранном периоде.
            </span>
          </span>
        </div>
        <select
          id="application-funnel-mode"
          v-model="selectionMode"
          class="funnel-control funnel-select"
        >
          <option value="created_in_period">Созданные за период</option>
          <option value="active_during_period">Активные в периоде</option>
        </select>
      </div>
    </fieldset>

    <div class="sr-only" aria-live="polite" aria-atomic="true">
      {{ liveStatus }}
    </div>

    <div v-if="isLoading" class="funnel-skeleton" aria-label="Загрузка воронки">
      <div class="funnel-skeleton-header" />
      <div v-for="index in 13" :key="index" class="funnel-skeleton-row">
        <span class="funnel-skeleton-bar" :style="{ width: `${28 + (index % 5) * 11}%` }" />
        <span class="funnel-skeleton-label" />
        <span class="funnel-skeleton-bar" :style="{ width: `${24 + (index % 4) * 13}%` }" />
      </div>
    </div>

    <div
      v-else-if="isHistoryUnavailable"
      class="funnel-state funnel-state--history"
      role="status"
    >
      <InformationCircleIcon class="funnel-state-icon" aria-hidden="true" />
      <div>
        <h3>Для выбранного периода ещё нет достоверной истории</h3>
        <p>{{ errorMessage }}</p>
      </div>
    </div>

    <div v-else-if="errorMessage" class="funnel-state funnel-state--error" role="alert">
      <ExclamationTriangleIcon class="funnel-state-icon" aria-hidden="true" />
      <div>
        <h3>Не удалось загрузить воронку</h3>
        <p>{{ errorMessage }}</p>
        <button type="button" class="funnel-retry" @click="refresh">
          <ArrowPathIcon aria-hidden="true" />
          Повторить
        </button>
      </div>
    </div>

    <div v-else-if="data" class="funnel-content">
      <p v-if="selectedCount === 0" class="funnel-empty" role="status">
        За выбранный период заявок нет
      </p>

      <div
        class="funnel-desktop"
        role="table"
        aria-label="Воронка заявок в лизинговые компании по статусам"
        :aria-rowcount="rows.length + 1"
        aria-colcount="3"
      >
        <div class="funnel-grid funnel-grid--header" role="row" aria-rowindex="1">
          <div
            id="application-funnel-events-column"
            class="funnel-column-heading funnel-column-heading--left"
            role="columnheader"
            aria-colindex="1"
          >
            <span>Входили в статус</span>
            <span class="funnel-tooltip-wrap">
              <button
                type="button"
                class="funnel-tooltip-trigger"
                aria-label="Что означает колонка входили в статус"
                aria-describedby="application-funnel-events-help"
              >
                <InformationCircleIcon aria-hidden="true" />
              </button>
              <span
                id="application-funnel-events-help"
                role="tooltip"
                class="funnel-tooltip"
              >
                Сколько уникальных заявок в ЛК входило в статус хотя бы один раз
                в выбранном периоде.
              </span>
            </span>
          </div>
          <div
            id="application-funnel-status-column"
            class="funnel-status-heading"
            role="columnheader"
            aria-colindex="2"
          >
            Статус
          </div>
          <div
            id="application-funnel-end-state-column"
            class="funnel-column-heading"
            role="columnheader"
            aria-colindex="3"
          >
            <span>На конец периода</span>
            <span class="funnel-tooltip-wrap">
              <button
                type="button"
                class="funnel-tooltip-trigger"
                aria-label="Что означает колонка на конец периода"
                aria-describedby="application-funnel-end-state-help"
              >
                <InformationCircleIcon aria-hidden="true" />
              </button>
              <span
                id="application-funnel-end-state-help"
                role="tooltip"
                class="funnel-tooltip funnel-tooltip--right"
              >
                Последний известный статус каждой выбранной заявки в ЛК на конец
                указанного периода.
              </span>
            </span>
          </div>
        </div>

        <div
          v-for="(row, index) in rows"
          :key="row.status"
          class="funnel-grid funnel-grid--row"
          role="row"
          :aria-rowindex="index + 2"
        >
          <div
            class="funnel-bar-cell funnel-bar-cell--left"
            role="cell"
            aria-colindex="1"
          >
            <span class="funnel-count">{{ formatCount(row.eventsCount) }}</span>
            <span class="funnel-track" aria-hidden="true">
              <span
                v-if="row.eventsCount > 0"
                class="funnel-bar funnel-bar--left"
                :style="{ width: barWidth(row.eventsCount, maxEventsCount) }"
              />
            </span>
          </div>
          <div class="funnel-status" role="rowheader" aria-colindex="2">
            {{ row.label }}
          </div>
          <div
            class="funnel-bar-cell funnel-bar-cell--right"
            role="cell"
            aria-colindex="3"
          >
            <span class="funnel-track" aria-hidden="true">
              <span
                v-if="row.endStateCount > 0"
                class="funnel-bar funnel-bar--right"
                :style="{ width: barWidth(row.endStateCount, maxEndStateCount) }"
              />
            </span>
            <span class="funnel-count">{{ formatCount(row.endStateCount) }}</span>
          </div>
        </div>
      </div>

    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
} from '@heroicons/vue/24/outline'
import { useApplicationStatusFunnel } from '../composables/useApplicationStatusFunnel'

const {
  periodFrom,
  periodTo,
  selectionMode,
  data,
  rows,
  selectedCount,
  isLoading,
  errorMessage,
  historyAvailableFrom,
  isHistoryUnavailable,
  refresh,
} = useApplicationStatusFunnel()

defineExpose({ refresh })

const maxEventsCount = computed(() =>
  Math.max(0, ...rows.value.map((row) => row.eventsCount)),
)
const maxEndStateCount = computed(() =>
  Math.max(0, ...rows.value.map((row) => row.endStateCount)),
)
const liveStatus = computed(() => {
  if (isLoading.value) return 'Воронка загружается'
  if (errorMessage.value) return errorMessage.value
  return `Воронка загружена. Выбрано заявок в ЛК: ${selectedCount.value}`
})

function barWidth(value: number, maximum: number): string {
  if (value <= 0 || maximum <= 0) return '0%'
  return `${(value / maximum) * 100}%`
}

function formatCount(value: number): string {
  return value.toLocaleString('ru-RU')
}

function formatDate(value: string): string {
  const [year, month, day] = value.split('-')
  if (!year || !month || !day) return value
  return `${day}.${month}.${year}`
}
</script>

<style scoped>
.funnel-card {
  --funnel-primary: #0077cc;
  --funnel-primary-strong: #0867a9;
  --funnel-primary-soft: #dceeff;
  --funnel-border: #e2e8f0;
  --funnel-muted: #64748b;
  --funnel-surface-muted: #f8fafc;
  margin-bottom: 16px;
  padding: 20px;
  overflow: hidden;
  color: #0f172a;
  background: #ffffff;
  border: 1px solid #e8ebf1;
  border-radius: 14px;
}

.funnel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.funnel-title {
  font-size: 20px;
  font-weight: 700;
  line-height: 1.25;
  letter-spacing: -0.01em;
}

.funnel-subtitle,
.funnel-total,
.funnel-hint {
  color: var(--funnel-muted);
  font-size: 14px;
  line-height: 1.5;
}

.funnel-subtitle {
  margin-top: 4px;
}

.funnel-total {
  flex: none;
  font-variant-numeric: tabular-nums;
}

.funnel-total strong {
  color: #0f172a;
}

.funnel-filters {
  display: grid;
  grid-template-columns: minmax(280px, 1.4fr) minmax(220px, 1fr);
  gap: 16px;
  margin-top: 20px;
  padding: 16px;
  background: var(--funnel-surface-muted);
  border: 1px solid var(--funnel-border);
  border-radius: 10px;
}

.funnel-filter {
  min-width: 0;
}

.funnel-label-row,
.funnel-column-heading {
  display: flex;
  align-items: center;
  gap: 6px;
}

.funnel-label {
  display: block;
  margin-bottom: 6px;
  color: #475569;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}

.funnel-label-row .funnel-label {
  margin-bottom: 6px;
}

.funnel-tooltip-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.funnel-tooltip-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  color: var(--funnel-muted);
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: help;
}

.funnel-tooltip-trigger svg {
  width: 18px;
  height: 18px;
}

.funnel-tooltip-trigger:hover {
  color: var(--funnel-primary-strong);
  background: var(--funnel-primary-soft);
}

.funnel-tooltip-trigger:focus-visible,
.funnel-control:focus-visible,
.funnel-retry:focus-visible {
  outline: 2px solid var(--funnel-primary);
  outline-offset: 2px;
}

.funnel-tooltip {
  position: absolute;
  z-index: 20;
  top: calc(100% + 6px);
  left: 50%;
  width: max-content;
  max-width: min(280px, calc(100vw - 32px));
  padding: 9px 11px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 400;
  line-height: 1.45;
  text-align: left;
  pointer-events: none;
  opacity: 0;
  background: #1e293b;
  border-radius: 8px;
  transform: translate(-50%, -4px);
  transition: opacity 150ms ease-out, transform 150ms ease-out;
}

.funnel-tooltip--right {
  right: 0;
  left: auto;
  transform: translate(0, -4px);
}

.funnel-tooltip-wrap:hover .funnel-tooltip,
.funnel-tooltip-wrap:focus-within .funnel-tooltip {
  opacity: 1;
  transform: translate(-50%, 0);
}

.funnel-tooltip-wrap:hover .funnel-tooltip--right,
.funnel-tooltip-wrap:focus-within .funnel-tooltip--right {
  transform: translate(0, 0);
}

.funnel-date-range {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
}

.funnel-date-field {
  min-width: 0;
}

.funnel-date-separator {
  color: #94a3b8;
}

.funnel-control {
  width: 100%;
  height: 42px;
  box-sizing: border-box;
  padding: 9px 11px;
  color: #0f172a;
  font-size: 14px;
  line-height: 1.4;
  background-color: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
}

.funnel-control:hover {
  border-color: #94a3b8;
}

.funnel-select {
  padding-right: 36px;
  appearance: none;
  background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2364748b' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");
  background-position: right 10px center;
  background-repeat: no-repeat;
  background-size: 18px;
}

.funnel-hint {
  margin-top: 6px;
}

.funnel-content,
.funnel-skeleton,
.funnel-state {
  margin-top: 20px;
}

.funnel-empty {
  margin-bottom: 14px;
  padding: 10px 12px;
  color: #475569;
  font-size: 14px;
  line-height: 1.5;
  text-align: center;
  background: var(--funnel-surface-muted);
  border-radius: 8px;
}

.funnel-grid {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) minmax(210px, 280px) minmax(160px, 1fr);
  align-items: center;
  column-gap: 16px;
}

.funnel-grid--header {
  min-height: 44px;
  padding-bottom: 8px;
  color: #475569;
  font-size: 14px;
  font-weight: 600;
}

.funnel-column-heading--left {
  justify-content: flex-end;
}

.funnel-status-heading {
  text-align: center;
}

.funnel-grid--row {
  min-height: 54px;
  border-top: 1px solid #eef2f7;
}

.funnel-bar-cell {
  display: grid;
  grid-template-columns: minmax(34px, auto) minmax(80px, 1fr);
  align-items: center;
  gap: 8px;
}

.funnel-bar-cell--right {
  grid-template-columns: minmax(80px, 1fr) minmax(34px, auto);
}

.funnel-track {
  position: relative;
  display: block;
  height: 18px;
  overflow: hidden;
  background: #f1f5f9;
  border-radius: 4px;
}

.funnel-bar {
  position: absolute;
  top: 0;
  bottom: 0;
  background: var(--funnel-primary);
}

.funnel-bar--left {
  right: 0;
  background: var(--funnel-primary-strong);
  border-radius: 4px 0 0 4px;
}

.funnel-bar--right {
  left: 0;
  border-radius: 0 4px 4px 0;
}

.funnel-count {
  min-width: 34px;
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.funnel-bar-cell--left .funnel-count {
  text-align: right;
}

.funnel-status {
  padding: 8px 12px;
  color: #1e293b;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.35;
  text-align: center;
}

.funnel-state {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-height: 124px;
  padding: 20px;
  color: #334155;
  background: var(--funnel-surface-muted);
  border: 1px solid var(--funnel-border);
  border-radius: 10px;
}

.funnel-state--history {
  color: #1e3a5f;
  background: #eff6ff;
  border-color: #bfdbfe;
}

.funnel-state--error {
  color: #7f1d1d;
  background: #fff7f7;
  border-color: #fecaca;
}

.funnel-state-icon {
  width: 24px;
  height: 24px;
  flex: none;
}

.funnel-state h3 {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.4;
}

.funnel-state p {
  margin-top: 4px;
  font-size: 14px;
  line-height: 1.5;
}

.funnel-retry {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 40px;
  margin-top: 12px;
  padding: 8px 14px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  background: var(--funnel-primary-strong);
  border: 0;
  border-radius: 8px;
  cursor: pointer;
}

.funnel-retry:hover {
  background: #075985;
}

.funnel-retry:active {
  transform: scale(0.98);
}

.funnel-retry svg {
  width: 18px;
  height: 18px;
}

.funnel-skeleton-header,
.funnel-skeleton-label,
.funnel-skeleton-bar {
  display: block;
  background: #e8edf3;
  border-radius: 5px;
  animation: funnel-pulse 1.5s ease-in-out infinite;
}

.funnel-skeleton-header {
  width: 42%;
  height: 16px;
  margin: 0 auto 14px;
}

.funnel-skeleton-row {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) minmax(210px, 280px) minmax(160px, 1fr);
  align-items: center;
  gap: 16px;
  min-height: 54px;
  border-top: 1px solid #eef2f7;
}

.funnel-skeleton-row .funnel-skeleton-bar:first-child {
  justify-self: end;
}

.funnel-skeleton-label {
  width: 72%;
  height: 14px;
  margin: 0 auto;
}

.funnel-skeleton-bar {
  height: 18px;
}

@keyframes funnel-pulse {
  0%, 100% { opacity: 0.55; }
  50% { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .funnel-tooltip,
  .funnel-retry,
  .funnel-skeleton-header,
  .funnel-skeleton-label,
  .funnel-skeleton-bar {
    animation: none;
    transition-duration: 0.01ms;
  }
}

</style>
