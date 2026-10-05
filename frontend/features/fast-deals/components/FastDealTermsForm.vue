<template>
  <Modal
    :show="true"
    title="Условия лизинга"
    size="2xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-terms-form" class="space-y-5" novalidate @submit.prevent="submit">
      <p class="text-sm text-gray-600">
        Стоимость техники по сделке: <strong>{{ formatMoney(deal.vehicles_total) }}</strong>.
        Аванс задаётся в рублях <em>или</em> в процентах — второе значение рассчитывается автоматически.
      </p>

      <fieldset class="space-y-3">
        <legend class="text-sm font-medium text-gray-700 mb-1">Аванс</legend>
        <div class="flex gap-6 text-sm">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input v-model="mode" type="radio" value="amount" class="text-blue-600" :disabled="ctx.busy.value" />
            В рублях
          </label>
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input v-model="mode" type="radio" value="percent" class="text-blue-600" :disabled="ctx.busy.value" />
            В процентах
          </label>
        </div>
        <FastDealCardField
          v-if="mode === 'amount'"
          label="Аванс, ₽"
          required
          for-id="fast-deal-down-payment"
          :error="errors.down_payment"
        >
          <input
            id="fast-deal-down-payment"
            v-model="downAmount"
            type="text"
            inputmode="decimal"
            autocomplete="off"
            class="input-field tabular-nums"
            :class="errors.down_payment ? 'border-red-500' : ''"
            :disabled="ctx.busy.value"
            placeholder="Например, 500000.00"
          />
        </FastDealCardField>
        <FastDealCardField
          v-else
          label="Аванс, %"
          required
          for-id="fast-deal-down-percent"
          :error="errors.down_payment_percent"
          :hint="percentHint"
        >
          <input
            id="fast-deal-down-percent"
            v-model="downPercent"
            type="text"
            inputmode="decimal"
            autocomplete="off"
            class="input-field tabular-nums"
            :class="errors.down_payment_percent ? 'border-red-500' : ''"
            :disabled="ctx.busy.value"
            placeholder="Например, 20"
          />
        </FastDealCardField>
      </fieldset>

      <FastDealCardField
        label="Срок лизинга, мес."
        required
        for-id="fast-deal-term"
        hint="От 12 до 84 месяцев"
        :error="errors.lease_term_months"
      >
        <input
          id="fast-deal-term"
          v-model="termText"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          class="input-field"
          :class="errors.lease_term_months ? 'border-red-500' : ''"
          :disabled="ctx.busy.value"
        />
      </FastDealCardField>

      <div class="space-y-2">
        <label class="inline-flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="manualPayment" type="checkbox" class="rounded text-blue-600" :disabled="ctx.busy.value" />
          Указать ежемесячный платёж вручную
        </label>
        <FastDealCardField
          v-if="manualPayment"
          label="Ежемесячный платёж, ₽"
          required
          for-id="fast-deal-monthly"
          :error="errors.monthly_payment"
          :hint="calculatedHint"
        >
          <input
            id="fast-deal-monthly"
            v-model="paymentText"
            type="text"
            inputmode="decimal"
            autocomplete="off"
            class="input-field tabular-nums"
            :class="errors.monthly_payment ? 'border-red-500' : ''"
            :disabled="ctx.busy.value"
          />
        </FastDealCardField>
        <p v-else class="text-xs text-gray-500">
          Платёж рассчитывается автоматически по ставкам калькулятора.
        </p>
        <p v-if="errors.monthly_payment && !manualPayment" role="alert" class="text-xs text-red-600">{{ errors.monthly_payment }}</p>
      </div>

      <FastDealCardField
        label="Выкупной платёж, ₽"
        for-id="fast-deal-buyout"
        hint="Не обязателен; по умолчанию 0"
        :error="errors.buyout_amount"
      >
        <input
          id="fast-deal-buyout"
          v-model="buyoutText"
          type="text"
          inputmode="decimal"
          autocomplete="off"
          class="input-field tabular-nums"
          :class="errors.buyout_amount ? 'border-red-500' : ''"
          :disabled="ctx.busy.value"
        />
      </FastDealCardField>

      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="submit" form="fast-deal-terms-form" class="btn-primary" :disabled="ctx.busy.value" :aria-busy="ctx.busy.value">
        {{ ctx.busy.value ? 'Сохраняем…' : 'Сохранить условия' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import {
  formatMoney,
  moneyToInput,
  parseMoneyInput,
  parsePercentInput,
  parseTermInput,
  percentOfMoney,
} from '../composables/fastDealCardFormat'
import type { FastDealCard, LeasingTermsBody } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const props = defineProps<{ deal: FastDealCard }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const initial = props.deal.requested_terms

const mode = ref<'amount' | 'percent'>(initial.down_payment_mode === 'percent' ? 'percent' : 'amount')
const downAmount = ref(moneyToInput(initial.down_payment))
const downPercent = ref(moneyToInput(initial.down_payment_percent))
const termText = ref(initial.lease_term_months != null ? String(initial.lease_term_months) : '')
const manualPayment = ref(initial.monthly_payment_is_manual === true)
const paymentText = ref(initial.monthly_payment_is_manual ? moneyToInput(initial.monthly_payment) : '')
const buyoutText = ref(moneyToInput(initial.buyout_amount))

const errors = reactive<Record<string, string>>({})
const serverError = ref<ActionFailure | null>(null)

const FIELDS = ['down_payment', 'down_payment_percent', 'lease_term_months', 'monthly_payment', 'buyout_amount']
const generalError = computed(() => (serverError.value && !(serverError.value.field && FIELDS.includes(serverError.value.field)) ? serverError.value : null))

const percentHint = computed(() => {
  const rubles = percentOfMoney(props.deal.vehicles_total, parsePercentInput(downPercent.value))
  return rubles ? `≈ ${formatMoney(rubles)} от стоимости техники` : 'До 49% стоимости техники'
})
const calculatedHint = computed(() =>
  initial.calculated_monthly_payment ? `Расчётный платёж: ${formatMoney(initial.calculated_monthly_payment)}` : '',
)

function validate(): LeasingTermsBody | null {
  for (const key of Object.keys(errors)) delete errors[key]
  const body: Partial<LeasingTermsBody> = {}

  if (mode.value === 'amount') {
    const amount = parseMoneyInput(downAmount.value)
    if (amount === null) errors.down_payment = 'Укажите аванс в рублях, например 500000.00'
    else body.down_payment = amount
  } else {
    const percent = parsePercentInput(downPercent.value)
    if (percent === null) errors.down_payment_percent = 'Укажите аванс в процентах от 0 до 100'
    else body.down_payment_percent = percent
  }

  const term = parseTermInput(termText.value)
  if (term === null || term < 12 || term > 84) errors.lease_term_months = 'Срок лизинга — целое число от 12 до 84 месяцев'
  else body.lease_term_months = term

  if (manualPayment.value) {
    const payment = parseMoneyInput(paymentText.value)
    if (payment === null) errors.monthly_payment = 'Укажите ежемесячный платёж, например 150000.00'
    else body.monthly_payment = payment
  }

  if (buyoutText.value.trim()) {
    const buyout = parseMoneyInput(buyoutText.value)
    if (buyout === null) errors.buyout_amount = 'Укажите выкупной платёж, например 100000.00'
    else body.buyout_amount = buyout
  }

  return Object.keys(errors).length > 0 ? null : (body as LeasingTermsBody)
}

async function submit() {
  serverError.value = null
  const body = validate()
  if (!body) return
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.terms(card.id, etag, body))
  if (result.ok) {
    emit('close')
    return
  }
  serverError.value = result.error
  const field = result.error.field
  if (field && FIELDS.includes(field)) {
    errors[field] = result.error.detail
    // Without calculator rates the payment can only be typed in.
    if (field === 'monthly_payment') manualPayment.value = true
  }
}
</script>
