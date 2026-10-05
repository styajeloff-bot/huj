<template>
  <section class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-terms-title">
    <div class="flex items-center justify-between gap-3 mb-4">
      <h2 id="fast-deal-terms-title" class="text-lg font-semibold text-gray-900">Условия лизинга</h2>
      <button
        v-if="ctx.canEditStructure.value"
        type="button"
        class="btn-outline text-sm px-3 py-1.5"
        @click="editing = true"
      >
        {{ complete ? 'Изменить' : 'Задать условия' }}
      </button>
    </div>

    <p v-if="!complete" class="text-sm text-gray-600">
      Условия лизинга ещё не заданы.
      <span v-if="ctx.canEditStructure.value">Без них сделку нельзя отправить.</span>
    </p>

    <dl class="grid grid-cols-[1fr_auto] gap-x-6 gap-y-2 text-sm">
      <dt class="text-gray-500">Стоимость техники</dt>
      <dd class="text-right font-medium text-gray-900 tabular-nums">{{ formatMoney(deal.vehicles_total) }}</dd>

      <template v-if="complete">
        <dt class="text-gray-500">
          Аванс
          <span v-if="terms.down_payment_mode" class="block text-xs text-gray-400">
            {{ terms.down_payment_mode === 'percent' ? 'задан в процентах' : 'задан в рублях' }}
          </span>
        </dt>
        <dd class="text-right text-gray-900 tabular-nums">
          {{ formatMoney(terms.down_payment) }}
          <span class="block text-xs text-gray-500">{{ formatPercent(terms.down_payment_percent) }}</span>
        </dd>

        <dt class="text-gray-500">Сумма финансирования</dt>
        <dd class="text-right text-gray-900 tabular-nums">{{ formatMoney(financing) }}</dd>

        <dt class="text-gray-500">Срок лизинга</dt>
        <dd class="text-right text-gray-900">{{ terms.lease_term_months }} мес.</dd>

        <dt class="text-gray-500">
          Ежемесячный платёж
          <span v-if="terms.monthly_payment_is_manual" class="block text-xs text-amber-700">введён вручную</span>
        </dt>
        <dd class="text-right text-gray-900 tabular-nums">
          {{ formatMoney(terms.monthly_payment) }}
          <span v-if="showCalculated" class="block text-xs text-gray-500">
            расчётный: {{ formatMoney(terms.calculated_monthly_payment) }}
          </span>
        </dd>

        <dt class="text-gray-500">Выкупной платёж</dt>
        <dd class="text-right text-gray-900 tabular-nums">{{ formatMoney(terms.buyout_amount ?? '0.00') }}</dd>

        <dt class="text-gray-500">Стоимость договора</dt>
        <dd class="text-right font-medium text-gray-900 tabular-nums">{{ formatMoney(terms.total_cost) }}</dd>
      </template>
    </dl>

    <div v-if="deal.final_terms" class="mt-6 border-t border-gray-100 pt-4" aria-label="Итоговые условия">
      <h3 class="text-sm font-semibold text-gray-900 mb-2">Итоговые условия</h3>
      <dl class="grid grid-cols-[1fr_auto] gap-x-6 gap-y-2 text-sm">
        <dt class="text-gray-500">Аванс</dt>
        <dd class="text-right text-gray-900 tabular-nums">
          {{ formatMoney(deal.final_terms.down_payment) }}
          <span class="block text-xs text-gray-500">{{ formatPercent(deal.final_terms.down_payment_percent) }}</span>
        </dd>
        <dt class="text-gray-500">Срок лизинга</dt>
        <dd class="text-right text-gray-900">{{ deal.final_terms.lease_term_months ?? '—' }} мес.</dd>
        <dt class="text-gray-500">Ежемесячный платёж</dt>
        <dd class="text-right text-gray-900 tabular-nums">{{ formatMoney(deal.final_terms.monthly_payment) }}</dd>
        <dt class="text-gray-500">Выкупной платёж</dt>
        <dd class="text-right text-gray-900 tabular-nums">{{ formatMoney(deal.final_terms.buyout_amount) }}</dd>
        <dt class="text-gray-500">Стоимость договора</dt>
        <dd class="text-right font-medium text-gray-900 tabular-nums">{{ formatMoney(deal.final_terms.total_cost) }}</dd>
        <template v-if="deal.confirmed_amount">
          <dt class="text-gray-500">Сумма сделки</dt>
          <dd class="text-right font-medium text-gray-900 tabular-nums">{{ formatMoney(deal.confirmed_amount) }}</dd>
        </template>
      </dl>
    </div>

    <FastDealTermsForm v-if="editing" :deal="deal" @close="editing = false" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import {
  formatMoney,
  formatPercent,
  requestedFinancingAmount,
  sameDecimal,
  termsAreComplete,
} from '../composables/fastDealCardFormat'
import type { FastDealCard } from '../types'
import FastDealTermsForm from './FastDealTermsForm.vue'

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const editing = ref(false)

const terms = computed(() => props.deal.requested_terms)
const complete = computed(() => termsAreComplete(props.deal))
const financing = computed(() => requestedFinancingAmount(props.deal))
/** A manual payment is shown beside the recomputed one whenever they differ. */
const showCalculated = computed(
  () => terms.value.monthly_payment_is_manual === true
    && terms.value.calculated_monthly_payment != null
    && !sameDecimal(terms.value.monthly_payment, terms.value.calculated_monthly_payment),
)
</script>
