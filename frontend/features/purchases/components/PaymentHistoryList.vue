<template>
  <div data-storefront-block="client.order" v-if="payments.length > 0" class="space-y-2">
    <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#374151)] mb-2">История платежей</h4>
    <div
      v-for="payment in payments"
      :key="payment.id"
      class="flex items-center justify-between py-2 px-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg text-sm"
    >
      <div class="flex items-center gap-3 min-w-0">
        <span
          class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
          :class="paymentStatusClass(payment.status)"
        >
          {{ paymentStatusText(payment.status) }}
        </span>
        <span class="text-[color:var(--storefront-text-muted,#4b5563)] truncate">{{ paymentTypeText(payment.payment_type) }}</span>
      </div>
      <div class="flex items-center gap-3 shrink-0">
        <span v-if="payment.payment_method" class="text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">{{ paymentMethodText(payment.payment_method) }}</span>
        <span class="font-semibold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(payment.amount) }}</span>
        <span class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ formatDate(payment.paid_at || payment.created_at) }}</span>
        <template v-if="payment.status === 'completed'">
          <a
            v-if="payment.receipt_url"
            :href="payment.receipt_url"
            target="_blank"
            class="text-[color:var(--storefront-link,#2563eb)] hover:text-[color:var(--storefront-link-hover,#1e40af)] text-xs font-medium"
          >
            Чек
          </a>
          <span
            v-else-if="payment.fiscal_status === 'sent' || payment.fiscal_status === 'pending'"
            class="text-xs text-[color:var(--storefront-text-muted,#9ca3af)]"
          >
            Чек формируется...
          </span>
          <button
            v-else
            type="button"
            class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] text-xs font-medium"
            @click="$emit('view-receipt', payment.id)"
          >
            Чек
          </button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PaymentRecord } from '~/types/domains'
import type { UUID } from '~/types/ids'

withDefaults(defineProps<{
  payments?: PaymentRecord[]
}>(), {
  payments: () => []
})

defineEmits<{
  'view-receipt': [paymentId: UUID]
}>()

const { formatPrice } = useFormatPrice()

function paymentStatusText(status: string) {
  const map: Record<string, string> = {
    completed: 'Оплачено',
    processing: 'В обработке',
    pending_payment: 'Ожидает оплаты',
    failed: 'Не оплачено',
    error: 'Ошибка'
  }
  return map[status] || status
}

function paymentStatusClass(status: string) {
  const map: Record<string, string> = {
    completed: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#15803d)]',
    processing: 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#a16207)]',
    pending_payment: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1d4ed8)]',
    failed: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#b91c1c)]',
    error: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#b91c1c)]'
  }
  return map[status] || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)]'
}

function paymentMethodText(method: string | null) {
  if (!method) return ''
  const map: Record<string, string> = {
    card: 'Карта',
    sbp: 'СБП',
    bank_transfer: 'По реквизитам'
  }
  return map[method] || ''
}

function paymentTypeText(type: string) {
  const map: Record<string, string> = {
    reservation: 'Резервирование (10%)',
    remaining_balance: 'Доплата остатка (90%)',
    full_purchase: 'Полная оплата',
    leasing_monthly: 'Ежемесячный платеж'
  }
  return map[type] || type
}

function formatDate(dateStr: string | null | undefined) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
</script>
