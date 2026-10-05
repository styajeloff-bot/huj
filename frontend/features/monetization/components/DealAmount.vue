<template>
  <article class="deal-amount" :class="{ 'expense-amount': side === 'expense', 'platform-amount': row.participant_type === 'platform' }" :data-amount-id="row.id">
    <h4>{{ participantLabels[row.participant_type] }} ({{ side === 'expense' ? 'Расход' : 'Доход' }})</h4>
    <p v-if="companyName" class="muted">{{ companyName }}</p>
    <div class="deal-terms-columns" :class="{ 'has-new-terms': editing || row.has_new_conditions }">
      <div class="deal-original-terms">
        <p class="terms-heading">Исходные условия</p>
        <p v-if="row.original_calc_type === 'percent' && row.original_percent !== null" class="terms-percent">{{ formatPercent(row.original_percent, 2) }}</p>
        <p v-else class="terms-description">{{ row.original_calc_type === 'amount' ? 'Фиксированная сумма' : 'Исходная формула не сохранена' }}</p>
        <p v-if="row.original_calc_type === 'percent'" class="terms-base">{{ baseLabel }}</p>
        <strong>{{ formatMoney(row.original_amount, 2) }}</strong>
        <p class="amount-vat">{{ row.vat_excluded ? 'Без НДС' : 'С НДС' }}</p>
        <p v-if="row.clip === 'min' || row.clip === 'max'" class="clip-note">
          <template v-if="row.applied_limit != null">Расчётная сумма {{ formatMoney(row.raw_amount, 2) }} {{ row.clip === 'min' ? 'ниже минимума' : 'выше максимума' }} {{ formatMoney(row.applied_limit) }}. Применён {{ row.clip === 'min' ? 'минимум' : 'максимум' }} {{ formatMoney(row.applied_limit) }}.</template>
          <template v-else>Применено ограничение: {{ row.clip === 'min' ? 'минимум' : 'максимум' }}. Расчётная сумма: {{ formatMoney(row.raw_amount, 2) }}. Исходный итог после ограничения: {{ formatMoney(row.original_amount, 2) }}. Точный порог недоступен.</template>
        </p>
      </div>
      <div v-if="editing" class="deal-new-terms deal-terms-editor">
        <p class="terms-heading">Новые условия</p>
        <p class="terms-base">{{ row.original_calc_type === 'percent' ? baseLabel : 'Эквивалентный процент ' + baseLabel }}</p>
        <label :for="'term-percent-' + row.id">Процент</label>
        <input :id="'term-percent-' + row.id" class="input-field" inputmode="decimal" :value="editing.percent" :disabled="disabled || !positiveBase" :aria-invalid="!!editing.error" :aria-describedby="editing.error ? 'term-error-' + row.id : undefined" @input="change('percent', $event)" @blur="emit('normalize', 'percent')" />
        <p v-if="!positiveBase" class="terms-hint">Процент не рассчитывается: база отсутствует или равна нулю.</p>
        <label :for="'term-amount-' + row.id">Сумма, ₽</label>
        <input :id="'term-amount-' + row.id" class="input-field" inputmode="decimal" required :value="editing.amount" :disabled="disabled" :aria-invalid="!!editing.error" :aria-describedby="editing.error ? 'term-error-' + row.id : undefined" @input="change('amount', $event)" @blur="emit('normalize', 'amount')" />
        <p v-if="editing.error" :id="'term-error-' + row.id" class="error terms-error" role="alert">{{ editing.error }}</p>
        <p v-else class="terms-hint">Итого: {{ formatMoney(editing.finalAmount, 2) }}</p>
        <p class="terms-hint">{{ editing.inputMode === 'percent' ? 'Новый процент округляется до сотых.' : 'Сохраняется сумма; процент рассчитывается.' }}</p>
      </div>
      <div v-else-if="row.has_new_conditions" class="deal-new-terms">
        <p class="terms-heading">Новые условия</p>
        <p v-if="row.percent !== null" class="terms-percent">{{ formatPercent(row.percent, 2) }}</p>
        <p v-else class="terms-description">Процент не рассчитывается</p>
        <p class="terms-base">{{ row.input_mode === 'percent' ? baseLabel : 'Эквивалентный процент ' + baseLabel }}</p>
        <strong>{{ formatMoney(row.amount, 2) }}</strong>
        <p class="amount-vat">{{ row.vat_excluded ? 'Без НДС' : 'С НДС' }}</p>
      </div>
    </div>
  </article>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { AmountRow, TermsInputMode } from '../types'
import type { TermPreview } from '../dealTerms'
import { participantLabels } from '../editor'
import { formatMoney, formatPercent } from '../money'
const props = defineProps<{ row: AmountRow; side: 'expense' | 'income'; companyName?: string; editing?: TermPreview; disabled?: boolean }>()
const emit = defineEmits<{ change: [mode: TermsInputMode, value: string]; normalize: [mode: TermsInputMode] }>()
const baseLabel = computed(() => props.row.base_type === 'expense_amount' ? 'от расхода' : 'от стоимости имущества')
const positiveBase = computed(() => props.editing?.base !== null && props.editing?.base !== undefined && /[1-9]/.test(props.editing.base))
function change(mode: TermsInputMode, event: Event) { emit('change', mode, (event.target as HTMLInputElement).value) }
</script>
