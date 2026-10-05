<template>
  <div class="space-y-4">
    <form class="grid grid-cols-2 lg:grid-cols-4 gap-3 items-end" novalidate @submit.prevent="applyFilters">
      <FastDealCardField label="VIN" for-id="fast-deal-table-vin">
        <input
          id="fast-deal-table-vin"
          v-model="filters.vin"
          type="text"
          maxlength="32"
          autocomplete="off"
          class="input-field font-mono uppercase"
          :disabled="loading"
        />
      </FastDealCardField>
      <FastDealCardField label="Склад" for-id="fast-deal-table-warehouse">
        <FastDealCardLookupSelect id="fast-deal-table-warehouse" v-model="filters.warehouse_id" kind="warehouses" placeholder="Все склады" />
      </FastDealCardField>
      <FastDealCardField label="Марка" for-id="fast-deal-table-mark">
        <FastDealCardLookupSelect
          id="fast-deal-table-mark"
          v-model="filters.mark_id"
          kind="marks"
          placeholder="Все марки"
          @update:model-value="filters.model_id = ''"
        />
      </FastDealCardField>
      <FastDealCardField label="Модель" for-id="fast-deal-table-model">
        <FastDealCardLookupSelect
          id="fast-deal-table-model"
          v-model="filters.model_id"
          kind="models"
          placeholder="Все модели"
          :params="{ mark_id: filters.mark_id || undefined }"
        />
      </FastDealCardField>
      <div class="col-span-2 lg:col-span-4 flex gap-2">
        <button type="submit" class="btn-primary text-sm px-3 py-2" :disabled="loading">Найти</button>
        <button type="button" class="btn-outline text-sm px-3 py-2" :disabled="loading" @click="resetFilters">Сбросить</button>
      </div>
    </form>

    <div class="overflow-x-auto rounded-lg border border-gray-200">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 text-left text-gray-600">
          <tr>
            <th scope="col" class="px-3 py-2 w-10"><span class="sr-only">Выбор</span></th>
            <th scope="col" class="px-3 py-2">Техника</th>
            <th scope="col" class="px-3 py-2">VIN</th>
            <th scope="col" class="px-3 py-2">Склад</th>
            <th scope="col" class="px-3 py-2 text-right">Цена</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-if="loading">
            <td colspan="5" class="px-3 py-6 text-center text-gray-500">Загрузка…</td>
          </tr>
          <tr v-else-if="failed">
            <td colspan="5" class="px-3 py-6 text-center text-red-600" role="alert">
              {{ failed }}
              <button type="button" class="underline ml-1" @click="load">Повторить</button>
            </td>
          </tr>
          <tr v-else-if="!rows.length">
            <td colspan="5" class="px-3 py-6 text-center text-gray-500">По заданным фильтрам техника не найдена</td>
          </tr>
          <template v-else>
           <template v-for="row in rows" :key="row.id">
            <tr :class="rowBlocked(row) ? 'bg-gray-50 text-gray-400' : 'hover:bg-gray-50'">
              <td class="px-3 py-2 align-top">
                <input
                  :type="multiple ? 'checkbox' : 'radio'"
                  :checked="!!selected[row.id]"
                  :disabled="!!rowBlocked(row) || busy"
                  :aria-label="`Выбрать ${row.title}`"
                  class="text-blue-600"
                  @change="toggle(row)"
                />
              </td>
              <td class="px-3 py-2 align-top">
                <span class="block" :class="rowBlocked(row) ? '' : 'text-gray-900'">{{ row.title }}</span>
                <span v-if="rowBlocked(row)" class="block text-xs text-red-600">{{ rowBlocked(row) }}</span>
              </td>
              <td class="px-3 py-2 align-top font-mono">{{ row.vin || '—' }}</td>
              <td class="px-3 py-2 align-top">{{ row.warehouseName || '—' }}</td>
              <td class="px-3 py-2 align-top text-right tabular-nums">
                {{ row.priceOnRequest ? 'По запросу' : formatMoney(row.price) }}
              </td>
            </tr>
            <tr v-if="selected[row.id] && (row.requiresManualVin || row.priceOnRequest)" class="bg-blue-50">
              <td></td>
              <td colspan="4" class="px-3 py-3">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <FastDealCardField
                    v-if="row.requiresManualVin"
                    label="VIN единицы"
                    required
                    hint="Объявление без VIN или «под заказ»: единица не резервируется"
                    :error="rowErrors[row.id]?.vin"
                  >
                    <input
                      v-model="extras[row.id].vin"
                      type="text"
                      maxlength="32"
                      autocomplete="off"
                      class="input-field font-mono uppercase"
                      :class="rowErrors[row.id]?.vin ? 'border-red-500' : ''"
                      :aria-label="`VIN: ${row.title}`"
                    />
                  </FastDealCardField>
                  <FastDealCardField
                    v-if="row.priceOnRequest"
                    label="Согласованная цена, ₽"
                    required
                    :error="rowErrors[row.id]?.price"
                  >
                    <input
                      v-model="extras[row.id].price"
                      type="text"
                      inputmode="decimal"
                      autocomplete="off"
                      class="input-field tabular-nums"
                      :class="rowErrors[row.id]?.price ? 'border-red-500' : ''"
                      :aria-label="`Цена: ${row.title}`"
                    />
                  </FastDealCardField>
                </div>
              </td>
            </tr>
           </template>
          </template>
        </tbody>
      </table>
    </div>

    <div v-if="total > pageSize" class="flex items-center justify-between text-sm text-gray-600">
      <span>Показано {{ rangeFrom }}–{{ rangeTo }} из {{ total }}</span>
      <div class="flex gap-2">
        <button type="button" class="btn-outline text-sm px-3 py-1.5" :disabled="loading || page <= 1" @click="goTo(page - 1)">Назад</button>
        <button type="button" class="btn-outline text-sm px-3 py-1.5" :disabled="loading || rangeTo >= total" @click="goTo(page + 1)">Далее</button>
      </div>
    </div>

    <FastDealCardError :error="error" />
    <div class="flex justify-end">
      <button type="button" class="btn-primary" :disabled="busy || !selectedCount" :aria-busy="busy" @click="pick">
        {{ busy ? 'Добавляем…' : multiple ? `Добавить выбранные (${selectedCount})` : actionLabel }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { parseFastDealError } from '../api/fastDealsApi'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import {
  formatMoney,
  isPositiveMoney,
  parseMoneyInput,
  toVehicleCandidate,
  type VehicleCandidate,
} from '../composables/fastDealCardFormat'
import type { AddVehicleBody } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'
import FastDealCardLookupSelect from './FastDealCardLookupSelect.vue'

const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/

const props = withDefaults(defineProps<{
  /** Several units may be added at once; a replacement takes exactly one. */
  multiple?: boolean
  busy?: boolean
  error?: ActionFailure | null
  actionLabel?: string
  /** VINs of the active positions: such a unit is already in the deal. */
  existingVins?: string[]
}>(), {
  multiple: true,
  busy: false,
  error: null,
  actionLabel: 'Выбрать',
  existingVins: () => [],
})

const emit = defineEmits<{ pick: [bodies: AddVehicleBody[]] }>()

const ctx = useFastDealCardContext()
const pageSize = 10
const page = ref(1)
const total = ref(0)
const rows = ref<VehicleCandidate[]>([])
const loading = ref(false)
const failed = ref('')
const filters = reactive({ vin: '', warehouse_id: '', mark_id: '', model_id: '' })
const selected = reactive<Record<string, boolean>>({})
const extras = reactive<Record<string, { vin: string; price: string }>>({})
const rowErrors = reactive<Record<string, { vin?: string; price?: string }>>({})
let generation = 0
// Every row seen so far, so a selection survives paging and filtering.
const seen = new Map<string, VehicleCandidate>()

const selectedCount = computed(() => Object.values(selected).filter(Boolean).length)
const rangeFrom = computed(() => (total.value ? (page.value - 1) * pageSize + 1 : 0))
const rangeTo = computed(() => Math.min(page.value * pageSize, total.value))

/** Why a row cannot be chosen: already in this deal, or the server's reason. */
function rowBlocked(row: VehicleCandidate): string {
  if (row.vin && props.existingVins.includes(row.vin)) return 'Уже добавлена в сделку'
  return row.selectable ? '' : row.reason || 'Недоступна для регистрации сделки'
}

async function load() {
  const current = ++generation
  loading.value = true
  failed.value = ''
  try {
    const query: { vin?: string; warehouse_id?: string; mark_id?: string; model_id?: string; page: number; page_size: number } = {
      page: page.value,
      page_size: pageSize,
    }
    if (filters.vin.trim()) query.vin = filters.vin.trim().toUpperCase()
    if (filters.warehouse_id) query.warehouse_id = filters.warehouse_id
    if (filters.mark_id) query.mark_id = filters.mark_id
    if (filters.model_id) query.model_id = filters.model_id
    const response = await ctx.api.vehicleCandidates(query)
    if (current !== generation) return
    rows.value = response.items.map(toVehicleCandidate).filter((item): item is VehicleCandidate => item !== null)
    total.value = response.total
    for (const row of rows.value) {
      extras[row.id] ??= { vin: '', price: '' }
      seen.set(row.id, row)
    }
  } catch (error) {
    if (current === generation) {
      rows.value = []
      total.value = 0
      failed.value = parseFastDealError(error).detail
    }
  } finally {
    if (current === generation) loading.value = false
  }
}

function applyFilters() {
  page.value = 1
  void load()
}

function resetFilters() {
  filters.vin = ''
  filters.warehouse_id = ''
  filters.mark_id = ''
  filters.model_id = ''
  applyFilters()
}

function goTo(next: number) {
  page.value = next
  void load()
}

function toggle(row: VehicleCandidate) {
  const was = !!selected[row.id]
  if (!props.multiple) {
    for (const key of Object.keys(selected)) delete selected[key]
  }
  if (was) delete selected[row.id]
  else selected[row.id] = true
}

function pick() {
  const bodies: AddVehicleBody[] = []
  let valid = true
  for (const key of Object.keys(rowErrors)) delete rowErrors[key]
  // Selected rows may sit on pages that are not shown now; their inputs are kept in `extras`.
  for (const row of seen.values()) {
    if (!selected[row.id]) continue
    const body: AddVehicleBody = { vehicle_source_type: 'product', product_id: row.id }
    const errors: { vin?: string; price?: string } = {}
    if (row.requiresManualVin) {
      const typed = extras[row.id].vin.trim().toUpperCase()
      if (VIN_PATTERN.test(typed)) body.vin = typed
      else errors.vin = 'VIN — 17 символов: латинские буквы (кроме I, O, Q) и цифры'
    }
    if (row.priceOnRequest) {
      const parsed = parseMoneyInput(extras[row.id].price)
      if (parsed !== null && isPositiveMoney(parsed)) body.price = parsed
      else errors.price = 'Укажите согласованную цену, например 2500000.00'
    }
    if (errors.vin || errors.price) {
      rowErrors[row.id] = errors
      valid = false
    } else {
      bodies.push(body)
    }
  }
  if (valid && bodies.length) emit('pick', bodies)
}

// Units that became positions meanwhile (a partly failed batch) leave the selection.
watch(() => props.existingVins, () => {
  for (const row of seen.values()) {
    if (selected[row.id] && rowBlocked(row)) delete selected[row.id]
  }
})

onMounted(load)
</script>
