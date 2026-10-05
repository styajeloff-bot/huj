<template>
  <div data-storefront-block="client.order">
    <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#374151)] mb-3">График лизинговых платежей</h4>

    <div v-if="loading" class="flex justify-center py-4">
      <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
    </div>

    <div v-else-if="schedule.length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] py-3">
      График платежей пока не сформирован
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-[color:var(--storefront-border,#e5e7eb)]">
            <th class="text-left py-2 pr-3 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">#</th>
            <th class="text-left py-2 pr-3 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Дата</th>
            <th class="text-right py-2 pr-3 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Сумма</th>
            <th class="table-cell text-right py-2 pr-3 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Основной долг</th>
            <th class="table-cell text-right py-2 pr-3 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Проценты</th>
            <th class="text-center py-2 text-[color:var(--storefront-text-muted,#6b7280)] font-medium">Статус</th>
            <th class="py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in schedule"
            :key="item.id"
            class="border-b border-[color:var(--storefront-border,#f3f4f6)]"
            :class="{ 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]': isNextPayment(item) }"
          >
            <td class="py-2.5 pr-3 text-[color:var(--storefront-text-muted,#4b5563)]">{{ item.payment_number }}</td>
            <td class="py-2.5 pr-3 text-[color:var(--storefront-text,#111827)]">{{ formatDate(item.due_date) }}</td>
            <td class="py-2.5 pr-3 text-right font-medium text-[color:var(--storefront-text,#111827)]">{{ formatPrice(item.amount) }}</td>
            <td class="table-cell py-2.5 pr-3 text-right text-[color:var(--storefront-text-muted,#4b5563)]">
              {{ item.principal ? formatPrice(item.principal) : '—' }}
            </td>
            <td class="table-cell py-2.5 pr-3 text-right text-[color:var(--storefront-text-muted,#4b5563)]">
              {{ item.interest ? formatPrice(item.interest) : '—' }}
            </td>
            <td class="py-2.5 text-center">
              <span
                v-if="item.is_paid"
                class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#15803d)]"
              >
                Оплачен
              </span>
              <span
                v-else-if="isOverdue(item)"
                class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#b91c1c)]"
              >
                Просрочен
              </span>
              <span
                v-else-if="isNextPayment(item)"
                class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1d4ed8)]"
              >
                Предстоящий
              </span>
              <span
                v-else
                class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)]"
              >
                Ожидает
              </span>
            </td>
            <td class="py-2.5 pl-2">
              <button
                v-if="!item.is_paid"
                type="button"
                class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] font-medium whitespace-nowrap"
                @click="$emit('pay', item)"
              >
                Оплатить
              </button>
              <button
                v-else-if="item.receipt_url && item.payment_id"
                type="button"
                class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] font-medium"
                @click="$emit('view-receipt', item.payment_id)"
              >
                Чек
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ScheduleItem } from '~/types/domains'
import type { UUID } from '~/types/ids'

withDefaults(defineProps<{
  schedule?: ScheduleItem[]
  loading?: boolean
}>(), {
  schedule: () => [],
  loading: false
})

defineEmits<{
  pay: [scheduleItem: ScheduleItem]
  'view-receipt': [paymentId: UUID]
}>()

const { formatPrice } = useFormatPrice()

function formatDate(dateStr: string | null | undefined) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

function isNextPayment(item: ScheduleItem) {
  if (item.is_paid) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const due = new Date(item.due_date)
  return due >= today
}

function isOverdue(item: ScheduleItem) {
  if (item.is_paid) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const due = new Date(item.due_date)
  return due < today
}
</script>
