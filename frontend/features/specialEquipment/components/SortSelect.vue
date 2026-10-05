<template>
  <label class="min-w-0 items-center gap-2 text-sm font-medium text-storefront-label">
    <span class="sr-only">Сортировка</span>
    <select
      :value="value"
      class="h-12 w-full min-w-0 rounded-lg border border-storefront-border bg-storefront-surface px-3 pr-9 text-sm font-medium text-storefront-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus lg:h-11 storefront-control"
      @change="$emit('change', ($event.target as HTMLSelectElement).value as SpecialEquipmentSort)"
    >
      <option v-for="option in options" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  </label>
</template>

<script setup lang="ts">
import { specialEquipmentSortOptions } from '../sortOptions'
import type { SpecialEquipmentSort, SpecialEquipmentUsageMetric } from '../types'

const props = defineProps<{
  value: SpecialEquipmentSort
  usageMetric: SpecialEquipmentUsageMetric | null
}>()
defineEmits<{ change: [value: SpecialEquipmentSort] }>()
const options = computed(() => specialEquipmentSortOptions(props.usageMetric))
</script>
