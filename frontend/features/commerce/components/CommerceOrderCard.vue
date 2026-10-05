<template>
  <article data-storefront-block="client.order" class="overflow-hidden rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-sm">
    <header class="flex flex-col gap-3 border-b border-[color:var(--storefront-border,#f3f4f6)] px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
      <div class="flex flex-wrap items-center gap-3">
        <span class="text-sm font-semibold text-[color:var(--storefront-text,#111827)]">Заказ #{{ order.id }}</span>
        <span class="inline-flex rounded-full px-2.5 py-1 text-xs font-medium" :class="statusClass(order.status)">
          {{ statusLabel(order.status) }}
        </span>
        <span class="rounded-full bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] px-2.5 py-1 text-xs font-medium text-[color:var(--storefront-text,#374151)]">
          {{ itemTypeLabel }}
        </span>
      </div>
      <time v-if="order.created_at" class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]" :datetime="order.created_at">{{ formatDateTime(order.created_at) }}</time>
      <span v-else class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Дата не указана</span>
    </header>

    <div class="px-4 py-4 sm:px-5">
      <div class="flex gap-4">
        <div class="grid h-20 w-24 shrink-0 place-items-center overflow-hidden rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] sm:h-24 sm:w-28">
          <img v-if="safeProxyUrl(order.item_snapshot.image_url)" :src="safeProxyUrl(order.item_snapshot.image_url) ?? undefined" :alt="order.item_snapshot.title" class="h-full w-full object-contain" width="224" height="192">
          <PhotoIcon v-else class="h-8 w-8 text-[color:var(--storefront-icon,#d1d5db)]" aria-hidden="true" />
        </div>

        <div class="min-w-0 flex-1">
          <h3 class="text-base font-semibold leading-snug text-[color:var(--storefront-title,#030712)]">{{ order.item_snapshot.title }}</h3>
          <p v-if="order.item_snapshot.subtitle" class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ order.item_snapshot.subtitle }}</p>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ purchaseTypeLabel(order.purchase_type) }}</p>
          <dl class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm">
            <div><dt class="inline text-[color:var(--storefront-text-muted,#6b7280)]">Стоимость:</dt> <dd class="inline font-semibold tabular-nums text-[color:var(--storefront-value,#030712)]">{{ formatCommerceMoney(order.total_price, order.currency_code) }}</dd></div>
            <div><dt class="inline text-[color:var(--storefront-text-muted,#6b7280)]">Оплачено:</dt> <dd class="inline font-semibold tabular-nums text-[color:var(--storefront-success-text,#047857)]">{{ formatCommerceMoney(order.paid_amount, order.currency_code) }}</dd></div>
            <div v-if="isPositiveMoney(order.remaining_amount)"><dt class="inline text-[color:var(--storefront-text-muted,#6b7280)]">Остаток:</dt> <dd class="inline font-semibold tabular-nums text-[color:var(--storefront-warning-text,#b45309)]">{{ formatCommerceMoney(order.remaining_amount, order.currency_code) }}</dd></div>
          </dl>
        </div>
      </div>

      <div v-if="order.status === 'cancellation_requested'" class="mt-4 rounded-lg border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-warning-text,#78350f)]" role="status">
        Запрос на отмену обрабатывается.<template v-if="order.cancellation_reason"> Причина: {{ order.cancellation_reason }}</template>
      </div>

      <div v-if="actionError" class="mt-4 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#991b1b)]" role="alert">{{ actionError }}</div>
      <div v-if="actionMessage" class="mt-4 rounded-lg border border-[color:var(--storefront-success-border,#a7f3d0)] bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-success-text,#064e3b)]" role="status">{{ actionMessage }}</div>
      <CommercePaymentAction v-if="paymentAction" class="mt-4" :widget-data="paymentAction.widgetData" :sbp-data="paymentAction.sbpData" :payment="paymentAction.payment" @status="handlePaymentStatus" />

      <div v-if="isExpanded" class="mt-5 border-t border-[color:var(--storefront-border,#f3f4f6)] pt-5">
        <div v-if="relatedLoading" class="flex flex-col gap-2" aria-label="Загрузка платежей" aria-busy="true">
          <div v-for="index in 2" :key="index" class="h-12 animate-pulse rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" />
        </div>
        <div v-else class="flex flex-col gap-6">
          <section :aria-labelledby="paymentsTitleId">
            <h4 :id="paymentsTitleId" class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)]">История платежей</h4>
            <div v-if="paymentsError" class="mt-2 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#991b1b)]" role="alert">
              {{ paymentsError }}
              <button type="button" class="storefront-action-ghost ml-2 font-semibold underline" @click="loadRelated">Повторить</button>
            </div>
            <p v-else-if="payments.length === 0" class="mt-2 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Платежей пока нет.</p>
            <ul v-else class="mt-3 flex flex-col gap-2">
              <li v-for="payment in payments" :key="payment.id" class="flex flex-col gap-2 rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-3 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                <div class="flex flex-wrap items-center gap-2">
                  <span class="rounded px-2 py-0.5 text-xs font-medium" :class="paymentStatusClass(payment.status)">{{ paymentStatusLabel(payment.status) }}</span>
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">{{ paymentTypeLabel(payment.payment_type) }}</span>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                  <span class="font-semibold tabular-nums text-[color:var(--storefront-text,#030712)]">{{ formatCommerceMoney(payment.amount, order.currency_code) }}</span>
                  <a v-if="safeProxyUrl(payment.receipt_content_url)" :href="safeProxyUrl(payment.receipt_content_url) ?? undefined" target="_blank" rel="noopener" class="font-medium text-[color:var(--storefront-link,#1d4ed8)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]">Чек</a>
                  <button
                    v-else-if="isPendingPayment(payment)"
                    type="button"
                    class="storefront-action-secondary min-h-10 rounded-lg border border-[color:var(--storefront-primary-border,#93c5fd)] bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 text-xs font-semibold text-[color:var(--storefront-primary-foreground,#1e40af)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] disabled:cursor-wait disabled:opacity-60"
                    :disabled="checkingPaymentIds.has(payment.id)"
                    @click="checkPaymentStatus(payment)"
                  >
                    {{ checkingPaymentIds.has(payment.id) ? 'Проверяем…' : 'Проверить статус' }}
                  </button>
                </div>
              </li>
            </ul>
          </section>

          <section v-if="shouldLoadSchedule" :aria-labelledby="scheduleTitleId">
            <h4 :id="scheduleTitleId" class="text-sm font-semibold text-[color:var(--storefront-title,#1f2937)]">График лизинговых платежей</h4>
            <div v-if="scheduleError" class="mt-2 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#991b1b)]" role="alert">
              {{ scheduleError }}
              <button type="button" class="storefront-action-ghost ml-2 font-semibold underline" @click="loadRelated">Повторить</button>
            </div>
            <p v-else-if="schedule.length === 0" class="mt-2 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">График пока не сформирован.</p>
            <div v-else class="mt-3 overflow-x-auto">
              <table class="min-w-[42rem] w-full text-sm">
                <thead><tr class="border-b border-[color:var(--storefront-border,#e5e7eb)] text-[color:var(--storefront-text-muted,#6b7280)]"><th class="py-2 text-left font-medium">№</th><th class="py-2 text-left font-medium">Дата</th><th class="py-2 text-right font-medium">Сумма</th><th class="py-2 text-left font-medium">Статус</th><th class="py-2 text-right font-medium">Действие</th></tr></thead>
                <tbody class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
                  <tr v-for="scheduleItem in schedule" :key="scheduleItem.id">
                    <td class="py-3 tabular-nums text-[color:var(--storefront-text,#374151)]">{{ scheduleItem.payment_number }}</td>
                    <td class="py-3 text-[color:var(--storefront-text,#374151)]">{{ formatDate(scheduleItem.due_date) }}</td>
                    <td class="py-3 text-right font-semibold tabular-nums text-[color:var(--storefront-text,#030712)]">{{ formatCommerceMoney(scheduleItem.amount, order.currency_code) }}</td>
                    <td class="py-3 text-[color:var(--storefront-text,#374151)]">{{ scheduleStatusLabel(scheduleItem) }}</td>
                    <td class="py-2 text-right">
                      <a v-if="safeProxyUrl(scheduleItem.receipt_content_url)" :href="safeProxyUrl(scheduleItem.receipt_content_url) ?? undefined" target="_blank" rel="noopener" class="font-medium text-[color:var(--storefront-link,#1d4ed8)] hover:underline">Чек</a>
                      <button v-else-if="scheduleItem.can_pay" type="button" class="storefront-action-ghost min-h-10 rounded-lg border border-[color:var(--storefront-primary-border,#93c5fd)] px-3 text-xs font-semibold text-[color:var(--storefront-primary-foreground,#1e40af)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] disabled:opacity-50" :disabled="actionLoading" @click="openPayment('scheduled', scheduleItem.amount, scheduleItem.id)">Оплатить</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>

    <footer class="flex flex-col gap-3 border-t border-[color:var(--storefront-border,#f3f4f6)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:px-5">
      <NuxtLink :to="commerceOrderLocation(order.item.type, order.id)" class="inline-flex min-h-11 items-center justify-center rounded-lg border border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-link,#111827)] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]">Открыть заказ</NuxtLink>
      <button type="button" class="storefront-action-secondary min-h-11 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#1f2937)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]" @click="toggleExpanded">{{ isExpanded ? 'Скрыть платежи' : 'Показать платежи' }}</button>
      <NuxtLink v-if="canApplyForLeasing" :to="commerceCheckoutLocation(order.item, 'leasing')" class="storefront-action-primary inline-flex min-h-11 items-center justify-center rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2">Оформить в лизинг</NuxtLink>
      <button v-if="canPayRemaining" type="button" class="storefront-action-ghost min-h-11 rounded-lg bg-[color:rgb(var(--storefront-ghost-rgb,5_150_105)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-ghost-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,4_120_87)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#059669)] focus-visible:ring-offset-2 disabled:opacity-50" :disabled="actionLoading" @click="openPayment('remaining', order.remaining_amount)">Оплатить остаток</button>
      <button v-if="canCancel && !showCancellation" type="button" class="storefront-action-secondary min-h-11 rounded-lg border border-[color:var(--storefront-destructive-border,#fca5a5)] bg-[color:rgb(var(--storefront-destructive-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-destructive-foreground,#b91c1c)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#dc2626)] sm:ml-auto" @click="showCancellation = true">Запросить отмену</button>
    </footer>

    <div v-if="showCancellation" class="border-t border-[color:var(--storefront-error-border,#fee2e2)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] px-4 py-4 sm:px-5">
      <label class="block">
        <span class="text-sm font-medium text-[color:var(--storefront-error-text,#450a0a)]">Причина отмены <span class="font-normal text-[color:var(--storefront-error-text,#991b1b)]">(необязательно)</span></span>
        <textarea v-model.trim="cancellationReason" rows="3" maxlength="2000" class="storefront-control mt-2 w-full rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#dc2626)]" />
      </label>
      <div class="mt-3 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" class="storefront-action-secondary min-h-11 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#1f2937)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]" @click="showCancellation = false">Не отменять</button>
        <button type="button" class="storefront-action-destructive min-h-11 rounded-lg bg-[color:rgb(var(--storefront-destructive-rgb,185_28_28)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-destructive-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,153_27_27)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#dc2626)] disabled:opacity-50" :disabled="actionLoading" @click="cancelOrder">Отправить запрос</button>
      </div>
    </div>

    <Modal :show="pendingPayment !== null" title="Оплата заказа" size="lg" @close="pendingPayment = null">
      <div v-if="pendingPayment">
        <div class="mb-5 flex items-center justify-between gap-4 rounded-xl bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-4 py-3">
          <span class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ pendingPayment.scope === 'remaining' ? 'Доплата остатка' : 'Платёж по графику' }}</span>
          <span class="text-lg font-bold tabular-nums text-[color:var(--storefront-text,#030712)]">{{ formatCommerceMoney(pendingPayment.amount, order.currency_code) }}</span>
        </div>
        <CommercePaymentMethodPicker
          v-model="paymentMethod"
          :disabled-methods="order.item.type === 'vehicle' ? ['bank_transfer'] : []"
        />
        <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button type="button" class="storefront-action-ghost min-h-11 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] px-4 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#1f2937)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]" :disabled="actionLoading" @click="pendingPayment = null">Отмена</button>
          <button type="button" class="storefront-action-primary inline-flex min-h-11 items-center justify-center rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60" :disabled="actionLoading" @click="confirmPayment">{{ actionLoading ? 'Создаём платёж…' : 'Продолжить к оплате' }}</button>
        </div>
      </div>
    </Modal>
  </article>
