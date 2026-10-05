<template>
  <div data-testid="application-kind-filter">
    <label :for="selectId" class="mb-1 block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Вид заявки</label>
    <select
      :id="selectId"
      :value="modelValue"
      class="storefront-control select-field"
      @change="onChange"
    >
      <option value="">Все заявки</option>
      <option v-for="option in APPLICATION_KIND_OPTIONS" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { APPLICATION_KIND_OPTIONS, type ApplicationListKind } from '~/features/fast-deals/mergedList'

/** «Вид заявки» filter of the merged «Мои заявки» lists: ordinary applications / fast deals / both (empty). */
defineProps<{ modelValue: ApplicationListKind | '' }>()
const emit = defineEmits<{ 'update:modelValue': [value: ApplicationListKind | ''] }>()

const selectId = useId()

const onChange = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value
  emit('update:modelValue', value === 'application' || value === 'fast_deal' ? value : '')
}
</script>
