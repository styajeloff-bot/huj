<template>
  <Modal
    :show="show"
    :title="title"
    size="sm"
    @close="handleClose"
  >
    <!-- Success state -->
    <div data-storefront-block="client.order" v-if="successPayment" class="text-center py-4">
      <div class="w-14 h-14 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-7 h-7 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
        </svg>
      </div>
      <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Оплата прошла успешно!</h3>
      <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-4">Сумма: {{ formatPrice(amount) }}</p>
      <button
        type="button"
        class="storefront-action-primary w-full py-2.5 px-4 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-lg text-sm font-medium hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] transition-colors"
        @click="handleClose"
      >
        Закрыть
      </button>
    </div>

    <!-- Error state -->
    <div data-storefront-block="client.order" v-else-if="errorMessage" class="text-center py-4">
      <div class="w-14 h-14 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-7 h-7 text-[color:var(--storefront-error-icon,#dc2626)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
        </svg>
      </div>
      <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Ошибка оплаты</h3>
      <p class="text-sm text-[color:var(--storefront-error-text,#dc2626)] mb-4">{{ errorMessage }}</p>
      <div class="flex gap-3">
        <button
          type="button"
          class="storefront-action-ghost flex-1 py-2.5 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-lg text-[color:var(--storefront-secondary-foreground,#374151)] text-sm font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
          @click="handleClose"
        >
          Закрыть
        </button>
        <button
          type="button"
          class="storefront-action-primary flex-1 py-2.5 px-4 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-lg text-sm font-medium hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]"
          @click="handleConfirm"
        >
          Попробовать снова
        </button>
      </div>
    </div>

    <!-- Confirm state -->
    <div data-storefront-block="client.order" v-else class="py-2">
      <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-xl p-4 mb-5">
        <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-1">{{ description }}</div>
        <div class="text-2xl font-bold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(amount) }}</div>
      </div>

      <div class="flex gap-3">
        <button
          type="button"
          class="storefront-action-ghost flex-1 py-2.5 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-lg text-[color:var(--storefront-secondary-foreground,#374151)] text-sm font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] transition-colors"
          :disabled="processing"
          @click="handleClose"
        >
          Отмена
        </button>
        <button
          type="button"
          class="storefront-action-ghost flex-1 py-2.5 px-4 bg-[color:rgb(var(--storefront-ghost-rgb,22_163_74)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-ghost-foreground,#ffffff)] rounded-lg text-sm font-medium hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,21_128_61)/var(--tw-bg-opacity,1))] transition-colors disabled:opacity-50"
          :disabled="processing"
          @click="handleConfirm"
        >
          <span v-if="processing" class="flex items-center justify-center gap-2">
            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#ffffff)]"></div>
            Обработка...
          </span>
          <span v-else>Оплатить</span>
        </button>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: 'Подтверждение оплаты' },
  description: { type: String, default: '' },
  amount: { type: Number, default: 0 }
})

const emit = defineEmits(['close', 'confirm'])

const { formatPrice } = useFormatPrice()

const processing = ref(false)
const successPayment = ref(false)
const errorMessage = ref('')

async function handleConfirm() {
  processing.value = true
  errorMessage.value = ''
  try {
    await new Promise((resolve, reject) => {
      emit('confirm', { resolve, reject })
    })
    successPayment.value = true
  } catch (err: unknown) {
    const e = err as Record<string, unknown> | null
    const data = e?.data as Record<string, unknown> | undefined
    errorMessage.value = (data?.error || e?.message || 'Произошла ошибка при оплате') as string
  } finally {
    processing.value = false
  }
}

function handleClose() {
  emit('close')
}

watch(() => props.show, (val) => {
  if (val) {
    processing.value = false
    successPayment.value = false
    errorMessage.value = ''
  }
})
</script>
