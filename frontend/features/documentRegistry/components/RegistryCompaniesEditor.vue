<template>
  <div class="dr-companies">
    <label class="dr-check"><input type="checkbox" :checked="modelValue.platform_ml" @change="setPlatform" /> Платформа МЛ</label>
    <div class="dr-grid dr-grid-three">
      <RegistryCompanyPicker v-for="role in roles" :key="role" :api="api" :role="role" :label="labels[role]" :selected-ids="modelValue[keys[role]]" :companies="(modelValue.companies ?? []).filter(item => item.role === role)" @change="(ids, companies) => update(role, ids, companies)" />
    </div>
  </div>
</template>
<script setup lang="ts">
import type { DocumentRegistryApi } from '../api'
import type { CompanyRole, CompanySelection, RegistryCompany } from '../types'
import RegistryCompanyPicker from './RegistryCompanyPicker.vue'
const props = defineProps<{ api: DocumentRegistryApi; modelValue: CompanySelection }>()
const emit = defineEmits<{ 'update:modelValue': [value: CompanySelection] }>()
const roles = ['leasing_company', 'distributor', 'dealer'] as const
const keys = { leasing_company: 'leasing_company_ids', distributor: 'distributor_company_ids', dealer: 'dealer_company_ids' } as const
const labels = { leasing_company: 'Лизинговые компании', distributor: 'Дистрибьюторы', dealer: 'Дилеры' }
function update(role: CompanyRole, ids: string[], companies: RegistryCompany[]) { emit('update:modelValue', { ...props.modelValue, [keys[role]]: ids, companies: [...(props.modelValue.companies ?? []).filter(item => item.role !== role), ...companies] }) }
function setPlatform(event: Event) { emit('update:modelValue', { ...props.modelValue, platform_ml: (event.target as HTMLInputElement).checked }) }
</script>