</template>

<script setup lang="ts">
import { PhotoIcon } from '@heroicons/vue/24/outline'
import { useId } from 'vue'
import type { UUID } from '~/types/ids'
import { commerceCheckoutLocation, commerceOrderLocation } from '../adapters/commerceAdapters'
import { createCommerceApi } from '../api/commerceApi'
import { commerceFailureMessage } from '../composables/commerceErrors'
import { clearCommerceIdempotencyKey, getCommerceIdempotencyKey } from '../composables/commerceIdempotency'
import { formatCommerceMoney, isPositiveMoney } from '../money'
import type {
  CommerceCreatePaymentResult,
  CommerceOrder,
  CommercePayment,
  CommercePaymentMethod,
  CommerceScheduleItem,
} from '../types'
import CommercePaymentAction from './CommercePaymentAction.vue'
import CommercePaymentMethodPicker from './CommercePaymentMethodPicker.vue'

const props = withDefaults(defineProps<{
  order: CommerceOrder
  hasCompanies?: boolean
  expandedByDefault?: boolean
}>(), {
  hasCompanies: false,
  expandedByDefault: false,
})

const emit = defineEmits<{
  updated: [order: CommerceOrder]
}>()

const componentId = useId()
const paymentsTitleId = `commerce-payments-title-${componentId}`
const scheduleTitleId = `commerce-schedule-title-${componentId}`
const api = createCommerceApi(useRuntimeConfig())
const isExpanded = ref(props.expandedByDefault)
const relatedLoading = ref(false)
const relatedLoaded = ref(false)
const paymentsError = ref('')
const scheduleError = ref('')
const payments = ref<CommercePayment[]>([])
const schedule = ref<CommerceScheduleItem[]>([])
const checkingPaymentIds = ref<Set<UUID>>(new Set())
const paymentMethod = ref<CommercePaymentMethod>('sbp')
const paymentAction = ref<CommerceCreatePaymentResult | null>(null)
const actionLoading = ref(false)
const actionError = ref('')
const actionMessage = ref('')
const showCancellation = ref(false)
const cancellationReason = ref('')
const pendingPayment = ref<{
  scope: 'remaining' | 'scheduled'
  amount: string
  scheduleId?: UUID
} | null>(null)

