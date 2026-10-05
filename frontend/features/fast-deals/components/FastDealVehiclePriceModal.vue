<template>
  <Modal
    :show="true"
    title="Скидка или наценка"
    :subtitle="vehicleTitle(vehicle)"
    size="lg"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-price-form" class="space-y-4" novalidate @submit.prevent="submit">
      <dl class="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm">
        <dt class="text-gray-500">Базовая цена</dt>
        <dd class="text-right tabular-nums">{{ formatMoney(vehicle.base_price) }}</dd>
        <dt class="text-gray-500">Итоговая цена сейчас</dt>
        <dd class="text-right font-medium tabular-nums">{{ formatMoney(vehicle.final_price) }}</dd>
      </dl>

      <fieldset class="space-y-2">
        <legend class="text-sm font-medium text-gray-700 mb-1">Корректировка цены</legend>
        <label class="flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="type" type="radio" value="" class="text-blue-600" :disabled="ctx.busy.value" />
          Без корректировки
        </label>
        <label v-for="option in types" :key="option" class="flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="type" type="radio" :value="option" class="text-blue-600" :disabled="ctx.busy.value" />
          {{ option === 'discount' ? 'Скидка' : 'Наценка' }}
        </label>
        <p v-if="types.length === 1" class="text-xs text-gray-500">В сделке «дилер → ЛК» доступна только скидка.</p>
      </fieldset>

      <FastDealCardField
        v-if="type"
        :label="type === 'discount' ? 'Размер скидки, ₽' : 'Размер наценки, ₽'"
        required
        for-id="fast-deal-adjustment-amount"
        :error="amountError"
      >
        <input
          id="fast-deal-adjustment-amount"
          v-model="amount"
          type="text"
          inputmode="decimal"
          autocomplete="off"
          class="input-field tabular-nums"
          :class="amountError ? 'border-red-500' : ''"
          :disabled="ctx.busy.value"
        />
      </FastDealCardField>

      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="submit" form="fast-deal-price-form" class="btn-primary" :disabled="ctx.busy.value || !changed" :aria-busy="ctx.busy.value">
        {{ ctx.busy.value ? 'Сохраняем…' : 'Сохранить' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { formatMoney, isPositiveMoney, parseMoneyInput, sameDecimal, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealVehicle } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const props = defineProps<{ vehicle: FastDealVehicle }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const types = ctx.adjustmentTypes.value

const type = ref<'' | 'discount' | 'markup'>(props.vehicle.adjustment_type ?? '')
const amount = ref(props.vehicle.adjustment_amount ?? '')
const localError = ref('')
const serverError = ref<ActionFailure | null>(null)

const changed = computed(() => {
  const before = props.vehicle.adjustment_type ?? ''
  if (before !== type.value) return true
  return type.value !== '' && !sameDecimal(parseMoneyInput(amount.value), props.vehicle.adjustment_amount)
})

const amountError = computed(() => localError.value || (serverError.value?.field ? serverError.value.detail : ''))
const generalError = computed(() => (serverError.value && !serverError.value.field ? serverError.value : null))

async function submit() {
  serverError.value = null
  localError.value = ''
  let body: { type: 'discount' | 'markup' | null; amount: string | null } = { type: null, amount: null }
  if (type.value) {
    const parsed = parseMoneyInput(amount.value)
    if (parsed === null || !isPositiveMoney(parsed)) {
      localError.value = 'Укажите положительную сумму, например 50000.00'
      return
    }
    body = { type: type.value, amount: parsed }
  }
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.priceAdjustment(card.id, props.vehicle.id, etag, body))
  if (result.ok) emit('close')
  else serverError.value = result.error
}
</script>
