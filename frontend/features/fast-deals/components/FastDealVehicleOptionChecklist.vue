<template>
  <section class="space-y-2" :aria-label="title">
    <div class="flex items-center justify-between gap-3">
      <h3 class="text-sm font-semibold text-gray-900">{{ title }}</h3>
      <span class="text-xs text-gray-500">Выбрано: {{ selected.length }}</span>
    </div>
    <input
      v-if="searchable"
      v-model="filter"
      type="search"
      class="input-field"
      placeholder="Фильтр списка"
      :aria-label="`Фильтр: ${title}`"
      :disabled="disabled"
    />
    <p v-if="loading" class="text-sm text-gray-500">Загрузка…</p>
    <p v-else-if="!entries.length" class="text-sm text-gray-500">Справочник пуст</p>
    <div v-else class="max-h-44 overflow-y-auto rounded-lg border border-gray-200 p-2 grid grid-cols-2 gap-x-4 gap-y-1">
      <label v-for="name in visible" :key="name" class="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" class="rounded text-blue-600" :checked="selected.includes(name)" :disabled="disabled" @change="toggle(name)" />
        <span class="truncate" :title="name">{{ name }}</span>
      </label>
      <p v-if="!visible.length" class="col-span-2 text-sm text-gray-500">Ничего не найдено</p>
    </div>
    <p v-if="error" role="alert" class="text-xs text-red-600">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  title: string
  /** Names offered by the directory. */
  catalog: string[]
  selected: string[]
  searchable?: boolean
  loading?: boolean
  disabled?: boolean
  error?: string | null
}>()

const emit = defineEmits<{ 'update:selected': [value: string[]] }>()

const filter = ref('')

// Values stored earlier that the directory no longer offers must stay visible and removable.
const entries = computed(() => [...props.catalog, ...props.selected.filter(name => !props.catalog.includes(name))])
const visible = computed(() => {
  const text = filter.value.trim().toLowerCase()
  return text ? entries.value.filter(name => name.toLowerCase().includes(text)) : entries.value
})

function toggle(name: string) {
  emit('update:selected', props.selected.includes(name) ? props.selected.filter(value => value !== name) : [...props.selected, name])
}
</script>
