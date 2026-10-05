<template>
  <div data-storefront-block="client.checkout" class="mb-6 md:mb-8">
    <div class="flex items-center">
      <div v-for="(step, index) in STEPS" :key="step.num" class="contents">
        <div
          class="flex items-center"
          :class="canSelect(step.num) ? 'cursor-pointer' : 'cursor-default'"
          @click="onSelect(step.num)"
        >
          <div
            class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium transition-all"
            :class="stepBubble(step.num)"
          >
            <svg v-if="isCompleted(step.num)" class="text-[color:var(--storefront-icon,inherit)] w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            <span v-else>{{ step.num }}</span>
          </div>
          <span class="ml-3 text-sm font-medium" :class="stepLabel(step.num)">{{ step.label }}</span>
        </div>
        <div v-if="index < STEPS.length - 1" class="flex-1 h-px bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] mx-4"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  currentStep: number
  completedSteps: number[]
}>()

const emit = defineEmits<{
  (e: 'select', step: number): void
}>()

const STEPS = [
  { num: 1, label: 'Контакты и адреса' },
  { num: 2, label: 'Согласие на обработку ПД' },
  { num: 3, label: 'Документы компании' },
] as const

const isCompleted = (n: number) => props.completedSteps.includes(n)
const isCurrent = (n: number) => n === props.currentStep
const isLocked = (n: number) => !isCompleted(n) && !isCurrent(n)

const canSelect = (n: number) => {
  if (n === props.currentStep) return false
  return isCompleted(n)
}

const onSelect = (n: number) => {
  if (!canSelect(n)) return
  emit('select', n)
}

const stepBubble = (n: number) => {
  if (isCompleted(n)) return 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)]'
  if (isCurrent(n)) return 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)] ring-4 ring-[color:var(--storefront-border,#dbeafe)]'
  if (isLocked(n)) return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)]'
  return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)]'
}

const stepLabel = (n: number) => {
  if (isCompleted(n)) return 'text-[color:var(--storefront-text,#111827)]'
  if (isCurrent(n)) return 'text-[color:var(--storefront-text,#111827)] font-semibold'
  if (isLocked(n)) return 'text-[color:var(--storefront-text-muted,#9ca3af)]'
  return 'text-[color:var(--storefront-text-muted,#6b7280)]'
}
</script>
