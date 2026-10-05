<template>
  <div>
    <SearchableDropdown :anchor-to-control="true" :loading="loading"
      :model-value="modelValue?.id ?? null"
      :items="options"
      :label="label"
      :placeholder="placeholder"
      :clear-label="placeholder"
      label-key="label"
      value-key="id"
      search-placeholder="Название или ИНН"
      :remote="true"
      :disabled="disabled"
      :error="!!error"
      @search="search"
      @update:model-value="choose"
    />
    <p v-if="loading" class="muted" role="status">Загрузка компаний…</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import type { Company } from '../types'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
const props = withDefaults(defineProps<{ api: MonetizationApi; kind: 'leasing' | 'dealer' | 'distributor' | 'client'; modelValue: Company | null; label: string; placeholder?: string; disabled?: boolean; distributorCompanyId?: string; dealerCompanyId?: string }>(), { placeholder: 'Выберите компанию', disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: Company | null] }>()
const items = ref<Company[]>([])
const loading = ref(false)
const error = ref('')
const companies = computed(() => props.modelValue && !items.value.some(item => item.id === props.modelValue?.id) ? [props.modelValue, ...items.value] : items.value)
const options = computed(() => companies.value.map(item => ({ ...item, label: `${item.name} · ИНН ${item.inn || 'не указан'}` })))
let generation = 0
let searchQuery = ''
async function search(query: string) {
  searchQuery = query
  if (props.disabled) return
  const token = ++generation
  loading.value = true; error.value = ''; items.value = []
  try {
    const result = await props.api.companies(props.kind, query.trim(), {
      distributor_company_id: props.distributorCompanyId,
      dealer_company_id: props.dealerCompanyId,
    })
    if (token === generation) items.value = result.items
  }
  catch (failure) { if (token === generation) error.value = errorMessage(failure) }
  finally { if (token === generation) loading.value = false }
}
watch(
  [() => props.kind, () => props.distributorCompanyId, () => props.dealerCompanyId],
  () => {
    ++generation
    items.value = []; error.value = ''; loading.value = false
    void search(searchQuery)
  },
  { flush: 'sync' },
)
function choose(value: unknown) {
  if (value === null) { emit('update:modelValue', null); return }
  const selected = companies.value.find(item => item.id === value)
  if (selected) emit('update:modelValue', selected)
}
onBeforeUnmount(() => { ++generation })
</script>
