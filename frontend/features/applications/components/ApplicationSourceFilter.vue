<template>
  <fieldset data-testid="application-source-filter">
    <legend class="mb-2 text-sm font-medium text-[color:var(--storefront-label,#374151)]">Источник заявки</legend>
    <div class="flex flex-wrap gap-x-4 gap-y-2">
      <label v-for="option in applicationSourceOptions" :key="option.value" class="inline-flex items-center gap-2 text-sm text-[color:var(--storefront-text,#374151)]">
        <input
          type="checkbox"
          class="h-4 w-4 rounded border-gray-300 accent-blue-600"
          :value="option.value"
          :checked="modelValue.includes(option.value)"
          @change="toggle(option.value)"
        >
        {{ option.label }}
      </label>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import { applicationSourceOptions, type SiteApplicationSourceType } from '../sourceType'

const props = defineProps<{ modelValue: SiteApplicationSourceType[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: SiteApplicationSourceType[]] }>()

const toggle = (source: SiteApplicationSourceType) => {
  emit('update:modelValue', props.modelValue.includes(source)
    ? props.modelValue.filter(value => value !== source)
    : [...props.modelValue, source])
}
</script>
