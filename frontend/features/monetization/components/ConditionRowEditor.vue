<template>
  <div class="condition-row">
    <h4>{{ income ? 'Доход' : 'Расход' }}</h4>
    <p class="condition-caption">{{ income ? 'Кто получает доход в этой связке.' : 'Кто несёт расход в этой связке.' }}</p>
    <label><span class="visually-hidden">Участник {{ income ? 'дохода' : 'расхода' }}</span><select class="select-field" :value="modelValue.participant_type" @change="patch({ participant_type: ($event.target as HTMLSelectElement).value as Participant })"><option v-for="(label, value) in participantLabels" :key="value" :value="value">{{ label }}</option><option disabled value="agent">Агент</option></select></label>
    <div class="condition-calculation">
      <SearchableDropdown :model-value="modelValue.base_type" :items="baseOptions" label="База расчёта" label-key="name" value-key="id" :allow-clear="false" :searchable="false" :anchor-to-control="true" @update:model-value="changeBase" />
      <p v-if="modelValue.base_type === 'expense_amount'" class="condition-hint">От суммы расхода в этой связке.</p>
      <div class="condition-grid">
        <div><p class="field-label">Тип расчёта</p><div class="calculation-options" role="group" aria-label="Тип расчёта"><button type="button" :aria-pressed="modelValue.calc_type === 'percent'" :disabled="modelValue.base_type === 'none'" @click="patch({ calc_type: 'percent' })">%</button><button type="button" :aria-pressed="modelValue.calc_type === 'amount'" :disabled="modelValue.base_type === 'none' || modelValue.base_type === 'property_value'" @click="patch({ calc_type: 'amount' })">₽</button></div></div>
        <label><span>Значение ({{ modelValue.calc_type === 'percent' ? '%' : '₽' }})</span><input class="input-field" :value="modelValue.value" inputmode="decimal" required placeholder="0" @input="patch({ value: ($event.target as HTMLInputElement).value.replace(',', '.') })" /></label>
      </div>
      <div class="condition-grid">
        <label><span class="visually-hidden">Минимум, ₽</span><input class="input-field" :value="modelValue.min ?? ''" inputmode="decimal" placeholder="Мин, ₽" @input="patch({ min: ($event.target as HTMLInputElement).value.replace(',', '.') || null })" /></label>
        <label><span class="visually-hidden">Максимум, ₽</span><input class="input-field" :value="modelValue.max ?? ''" inputmode="decimal" placeholder="Макс, ₽" @input="patch({ max: ($event.target as HTMLInputElement).value.replace(',', '.') || null })" /></label>
      </div>
      <label class="check"><input type="checkbox" :checked="modelValue.vat_excluded" @change="patch({ vat_excluded: ($event.target as HTMLInputElement).checked })" /> Не включён НДС</label>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import type { ConditionRow, Participant } from '../types'
import { participantLabels } from '../editor'
const props = defineProps<{ modelValue: ConditionRow; income: boolean; expense?: ConditionRow }>()
const emit = defineEmits<{ 'update:modelValue': [row: ConditionRow] }>()
const baseOptions = computed(() => [
  { id: 'property_value', name: 'Стоимость имущества по договору' },
  ...(props.income ? [{ id: 'expense_amount', name: 'Сумма расхода' }] : []),
  { id: 'none', name: 'Без базы (фиксированная сумма)' },
])
function patch(value: Partial<ConditionRow>) { emit('update:modelValue', { ...props.modelValue, ...value }) }
function changeBase(value: unknown) {
  if (value !== 'property_value' && value !== 'none' && !(value === 'expense_amount' && props.income && props.expense)) return
  patch({ base_type: value, expense_ref: props.income ? props.expense!.local_id : null, ...(value === 'none' ? { calc_type: 'amount' } : value === 'property_value' ? { calc_type: 'percent' } : {}) })
}
</script>
