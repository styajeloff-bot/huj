<template>
  <article class="condition-summary" :class="{ 'income-summary': income }">
    <h4>{{ participantLabels[row.participant_type] }}</h4>
    <dl>
      <div class="summary-base"><dt>БАЗА РАСЧЁТА</dt><dd>{{ baseLabel || bases[row.base_type] }}</dd></div>
      <div><dt>ТИП РАСЧЁТА</dt><dd><span class="source-badge">{{ row.calc_type === 'percent' ? 'Процент' : 'Фиксированная сумма' }}</span></dd></div>
      <div><dt>ЗНАЧЕНИЕ</dt><dd class="summary-value">{{ row.calc_type === 'percent' ? formatPercent(row.value) : formatMoney(row.value) }}</dd></div>
    </dl>
    <p class="summary-bounds">Мин {{ row.min === null ? 'не задан' : formatMoney(row.min) }} · Макс {{ row.max === null ? 'не задан' : formatMoney(row.max) }}</p>
    <span class="badge" :class="row.vat_excluded ? 'inactive' : 'active'">{{ row.vat_excluded ? 'Без НДС' : 'С НДС' }}</span>
  </article>
</template>
<script setup lang="ts">
import type { SavedConditionRow } from '../types'
import { participantLabels } from '../editor'
import { formatMoney, formatPercent } from '../money'
defineProps<{ row: SavedConditionRow; baseLabel?: string; income?: boolean }>()
const bases = { property_value: 'Стоимость имущества по договору', expense_amount: 'Сумма расхода', none: 'Без базы (фиксированная сумма)' }
</script>
