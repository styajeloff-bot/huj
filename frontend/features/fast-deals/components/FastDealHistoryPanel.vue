<template>
  <section class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-history-title">
    <h2 id="fast-deal-history-title" class="text-lg font-semibold text-gray-900 mb-4">История</h2>
    <p v-if="!events.length" class="text-sm text-gray-500">История пока пуста.</p>
    <ol v-else class="space-y-4">
      <li v-for="event in visibleEvents" :key="event.id" class="border-l-2 border-gray-200 pl-4">
        <div class="flex items-baseline justify-between gap-3 flex-wrap">
          <p class="text-sm font-medium text-gray-900">{{ historyEventLabel(event.event_type) }}</p>
          <time class="text-xs text-gray-500" :datetime="event.created_at">{{ formatDateTime(event.created_at) }}</time>
        </div>
        <p v-if="event.actor_name || event.actor_company_name" class="text-xs text-gray-500">
          {{ [event.actor_name, event.actor_company_name].filter(Boolean).join(' · ') }}
        </p>
        <p v-if="event.lc_company_name" class="text-sm text-gray-700">Лизинговая компания: {{ event.lc_company_name }}</p>
        <p v-if="event.from_status || event.to_status" class="text-sm text-gray-700">
          Статус: {{ event.from_status ? dealStatusLabel(event.from_status) : '—' }} → {{ event.to_status ? dealStatusLabel(event.to_status) : '—' }}
        </p>
        <p v-if="event.reason" class="text-sm text-gray-700">Причина: {{ event.reason }}</p>
        <ul v-if="changeLines(event).length" class="mt-1 space-y-0.5 text-sm text-gray-700">
          <li v-for="(line, index) in changeLines(event)" :key="index">
            <span class="text-gray-500">{{ line.label }}:</span>
            <span v-if="line.before !== null" class="text-gray-500 line-through"> {{ line.before }}</span>
            <span v-if="line.before !== null"> →</span>
            {{ line.after }}
          </li>
        </ul>
      </li>
    </ol>
    <button v-if="events.length > LIMIT" type="button" class="mt-4 text-sm text-blue-600 hover:text-blue-700" @click="expanded = !expanded">
      {{ expanded ? 'Свернуть' : `Показать всё (${events.length})` }}
    </button>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import {
  dealStatusLabel,
  formatChangeValue,
  formatDateTime,
  historyEventLabel,
  vehicleFieldLabel,
} from '../composables/fastDealCardFormat'
import type { FastDealCard, FastDealHistoryItem } from '../types'

const LIMIT = 10

interface ChangeLine {
  label: string
  /** `null` when the entry has no "before" side (a value that was added). */
  before: string | null
  after: string
}

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const expanded = ref(false)

/** Newest first; the server's order breaks ties between events of the same instant. */
const events = computed(() =>
  props.deal.history
    .map((item, index) => ({ item, index }))
    .sort((a, b) => (Date.parse(b.item.created_at) - Date.parse(a.item.created_at)) || b.index - a.index)
    .map(entry => entry.item),
)
const visibleEvents = computed(() => (expanded.value ? events.value : events.value.slice(0, LIMIT)))

function vehicleLabel(vehicleId: string): string {
  const vehicle = props.deal.vehicles.find(item => item.id === vehicleId)
  return vehicle ? `VIN ${vehicle.vin}` : 'Позиция'
}

/** Purposes and regions are stored by code; the history shows their display names. */
function valueText(field: string, value: unknown): string {
  if ((field === 'purposes' || field === 'regions') && Array.isArray(value)) {
    return value.length ? value.map(code => ctx.directoryLabel(field, String(code))).join(', ') : 'Не выбрано'
  }
  // A dealer is stored by its company id: show the name the card already knows.
  if (field === 'dealer_company_id' && typeof value === 'string') return ctx.companyName(value) || value
  return formatChangeValue(field, value)
}

function isBeforeAfter(value: unknown): value is { before?: unknown; after?: unknown } {
  return !!value && typeof value === 'object' && !Array.isArray(value) && ('before' in value || 'after' in value)
}

/** Flat `{field: {before, after}}` snapshots, keys like `vehicle.<id>.<field>`, and the DL `positions` diff list. */
function changeLines(event: FastDealHistoryItem): ChangeLine[] {
  const changes = event.changes
  if (!changes || typeof changes !== 'object') return []
  const lines: ChangeLine[] = []
  for (const [key, value] of Object.entries(changes)) {
    if (key === 'positions' && Array.isArray(value)) {
      for (const entry of value) {
        const diff = entry as { vehicle_id?: string; vin?: string; field?: string; before?: unknown; after?: unknown }
        const field = String(diff.field ?? '')
        lines.push({
          label: `${diff.vin ? `VIN ${diff.vin}` : vehicleLabel(String(diff.vehicle_id ?? ''))}: ${vehicleFieldLabel(field)}`,
          before: valueText(field, diff.before),
          after: valueText(field, diff.after),
        })
      }
      continue
    }
    const parts = key.split('.')
    const isVehicleKey = parts[0] === 'vehicle' && parts.length >= 3
    const field = isVehicleKey ? parts.slice(2).join('.') : key
    const label = isVehicleKey ? `${vehicleLabel(parts[1])}: ${vehicleFieldLabel(field)}` : vehicleFieldLabel(field)
    if (isBeforeAfter(value)) {
      lines.push({
        label,
        before: value.before === null || value.before === undefined ? null : valueText(field, value.before),
        after: valueText(field, value.after),
      })
    } else {
      lines.push({ label, before: null, after: valueText(field, value) })
    }
  }
  return lines
}
</script>