const itemTypeLabel = computed(() => props.order.item.type === 'vehicle' ? 'Автомобиль' : 'Спецтехника')
const canPayRemaining = computed(() => props.order.status === 'reserved' && isPositiveMoney(props.order.remaining_amount))
const canApplyForLeasing = computed(() => props.hasCompanies && props.order.item.type === 'vehicle' && props.order.status === 'reserved')
const canCancel = computed(() => {
  const cancellableStatuses = props.order.item.type === 'vehicle'
    ? ['reserved', 'purchased']
    : ['payment_pending', 'reserved', 'purchased', 'leasing_pending', 'leasing_active']
  return cancellableStatuses.includes(props.order.status)
})
const shouldLoadSchedule = computed(() => props.order.purchase_type === 'leasing' || ['leasing_pending', 'leasing_active'].includes(props.order.status))

const safeProxyUrl = (value: string | null): string | null => value?.startsWith('/api/v1/') ? value : null
const formatDateTime = (value: string): string => new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const formatDate = (value: string): string => new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`))
const statusLabel = (status: string): string => ({ payment_pending: 'Ожидает оплаты', reserved: 'Зарезервирован', preordered: 'Предзаказ оформлен', purchased: 'Оплачен', leasing_pending: 'Ждёт оформления лизинга', leasing_active: 'В лизинге', cancellation_requested: 'Отмена обрабатывается', cancelled: 'Отменён', expired: 'Истёк', failed: 'Ошибка' })[status] ?? status
const statusClass = (status: string): string => ({ payment_pending: 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#78350f)]', reserved: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e3a8a)]', preordered: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e3a8a)]', purchased: 'bg-[color:rgb(var(--storefront-success-rgb,209_250_229)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#064e3b)]', leasing_pending: 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#78350f)]', leasing_active: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e3a8a)]', cancellation_requested: 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#78350f)]', cancelled: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]', expired: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]', failed: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#7f1d1d)]' })[status] ?? 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
const purchaseTypeLabel = (type: CommerceOrder['purchase_type']): string => ({
  reservation: 'Предоплата и резерв',
  preorder: 'Предзаказ с предоплатой',
  full_purchase: 'Полная покупка',
  leasing: 'Лизинг',
})[type] ?? type
const paymentStatusLabel = (status: string): string => ({ pending: 'Ожидает оплаты', pending_payment: 'Ожидает оплаты', processing: 'Обрабатывается', completed: 'Оплачен', failed: 'Ошибка', error: 'Ошибка', expired: 'Истёк', refunded: 'Возвращён' })[status] ?? status
const paymentStatusClass = (status: string): string => ({ completed: 'bg-[color:rgb(var(--storefront-success-rgb,209_250_229)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#065f46)]', pending: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]', pending_payment: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]', processing: 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#92400e)]', failed: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]', error: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]', refunded: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]' })[status] ?? 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)]'
const paymentTypeLabel = (type: string): string => ({ reservation: 'Предоплата', preorder: 'Предоплата по предзаказу', remaining_balance: 'Доплата остатка', full_purchase: 'Полная оплата', leasing: 'Лизинг', leasing_monthly: 'Лизинговый платёж' })[type] ?? type
const scheduleStatusLabel = (item: CommerceScheduleItem): string => item.is_paid ? 'Оплачен' : ({ pending: 'Ожидает оплаты', processing: 'Подтверждается', failed: 'Нужна повторная оплата', expired: 'Истёк' })[item.payment_status ?? ''] ?? 'К оплате'
const isPendingPayment = (payment: CommercePayment): boolean => ['pending', 'pending_payment', 'processing'].includes(payment.status)

const setPaymentChecking = (paymentId: UUID, checking: boolean): void => {
  const next = new Set(checkingPaymentIds.value)
  if (checking) next.add(paymentId)
  else next.delete(paymentId)
  checkingPaymentIds.value = next
}

const checkPaymentStatus = async (payment: CommercePayment): Promise<void> => {
  if (checkingPaymentIds.value.has(payment.id)) return
  setPaymentChecking(payment.id, true)
  actionError.value = ''
  try {
    const response = await api.getPaymentStatus(payment.order.type, payment.order.id, payment.id)
    await handlePaymentStatus(response.payment)
  } catch (error: unknown) {
    actionError.value = commerceFailureMessage(error, 'Не удалось проверить статус платежа.')
  } finally {
    setPaymentChecking(payment.id, false)
  }
}

const loadRelated = async (): Promise<void> => {
  relatedLoading.value = true
  paymentsError.value = ''
  scheduleError.value = ''

  const paymentRequest = api.getPayments(props.order.item.type, props.order.id)
  const scheduleRequest = shouldLoadSchedule.value
    ? api.getSchedule(props.order.item.type, props.order.id)
    : Promise.resolve({ items: [] as CommerceScheduleItem[] })
  const [paymentResult, scheduleResult] = await Promise.allSettled([paymentRequest, scheduleRequest])

  if (paymentResult.status === 'fulfilled') {
    payments.value = paymentResult.value.items
  } else {
    paymentsError.value = commerceFailureMessage(paymentResult.reason, 'Не удалось загрузить историю платежей.')
  }
  if (scheduleResult.status === 'fulfilled') {
    schedule.value = scheduleResult.value.items
  } else {
    scheduleError.value = commerceFailureMessage(scheduleResult.reason, 'Не удалось загрузить график платежей.')
  }

  relatedLoaded.value = paymentResult.status === 'fulfilled' && scheduleResult.status === 'fulfilled'
  relatedLoading.value = false
}

const toggleExpanded = (): void => {
  isExpanded.value = !isExpanded.value
  if (isExpanded.value && !relatedLoaded.value) void loadRelated()
}

const createPayment = async (scope: 'remaining' | 'scheduled', scheduleId?: UUID): Promise<void> => {
  if (props.order.item.type === 'vehicle' && paymentMethod.value === 'bank_transfer') {
    actionError.value = 'Для автомобиля выберите оплату картой или через СБП.'
    return
  }
  actionLoading.value = true
  actionError.value = ''
  actionMessage.value = ''
  const target = scheduleId ?? 'balance'
  const operationKey = `payment:${props.order.item.type}:${props.order.id}:${scope}:${target}:${paymentMethod.value}`
  try {
    paymentAction.value = await api.createPayment(props.order.item.type, props.order.id, {
      scope,
      ...(scheduleId ? { schedule_id: scheduleId } : {}),
      payment_method: paymentMethod.value,
    }, getCommerceIdempotencyKey(operationKey))
    clearCommerceIdempotencyKey(operationKey)
    actionMessage.value = paymentMethod.value === 'bank_transfer' ? 'Платёж создан и ожидает подтверждения перевода.' : 'Платёж создан. После оплаты статус обновится.'
    emit('updated', paymentAction.value.order)
    await loadRelated()
  } catch (error: unknown) {
    actionError.value = commerceFailureMessage(error, 'Не удалось создать платёж.')
  } finally {
    actionLoading.value = false
  }
}

const openPayment = (scope: 'remaining' | 'scheduled', amount: string, scheduleId?: UUID): void => {
  pendingPayment.value = { scope, amount, ...(scheduleId ? { scheduleId } : {}) }
}

const confirmPayment = async (): Promise<void> => {
  const pending = pendingPayment.value
  if (!pending) return
  await createPayment(pending.scope, pending.scheduleId)
  if (!actionError.value) pendingPayment.value = null
}

const handlePaymentStatus = async (updated: CommercePayment): Promise<void> => {
  payments.value = payments.value.map((payment) => payment.id === updated.id ? updated : payment)
  if (paymentAction.value?.payment.id === updated.id) {
    paymentAction.value = { ...paymentAction.value, payment: updated }
  }
  if (updated.status !== 'completed') return
  try {
    const response = await api.getOrder(props.order.item.type, props.order.id)
    emit('updated', response.order)
    await loadRelated()
  } catch (error: unknown) {
    actionError.value = commerceFailureMessage(error, 'Оплата подтверждена, но данные заказа обновятся после перезагрузки.')
  }
}

const cancelOrder = async (): Promise<void> => {
  actionLoading.value = true
  actionError.value = ''
  try {
    const response = await api.cancelOrder(props.order.item.type, props.order.id, cancellationReason.value)
    emit('updated', response.order)
    showCancellation.value = false
    actionMessage.value = response.order.status === 'cancellation_requested' ? 'Запрос на отмену принят.' : 'Заказ отменён.'
  } catch (error: unknown) {
    actionError.value = commerceFailureMessage(error, 'Не удалось отправить запрос на отмену.')
  } finally {
    actionLoading.value = false
  }
}

onMounted(() => {
  if (props.expandedByDefault) void loadRelated()
})
</script>
