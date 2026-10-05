<template>
  <div class="inline-flex min-w-0 items-center gap-2">
    <span :id="labelId" class="text-sm font-semibold text-storefront-text">{{ label }}</span>
    <div class="inline-flex h-11 shrink-0 items-stretch overflow-hidden rounded-lg border border-storefront-border bg-storefront-surface">
      <button
        type="button"
        class="grid min-w-11 place-items-center text-lg font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-storefront-focus disabled:cursor-not-allowed disabled:text-storefront-disabled-foreground storefront-action-secondary"
        :disabled="disabled || modelValue <= 1"
        :aria-label="`Уменьшить ${label.toLocaleLowerCase('ru-RU')}`"
        @click="setQuantity(modelValue - 1)"
      >
        −
      </button>
      <input
        :value="modelValue"
        type="number"
        inputmode="numeric"
        min="1"
        :max="normalizedMax"
        :disabled="disabled"
        :aria-labelledby="labelId"
        class="w-14 border-x border-storefront-border bg-storefront-surface text-center text-sm font-bold tabular-nums text-storefront-text [appearance:textfield] focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-storefront-focus [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none storefront-control"
        @change="setQuantity(Number(($event.target as HTMLInputElement).value))"
      >
      <button
        type="button"
        class="grid min-w-11 place-items-center text-lg font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-storefront-focus disabled:cursor-not-allowed disabled:text-storefront-disabled-foreground storefront-action-secondary"
        :disabled="disabled || modelValue >= normalizedMax"
        :aria-label="`Увеличить ${label.toLocaleLowerCase('ru-RU')}`"
        @click="setQuantity(modelValue + 1)"
      >
        +
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  modelValue: number
  max: number
  label?: string
  disabled?: boolean
}>(), {
  label: 'Количество',
  disabled: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: number] }>()
const labelId = `special-equipment-quantity-${useId()}`
const normalizedMax = computed(() => Math.max(1, Math.floor(props.max)))

const setQuantity = (rawValue: number) => {
  const value = Number.isFinite(rawValue) ? Math.floor(rawValue) : 1
  emit('update:modelValue', Math.min(normalizedMax.value, Math.max(1, value)))
}
</script>
