<template>
  <section class="space-y-2" :aria-label="title">
    <div class="flex items-center justify-between gap-3">
      <h3 class="text-sm font-semibold text-gray-900">{{ title }}</h3>
      <span v-if="rows.length" class="text-xs text-gray-500">Сумма: {{ formatMoney(sumOptionRows(rows)) }}</span>
    </div>

    <p v-if="!rows.length" class="text-sm text-gray-500">Не выбрано</p>
    <ul v-else class="space-y-2">
      <li v-for="(row, index) in rows" :key="row.code" class="rounded-lg border border-gray-200 p-3 space-y-2">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-medium text-gray-900">{{ row.name || row.code }}</p>
            <p class="text-xs text-gray-400 break-all">{{ row.code }}</p>
          </div>
          <button
            type="button"
            class="text-sm text-red-600 hover:text-red-700 shrink-0"
            :disabled="disabled"
            @click="remove(index)"
          >
            Убрать
          </button>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <FastDealCardField label="Цена, ₽" :error="priceError(row)">
            <input
              :value="row.price"
              type="text"
              inputmode="decimal"
              autocomplete="off"
              class="input-field tabular-nums"
              :class="priceError(row) ? 'border-red-500' : ''"
              :disabled="disabled"
              :aria-label="`Цена: ${row.name || row.code}`"
              @input="update(index, { price: ($event.target as HTMLInputElement).value })"
            />
          </FastDealCardField>
          <FastDealCardField label="Комментарий">
            <input
              :value="row.comment"
              type="text"
              maxlength="500"
              class="input-field"
              :disabled="disabled"
              :aria-label="`Комментарий: ${row.name || row.code}`"
              @input="update(index, { comment: ($event.target as HTMLInputElement).value })"
            />
          </FastDealCardField>
        </div>
      </li>
    </ul>

    <div class="flex items-center gap-2">
      <select v-model="pick" class="select-field flex-1" :disabled="disabled || loading" :aria-label="addLabel">
        <option value="">{{ loading ? 'Загрузка…' : addLabel }}</option>
        <option v-for="item in available" :key="lookupCode(item)" :value="lookupCode(item)">{{ lookupName(item) }}</option>
      </select>
      <button type="button" class="btn-outline text-sm px-3 py-2" :disabled="disabled || !pick" @click="add">Добавить</button>
    </div>
    <p v-if="error" role="alert" class="text-xs text-red-600">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  formatMoney,
  lookupCode,
  lookupName,
  parseMoneyInput,
  sumOptionRows,
  type OptionRow,
} from '../composables/fastDealCardFormat'
import type { LookupItem } from '../api/fastDealsApi'
import FastDealCardField from './FastDealCardField.vue'

const props = defineProps<{
  title: string
  addLabel: string
  rows: OptionRow[]
  catalog: LookupItem[]
  loading?: boolean
  disabled?: boolean
  error?: string | null
}>()

const emit = defineEmits<{ 'update:rows': [rows: OptionRow[]] }>()

const pick = ref('')
const available = computed(() => props.catalog.filter(item => !props.rows.some(row => row.code === lookupCode(item))))

const priceError = (row: OptionRow) => (parseMoneyInput(row.price) === null ? 'Укажите цену, например 15000.00' : '')

function add() {
  const item = props.catalog.find(candidate => lookupCode(candidate) === pick.value)
  if (!item) return
  const suggested = typeof item.price === 'string' ? parseMoneyInput(item.price) : null
  emit('update:rows', [...props.rows, { code: lookupCode(item), name: lookupName(item), price: suggested ?? '0.00', comment: '' }])
  pick.value = ''
}

function update(index: number, patch: Partial<OptionRow>) {
  emit('update:rows', props.rows.map((row, position) => (position === index ? { ...row, ...patch } : row)))
}

function remove(index: number) {
  emit('update:rows', props.rows.filter((_, position) => position !== index))
}
</script>
