<template>
  <div class="grid grid-cols-2 gap-2">
    <label>
      <span class="sr-only">{{ minLabel }}</span>
      <input
        :value="minValue"
        :type="integer ? 'number' : 'text'"
        :inputmode="integer ? 'numeric' : 'decimal'"
        :min="integer ? 0 : undefined"
        :step="integer ? 1 : undefined"
        autocomplete="off"
        placeholder="От"
        class="h-11 min-w-0 w-full rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
        @input="$emit('update:min-value', ($event.target as HTMLInputElement).value)"
        @blur="$emit('blur')"
      >
    </label>
    <label>
      <span class="sr-only">{{ maxLabel }}</span>
      <input
        :value="maxValue"
        :type="integer ? 'number' : 'text'"
        :inputmode="integer ? 'numeric' : 'decimal'"
        :min="integer ? 0 : undefined"
        :step="integer ? 1 : undefined"
        autocomplete="off"
        placeholder="До"
        class="h-11 min-w-0 w-full rounded-lg border border-storefront-border px-3 text-sm text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
        @input="$emit('update:max-value', ($event.target as HTMLInputElement).value)"
        @blur="$emit('blur')"
      >
    </label>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  minValue: string
  maxValue: string
  minLabel: string
  maxLabel: string
  integer?: boolean
}>()

defineEmits<{
  'update:min-value': [value: string]
  'update:max-value': [value: string]
  blur: []
}>()
</script>
