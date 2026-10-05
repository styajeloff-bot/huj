<template>
  <div data-storefront-block="client.order" class="rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] overflow-hidden shadow-sm">
    <!-- Header -->
    <div class="px-4 sm:px-5 py-4 border-b border-[color:var(--storefront-border,#f3f4f6)] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
      <div class="flex items-center gap-3">
        <span class="text-sm font-semibold text-[color:var(--storefront-text,#111827)]">Заказ #{{ order.id }}</span>
        <PurchaseStatusBadge :status="order.status" />
      </div>
      <span class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ formatDateTime(order.created_at) }}</span>
    </div>

    <!-- Body -->
    <div class="px-4 sm:px-5 py-4">
      <div class="flex gap-4">
        <!-- Image -->
        <div class="w-20 h-20 sm:w-24 sm:h-24 rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden flex-shrink-0 flex items-center justify-center">
          <img
            v-if="vehicleImage"
            :src="vehicleImage"
            :alt="vehicleTitle"
            class="w-full h-full object-contain"
            onerror="this.src='/images/car-placeholder.png'"
          >
          <svg v-else class="w-8 h-8 text-[color:var(--storefront-icon,#d1d5db)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
          </svg>
        </div>

        <!-- Info -->
        <div class="min-w-0 flex-1">
          <h3 class="font-semibold text-[color:var(--storefront-title,#111827)] text-base mb-1">{{ vehicleTitle }}</h3>
          <div class="space-y-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            <div v-if="order.vin" class="flex items-center gap-1.5">
              <span class="text-[color:var(--storefront-text-muted,#6b7280)]">VIN:</span>
              <span class="font-mono text-[color:var(--storefront-text,#111827)]">{{ order.vin }}</span>
            </div>
            <div v-if="warehouseDisplay" class="flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span>{{ warehouseDisplay }}</span>
            </div>
          </div>

          <!-- Price info -->
          <div class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
            <div>
              <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Стоимость:</span>
              <span class="font-semibold text-[color:var(--storefront-text,#111827)] ml-1">{{ formatPrice(order.total_price) }}</span>
            </div>
            <div>
              <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Оплачено:</span>
              <span class="font-semibold text-[color:var(--storefront-success-text,#16a34a)] ml-1">{{ formatPrice(order.paid_amount) }}</span>
            </div>
            <div v-if="parseFloat(order.remaining_amount) > 0">
              <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Остаток:</span>
              <span class="font-semibold text-[color:var(--storefront-warning-text,#ea580c)] ml-1">{{ formatPrice(order.remaining_amount) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Cancellation requested notice -->
      <div v-if="order.status === 'cancellation_requested'" class="mt-4 p-3 bg-[color:rgb(var(--storefront-warning-rgb,255_247_237)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fed7aa)] rounded-lg text-sm text-[color:var(--storefront-warning-text,#9a3412)]">
        <div class="flex items-center gap-2">
          <svg class="text-[color:var(--storefront-icon,inherit)] w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Ваш запрос на отмену обрабатывается
        </div>
        <div v-if="order.cancellation_reason" class="mt-1 text-xs text-[color:var(--storefront-warning-text,#c2410c)]">
          Причина: {{ order.cancellation_reason }}
        </div>
      </div>

      <!-- Payment History -->
      <div v-if="payments.length > 0" class="mt-4">
        <PaymentHistoryList
          :payments="payments"
          @view-receipt="handleViewReceipt"
        />
      </div>

      <!-- Leasing Schedule -->
      <div v-if="order.status === 'leasing_active'" class="mt-4">
        <LeasingSchedulePanel
          :schedule="schedule"
          :loading="loadingSchedule"
          @pay="handlePaySchedule"
          @view-receipt="handleViewReceipt"
        />
      </div>
    </div>

    <!-- Actions -->
    <div v-if="showActions" class="px-4 sm:px-5 py-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-t border-[color:var(--storefront-border,#f3f4f6)] flex flex-wrap gap-2">
      <!-- Reserved actions -->
      <template v-if="order.status === 'reserved'">
        <button
          type="button"
          class="storefront-action-ghost py-2 px-4 bg-[color:rgb(var(--storefront-ghost-rgb,22_163_74)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-ghost-foreground,#ffffff)] text-sm font-medium rounded-lg hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,21_128_61)/var(--tw-bg-opacity,1))] transition-colors"
          @click="showPayRemainingModal = true"
        >
          Оплатить остаток
        </button>
        <button
          v-if="hasCompanies"
          type="button"
          class="storefront-action-primary py-2 px-4 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] text-sm font-medium rounded-lg hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] transition-colors"
          @click="goToLeasing"
        >
          Оформить заявку на лизинг
        </button>
        <button
          type="button"
          class="storefront-action-ghost py-2 px-4 border border-[color:var(--storefront-destructive-border,#fca5a5)] text-[color:var(--storefront-destructive-foreground,#dc2626)] text-sm font-medium rounded-lg hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))] transition-colors ml-auto"
          @click="showCancelModal = true"
        >
          Запросить отмену
        </button>
      </template>

      <!-- Purchased actions -->
      <template v-if="order.status === 'purchased'">
        <button
          type="button"
          class="storefront-action-ghost py-2 px-4 border border-[color:var(--storefront-destructive-border,#fca5a5)] text-[color:var(--storefront-destructive-foreground,#dc2626)] text-sm font-medium rounded-lg hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))] transition-colors ml-auto"
          @click="showCancelModal = true"
        >
          Запросить отмену
        </button>
      </template>
    </div>

    <!-- Pay Remaining Modal -->
    <PayRemainingModal
      :show="showPayRemainingModal"
      :order="order"
      @close="showPayRemainingModal = false"
      @success="handlePayRemainingSuccess"
    />

    <!-- Pay Schedule Modal -->
    <PaymentConfirmModal
      :show="showPayScheduleModal"
      title="Оплата лизингового платежа"
      :description="`Платеж #${selectedScheduleItem?.payment_number || ''}`"
      :amount="selectedScheduleItem?.amount || 0"
      @close="showPayScheduleModal = false; selectedScheduleItem = null"
      @confirm="handlePayScheduleConfirm"
    />

    <!-- Cancel Modal -->
    <CancellationRequestModal
      :show="showCancelModal"
      :order-id="order.id"
      :vehicle-name="vehicleTitle"
      @close="showCancelModal = false"
      @cancelled="$emit('refresh')"
    />
  </div>
</template>

<script setup lang="ts">
import type { PaymentRecord, ScheduleItem as ScheduleItemType } from '~/types/domains'
import type { UUID } from '~/types/ids'
import PurchaseStatusBadge from '~/features/purchases/components/PurchaseStatusBadge.vue'
import PaymentHistoryList from '~/features/purchases/components/PaymentHistoryList.vue'
import LeasingSchedulePanel from '~/features/purchases/components/LeasingSchedulePanel.vue'
import PayRemainingModal from '~/features/purchases/components/PayRemainingModal.vue'
import PaymentConfirmModal from '~/features/purchases/components/PaymentConfirmModal.vue'
import CancellationRequestModal from '~/features/purchases/components/CancellationRequestModal.vue'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

const props = defineProps({
  order: { type: Object, required: true },
  hasCompanies: { type: Boolean, default: false }
})

const emit = defineEmits(['refresh'])

const { formatPrice } = useFormatPrice()
const purchasesStore = usePurchasesStore()
const router = useRouter()
const toast = useToast()

const payments = ref<PaymentRecord[]>([])
const schedule = ref<ScheduleItemType[]>([])
const loadingSchedule = ref(false)
const showPayRemainingModal = ref(false)
const showPayScheduleModal = ref(false)
const showCancelModal = ref(false)
const selectedScheduleItem = ref<ScheduleItemType | null>(null)

const vehicleTitle = computed(() =>
  `${props.order.mark_name || ''} ${props.order.model_name || ''}`.trim() || 'Автомобиль'
)

const vehicleImage = computed(() => {
  const images = props.order.images
  if (Array.isArray(images) && images.length > 0 && images[0]) {
    return vehicleImageUrl(images[0])
  }
  return null
})

const warehouseDisplay = computed(() => {
  const parts = []
  if (props.order.warehouse_name) parts.push(props.order.warehouse_name)
  if (props.order.warehouse_address) parts.push(props.order.warehouse_address)
  return parts.join(', ') || null
})

const showActions = computed(() =>
  ['reserved', 'purchased'].includes(props.order.status)
)

function formatDateTime(dateStr: string | null | undefined) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}

function goToLeasing() {
  router.push(`/cart/conditions?fromPurchase=${props.order.id}`)
}

async function loadPayments() {
  try {
    payments.value = await purchasesStore.getPayments(props.order.id)
  } catch {
    // Silent fail, not critical
  }
}

async function loadSchedule() {
  if (!['leasing_active', 'leasing_pending'].includes(props.order.status)) return
  loadingSchedule.value = true
  try {
    schedule.value = await purchasesStore.getSchedule(props.order.id)
  } catch {
    // Silent fail
  } finally {
    loadingSchedule.value = false
  }
}

async function handlePayRemainingSuccess() {
  showPayRemainingModal.value = false
  emit('refresh')
  await loadPayments()
}

function handlePaySchedule(scheduleItem: ScheduleItemType) {
  selectedScheduleItem.value = scheduleItem
  showPayScheduleModal.value = true
}

async function handlePayScheduleConfirm({ resolve, reject }: { resolve: () => void; reject: (err: unknown) => void }) {
  if (!selectedScheduleItem.value) return reject(new Error('No schedule item'))
  try {
    await purchasesStore.paySchedule(props.order.id, selectedScheduleItem.value.id)
    toast.success('Платеж оплачен')
    resolve()
    await loadSchedule()
    await loadPayments()
  } catch (err) {
    reject(err)
  }
}

async function handleViewReceipt(paymentId: UUID) {
  try {
    // Check if this payment has a fiscal receipt URL
    const payment = payments.value.find(p => p.id === paymentId)
    if (payment?.receipt_url) {
      window.open(payment.receipt_url, '_blank')
      return
    }

    // Fallback: show receipt data as HTML
    const result = await purchasesStore.getReceipt(paymentId)
    const receiptWindow = window.open('', '_blank')
    if (receiptWindow) {
      const r = result.receipt
      receiptWindow.document.write(`
        <html><head><title>Чек #${r.payment.id}</title>
        <style>body{font-family:sans-serif;padding:40px;max-width:600px;margin:0 auto}
        h1{font-size:20px;border-bottom:2px solid #333;padding-bottom:10px}
        .row{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #eee}
        .label{color:#666}.value{font-weight:600}
        .total{font-size:24px;margin-top:20px;text-align:right}</style></head><body>
        <h1>Чек об оплате</h1>
        <div class="row"><span class="label">Номер платежа</span><span class="value">${r.payment.id}</span></div>
        <div class="row"><span class="label">Автомобиль</span><span class="value">${r.order.mark_name} ${r.order.model_name}</span></div>
        <div class="row"><span class="label">VIN</span><span class="value">${r.order.vin || '—'}</span></div>
        <div class="row"><span class="label">Тип платежа</span><span class="value">${r.payment.payment_type}</span></div>
        <div class="row"><span class="label">Дата</span><span class="value">${new Date(r.payment.paid_at || r.payment.created_at).toLocaleString('ru-RU')}</span></div>
        <div class="total">Сумма: ${Number(r.payment.amount).toLocaleString('ru-RU')} ₽</div>
        <button onclick="window.print()" style="margin-top:30px;padding:10px 20px;cursor:pointer">Печать</button>
        </body></html>
      `)
    }
  } catch {
    toast.error('Не удалось загрузить чек')
  }
}

onMounted(async () => {
  await loadPayments()
  await loadSchedule()
})
</script>
