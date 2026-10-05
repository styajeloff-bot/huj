<template>
  <div data-storefront-block="shared.form"
    v-if="currentProgram"
    class="group/support-badge relative z-20 inline-flex max-w-full"
  >
    <button
      type="button"
      class="storefront-action-ghost inline-flex max-w-full items-center bg-[color:rgb(var(--storefront-ghost-rgb,236_253_245)/var(--tw-bg-opacity,1))] px-2 py-1 text-xs font-medium text-[color:var(--storefront-ghost-foreground,#065f46)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#059669)] focus-visible:ring-offset-2"
      :class="props.shape === 'badge' ? 'rounded' : 'rounded-full'"
      :aria-describedby="tooltipId"
      :aria-label="`Поддержка дистрибьютора: ${currentProgram.name}`"
    >
      <span class="truncate" aria-live="polite">{{ currentProgram.name }}</span>
    </button>
    <div data-storefront-block="shared.tooltip"
      :id="tooltipId"
      role="tooltip"
      class="pointer-events-none absolute top-full z-30 mt-2 hidden w-72 max-w-[min(18rem,calc(100vw-2rem))] rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,3_7_18)/var(--tw-bg-opacity,1))] px-3 py-2 text-left text-xs font-normal leading-relaxed text-[color:var(--storefront-text,#ffffff)] shadow-xl group-hover/support-badge:block group-focus-within/support-badge:block"
      :class="props.tooltipAlign === 'right' ? 'right-0' : 'left-0'"
    >
      <p>{{ description }}</p>
      <p v-if="supportAmountText" class="mt-1 font-semibold">Сумма поддержки: {{ supportAmountText }}</p>
      <p v-if="endsAtText" class="mt-1 text-[color:var(--storefront-text,#e5e7eb)]">До {{ endsAtText }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SupportBadgeProgram } from '~/types/support'
import {
  SUPPORT_BADGE_ROTATION_MS,
  useRotatingSupportBadge,
} from '~/features/support/composables/useRotatingSupportBadge'

const props = withDefaults(defineProps<{
  programs: readonly SupportBadgeProgram[]
  tooltipAlign?: 'left' | 'right'
  shape?: 'pill' | 'badge'
  rotationMs?: number
}>(), {
  tooltipAlign: 'left',
  shape: 'pill',
  rotationMs: SUPPORT_BADGE_ROTATION_MS,
})

const tooltipId = `support-badge-${useId()}`
const { currentProgram } = useRotatingSupportBadge(
  () => props.programs,
  () => props.rotationMs,
)

const fallbackDescription = computed(() => {
  const type = currentProgram.value?.support_type
  if (type === 'down_payment_compensation') return 'Поддержка уменьшает первоначальный взнос.'
  if (type === 'vehicle_discount_dealer_compensation' || type === 'vehicle_discount_dealer_invoice') {
    return 'Поддержка уменьшает стоимость транспортного средства.'
  }
  if (type === 'leasing_interest_compensation') return 'Поддержка уменьшает стоимость лизинга.'
  return 'Для транспортного средства действует программа поддержки.'
})

const description = computed(() => currentProgram.value?.comment?.trim() || fallbackDescription.value)
const supportAmountText = computed(() => {
  const amount = currentProgram.value?.support_amount
  if (typeof amount !== 'number' || !Number.isFinite(amount) || amount <= 0) return ''
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(amount)} ₽`
})
const endsAtText = computed(() => {
  const raw = currentProgram.value?.ends_at?.slice(0, 10)
  const match = raw?.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return match ? `${match[3]}.${match[2]}.${match[1]}` : ''
})
</script>
