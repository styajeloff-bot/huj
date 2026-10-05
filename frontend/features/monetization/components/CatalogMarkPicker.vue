<template>
  <div>
    <SearchableDropdown :anchor-to-control="true" :loading="loading"
      :model-value="modelValue?.id ?? null"
      :items="options"
      :label="label"
      :placeholder="placeholder"
      :clear-label="placeholder"
      label-key="name"
      value-key="id"
      search-placeholder="Найти марку..."
      :remote="!loaded" :empty-label="loaded && !items.length ? 'В справочнике пока нет марок' : 'Ничего не найдено'"
      :error="!!error"
      @search="load"
      @update:model-value="choose"
    />
    <p v-if="loading" class="muted" role="status">Загрузка марок…</p>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import type { CatalogMark } from '../types'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
const props = withDefaults(defineProps<{ api: MonetizationApi; modelValue: CatalogMark | null; label?: string; placeholder?: string }>(), { label: 'Марка', placeholder: 'Все марки' })
const emit = defineEmits<{ 'update:modelValue': [value: CatalogMark | null] }>()
const items = ref<CatalogMark[]>([])
const loaded = ref(false)
const loading = ref(false)
const error = ref('')
const marks = computed(() => props.modelValue && !items.value.some(item => item.id === props.modelValue?.id) ? [props.modelValue, ...items.value] : items.value)
const options = computed(() => marks.value.map(item => ({ ...item })))
let generation = 0
async function load() {
  if (loaded.value || loading.value) return
  const token = ++generation
  loading.value = true; error.value = ''
  try { const result = await props.api.marks(); if (token === generation) { items.value = result.marks; loaded.value = true } }
  catch (failure) { if (token === generation) error.value = errorMessage(failure) }
  finally { if (token === generation) loading.value = false }
}
function choose(value: unknown) {
  if (value === null) { emit('update:modelValue', null); return }
  const selected = marks.value.find(item => item.id === value)
  if (selected) emit('update:modelValue', selected)
}
onBeforeUnmount(() => { ++generation })
</script>
