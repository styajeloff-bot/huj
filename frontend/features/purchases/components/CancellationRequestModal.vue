<template>
  <Modal
    :show="show"
    size="sm"
    :show-header="false"
    @close="$emit('close')"
  >
    <div data-storefront-block="client.order" class="text-center pt-2">
      <div class="w-14 h-14 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center mx-auto mb-4">
        <svg class="w-7 h-7 text-[color:var(--storefront-error-icon,#dc2626)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
      </div>

      <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Запросить отмену?</h3>
      <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-5">
        Вы уверены, что хотите отменить
        <span class="font-medium text-[color:var(--storefront-text,#111827)]">{{ vehicleName }}</span>?
        Запрос будет отправлен на рассмотрение.
      </p>

      <div class="mb-5">
        <textarea
          v-model="reason"
          rows="3"
          class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#ef4444)] focus:border-[color:var(--storefront-error-border,#ef4444)] resize-none"
          placeholder="Причина отмены (необязательно)"
        ></textarea>
      </div>

      <div class="flex gap-3">
        <button
          type="button"
          class="storefront-action-ghost flex-1 py-2.5 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-lg text-[color:var(--storefront-secondary-foreground,#374151)] text-sm font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] transition-colors"
          :disabled="processing"
          @click="$emit('close')"
        >
          Нет, оставить
        </button>
        <button
          type="button"
          class="storefront-action-destructive flex-1 py-2.5 px-4 bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-destructive-foreground,#ffffff)] rounded-lg text-sm font-medium hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] transition-colors disabled:opacity-50"
          :disabled="processing"
          @click="handleCancel"
        >
          <span v-if="processing" class="flex items-center justify-center gap-2">
            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#ffffff)]"></div>
            Отправка...
          </span>
          <span v-else>Да, отменить</span>
        </button>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import type { UUID } from '~/types/ids'

const props = withDefaults(defineProps<{
  show?: boolean
  orderId: UUID
  vehicleName?: string
}>(), {
  show: false,
  vehicleName: ''
})

const emit = defineEmits(['close', 'cancelled'])

const purchasesStore = usePurchasesStore()
const toast = useToast()

const reason = ref('')
const processing = ref(false)

async function handleCancel() {
  processing.value = true
  try {
    await purchasesStore.cancelOrder(props.orderId, reason.value || undefined)
    toast.success('Запрос на отмену отправлен')
    emit('cancelled')
    emit('close')
  } catch {
    toast.error('Не удалось отправить запрос на отмену')
  } finally {
    processing.value = false
  }
}

watch(() => props.show, (val) => {
  if (val) {
    reason.value = ''
    processing.value = false
  }
})
</script>
