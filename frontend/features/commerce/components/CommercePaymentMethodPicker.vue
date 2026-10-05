<template>
  <fieldset data-storefront-block="client.order">
    <legend class="text-sm font-semibold text-[color:var(--storefront-text,#111827)]">Способ оплаты</legend>
    <div data-storefront-block="client.order" class="mt-3 grid gap-3 sm:grid-cols-3">
      <label
        v-for="method in methods"
        :key="method.value"
        class="flex min-h-24 items-start gap-3 rounded-xl border-2 p-4 transition-colors focus-within:ring-2 focus-within:ring-[color:var(--storefront-focus,#2563eb)] focus-within:ring-offset-2"
        :class="isDisabled(method.value)
          ? 'cursor-not-allowed border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] opacity-60'
          : modelValue === method.value
            ? 'cursor-pointer border-[color:var(--storefront-border,#2563eb)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]'
            : 'cursor-pointer border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] hover:border-[color:var(--storefront-border,#d1d5db)]'"
        :aria-disabled="isDisabled(method.value) ? 'true' : undefined"
      >
        <input
          :checked="modelValue === method.value"
          :value="method.value"
          type="radio"
          name="commerce-payment-method"
          class="storefront-control mt-1 h-4 w-4 accent-[var(--storefront-primary,#2563eb)]"
          :disabled="isDisabled(method.value)"
          @change="emit('update:modelValue', method.value)"
        >
        <span>
          <span class="block text-sm font-semibold text-[color:var(--storefront-text,#030712)]">{{ method.label }}</span>
          <span class="mt-1 block text-sm leading-snug text-[color:var(--storefront-text-muted,#4b5563)]">{{ method.description }}</span>
        </span>
      </label>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import type { CommercePaymentMethod } from '../types'

const props = withDefaults(defineProps<{
  modelValue: CommercePaymentMethod
  disabledMethods?: CommercePaymentMethod[]
}>(), {
  disabledMethods: () => [],
})

const emit = defineEmits<{
  'update:modelValue': [value: CommercePaymentMethod]
}>()

const methods: Array<{
  value: CommercePaymentMethod
  label: string
  description: string
}> = [
  { value: 'sbp', label: 'СБП', description: 'Оплата через приложение банка' },
  { value: 'card', label: 'Банковская карта', description: 'МИР, Visa или MasterCard' },
  { value: 'bank_transfer', label: 'По реквизитам', description: 'Безналичный перевод по счёту' },
]

const isDisabled = (method: CommercePaymentMethod): boolean => props.disabledMethods.includes(method)
</script>
