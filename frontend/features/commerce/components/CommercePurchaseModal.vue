<template>
  <Modal
    :show="show"
    :title="modalTitle"
    :closable="!processing"
    :close-on-overlay="!processing"
    size="xl"
    @close="handleClose"
  >
    <div data-storefront-block="client.order" v-if="loading" class="flex flex-col gap-3 py-4" aria-label="Загрузка выбранной техники" aria-busy="true">
      <div v-for="index in Math.max(items.length, 1)" :key="index" class="h-24 animate-pulse rounded-xl bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] motion-reduce:animate-none" />
    </div>

    <div data-storefront-block="client.order" v-else-if="loadError" class="rounded-xl border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-5" role="alert">
      <p class="font-semibold text-[color:var(--storefront-error-text,#7f1d1d)]">Не удалось подготовить оформление</p>
      <p class="mt-1 text-sm leading-relaxed text-[color:var(--storefront-error-text,#991b1b)]">{{ loadError }}</p>
      <button
        type="button"
        class="storefront-action-secondary mt-4 min-h-11 rounded-lg border border-[color:var(--storefront-destructive-border,#fca5a5)] bg-[color:rgb(var(--storefront-destructive-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-destructive-foreground,#991b1b)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_226_226)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#dc2626)]"
        @click="loadItems"
      >
        Повторить
      </button>
    </div>

    <template v-else-if="resolvedLines.length">
      <ol data-storefront-block="client.order" v-if="!hasOrderResults" class="mb-6 flex items-center justify-center gap-2" aria-label="Этапы оформления">
        <li v-for="stage in 3" :key="stage" class="flex items-center gap-2">
          <span
            class="grid h-8 w-8 place-items-center rounded-full text-sm font-semibold"
            :class="step >= stage ? 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)]' : 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)]'"
            :aria-current="step === stage ? 'step' : undefined"
          >
            <CheckIcon v-if="step > stage" class="text-[color:var(--storefront-icon,inherit)] h-4 w-4" aria-hidden="true" />
            <span v-else>{{ stage }}</span>
          </span>
          <span v-if="stage < 3" class="h-0.5 w-8 rounded sm:w-12" :class="step > stage ? 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))]' : 'bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]'" aria-hidden="true" />
        </li>
      </ol>

      <section data-storefront-block="client.order" v-if="hasOrderResults" aria-labelledby="commerce-order-success-title">
        <div class="text-center">
          <div class="mx-auto grid h-16 w-16 place-items-center rounded-full" :class="isComplete ? 'bg-[color:rgb(var(--storefront-success-rgb,209_250_229)/var(--tw-bg-opacity,1))]' : 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))]'">
            <CheckIcon class="h-8 w-8" :class="isComplete ? 'text-[color:var(--storefront-success-icon,#047857)]' : 'text-[color:var(--storefront-warning-icon,#b45309)]'" aria-hidden="true" />
          </div>
          <h3 id="commerce-order-success-title" class="mt-4 text-xl font-bold text-[color:var(--storefront-title,#030712)]">
            {{ createdOrderEntries.length === 1 ? 'Заказ создан' : 'Заказы созданы' }}
          </h3>
          <p class="mt-2 text-sm leading-relaxed text-[color:var(--storefront-text-muted,#4b5563)]">
            Цена и доступность проверены сервером. Дальнейшие действия доступны для каждого заказа отдельно.
          </p>
        </div>

        <div v-if="submitError" class="mt-5 rounded-xl border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] p-4" role="alert">
          <p class="font-semibold text-[color:var(--storefront-warning-text,#451a03)]">Часть заказов требует повторной попытки</p>
          <p class="mt-1 text-sm leading-relaxed text-[color:var(--storefront-warning-text,#78350f)]">{{ submitError }}</p>
          <button
            v-if="failedTargets.length"
            type="button"
            class="storefront-action-secondary mt-3 inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-[color:var(--storefront-secondary-border,#fcd34d)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#451a03)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,254_243_199)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#b45309)] disabled:cursor-wait disabled:opacity-60"
            :disabled="processing"
            @click="submitOrders"
          >
            <ArrowPathIcon v-if="processing" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Повторить только для неоформленных
          </button>
        </div>

        <div class="mt-6 flex flex-col gap-4">
          <article v-for="entry in createdOrderEntries" :key="entry.order.id" class="rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] p-4">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p class="font-semibold text-[color:var(--storefront-text,#030712)]">{{ entry.order.item_snapshot.title }}</p>
                <p class="mt-1 break-all font-mono text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Заказ {{ entry.order.id }}</p>
              </div>
              <NuxtLink
                :to="commerceOrderLocation(entry.order.item.type, entry.order.id)"
                class="inline-flex min-h-11 items-center justify-center rounded-lg border border-[color:var(--storefront-border,#d1d5db)] px-4 text-sm font-semibold text-[color:var(--storefront-link,#111827)] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
              >
                Открыть заказ
              </NuxtLink>
            </div>
            <CommercePaymentAction
              class="mt-4"
              :widget-data="entry.widgetData"
              :sbp-data="entry.sbpData"
              :payment="entry.payment"
              @status="payment => handleResultPaymentStatus(entry.resultIndex, payment)"
            />
          </article>
        </div>

        <div class="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">
          <NuxtLink
            :to="publicRoute('/cabinet?tab=my-cars')"
            class="storefront-action-primary inline-flex min-h-11 items-center justify-center rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2"
          >
            Перейти к моим заказам
          </NuxtLink>
          <button
            type="button"
            class="storefront-action-ghost min-h-11 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] px-5 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#1f2937)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
            @click="handleClose"
          >
            Закрыть
          </button>
        </div>
      </section>

      <section data-storefront-block="client.order" v-else-if="step === 1" aria-labelledby="commerce-purchase-type-title">
        <h3 id="commerce-purchase-type-title" class="text-base font-semibold text-[color:var(--storefront-title,#030712)]">Как оформить технику</h3>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <button
            v-if="canPrepay"
            type="button"
            class="storefront-action-ghost min-h-24 rounded-xl border-2 p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2"
            :class="purchaseType !== 'full_purchase' ? 'border-[color:var(--storefront-primary-border,#2563eb)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : 'border-[color:var(--storefront-primary-border,#e5e7eb)] hover:border-[color:var(--storefront-primary-hover-border,#d1d5db)]'"
            @click="purchaseType = prepaymentPurchaseType"
          >
            <span class="block font-semibold text-[color:var(--storefront-primary-foreground,#030712)]">{{ prepaymentTitle }}</span>
            <span class="mt-1 block text-sm leading-relaxed text-[color:var(--storefront-primary-foreground,#4b5563)]">{{ prepaymentDescription }}</span>
          </button>
          <button
            v-if="canFullPurchase"
            type="button"
            class="storefront-action-ghost min-h-24 rounded-xl border-2 p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2"
            :class="purchaseType === 'full_purchase' ? 'border-[color:var(--storefront-primary-border,#2563eb)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : 'border-[color:var(--storefront-primary-border,#e5e7eb)] hover:border-[color:var(--storefront-primary-hover-border,#d1d5db)]'"
            @click="purchaseType = 'full_purchase'"
          >
            <span class="block font-semibold text-[color:var(--storefront-primary-foreground,#030712)]">Полная покупка</span>
            <span class="mt-1 block text-sm leading-relaxed text-[color:var(--storefront-primary-foreground,#4b5563)]">Оплатить полную стоимость выбранной техники.</span>
          </button>
        </div>

        <label v-if="purchaseType !== 'full_purchase'" class="mt-5 block max-w-xs">
          <span class="text-sm font-semibold text-[color:var(--storefront-text,#1f2937)]">Размер предоплаты, %</span>
          <input
            v-model.trim="downPaymentPercent"
            type="text"
            inputmode="decimal"
            autocomplete="off"
            class="storefront-control mt-2 min-h-11 w-full rounded-lg border border-[color:var(--storefront-border,#d1d5db)] px-3 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
            :aria-invalid="percentError ? 'true' : undefined"
            aria-describedby="commerce-down-payment-help"
          >
          <span id="commerce-down-payment-help" class="mt-2 block text-sm" :class="percentError ? 'text-[color:var(--storefront-error-text,#b91c1c)]' : 'text-[color:var(--storefront-text-muted,#4b5563)]'">
            {{ percentError || 'Оставшаяся сумма будет доступна в карточке заказа.' }}
          </span>
        </label>

        <CommerceItemSummaryList class="mt-6" :items="resolvedLines" :amount="payableAmount" />

        <div class="mt-6 flex justify-end">
          <button type="button" class="storefront-action-primary min-h-11 rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2" @click="goToPaymentMethod">
            Продолжить
          </button>
        </div>
      </section>

      <section data-storefront-block="client.order" v-else-if="step === 2" aria-labelledby="commerce-payment-method-title">
        <h3 id="commerce-payment-method-title" class="text-[color:var(--storefront-title,inherit)] sr-only">Выбор способа оплаты</h3>
        <div v-if="hasVehicleItems" class="mb-4 rounded-lg border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-3 text-sm leading-relaxed text-[color:var(--storefront-text,#172554)]" role="status">
          Для оплаты автомобилей доступны карта и СБП.
        </div>
        <CommercePaymentMethodPicker
          v-model="paymentMethod"
          :disabled-methods="hasVehicleItems ? ['bank_transfer'] : []"
        />
        <CommerceItemSummaryList class="mt-6" :items="resolvedLines" :amount="payableAmount" />
        <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
          <button type="button" class="storefront-action-ghost min-h-11 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] px-5 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#1f2937)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]" @click="step = 1">Назад</button>
          <button type="button" class="storefront-action-primary min-h-11 rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2" @click="step = 3">Продолжить</button>
        </div>
      </section>

      <section data-storefront-block="client.order" v-else aria-labelledby="commerce-confirm-title">
        <h3 id="commerce-confirm-title" class="text-lg font-semibold text-[color:var(--storefront-title,#030712)]">Проверьте заказ</h3>
        <p class="mt-1 text-sm leading-relaxed text-[color:var(--storefront-text-muted,#4b5563)]">
          {{ purchaseSummaryLabel }} · {{ paymentMethodLabel }}
        </p>
        <CommerceItemSummaryList class="mt-5" :items="resolvedLines" :amount="payableAmount" />

        <div v-if="submitError" class="mt-5 rounded-xl border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-4" role="alert">
          <p class="font-semibold text-[color:var(--storefront-error-text,#7f1d1d)]">Оформление не завершено</p>
          <p class="mt-1 text-sm leading-relaxed text-[color:var(--storefront-error-text,#991b1b)]">{{ submitError }}</p>
        </div>

        <div class="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
          <button type="button" class="storefront-action-ghost min-h-11 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] px-5 text-sm font-semibold text-[color:var(--storefront-secondary-foreground,#1f2937)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] disabled:opacity-50" :disabled="processing" @click="step = 2">Назад</button>
          <button type="button" class="storefront-action-primary inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-60" :disabled="processing" @click="submitOrders">
            <ArrowPathIcon v-if="processing" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            {{ processing ? 'Создаём заказ…' : 'Подтвердить и оплатить' }}
          </button>
        </div>
      </section>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { ArrowPathIcon, CheckIcon } from '@heroicons/vue/24/outline'
import { createCommerceApi } from '../api/commerceApi'
import { createSpecialEquipmentCartApi } from '~/features/specialEquipment/api/specialEquipmentCartApi'
import { specialEquipmentCreateOrderResult } from '~/features/specialEquipment/adapters/specialEquipmentCommerceOrder'
import { commerceOrderLocation } from '../adapters/commerceAdapters'
import { commerceFailureMessage } from '../composables/commerceErrors'
import { clearCommerceIdempotencyKey, getCommerceIdempotencyKey } from '../composables/commerceIdempotency'
import { isValidPercent, normalizeMoney, percentageOfMoney, sumCommercePurchaseLines } from '../money'
import { resolveCommerceGroupPurchaseType } from '../purchaseType'
import type {
  CommerceCreateOrderResult,
  CommercePaymentMethod,
  CommercePayment,
  CommercePurchaseLine,
  CommercePurchaseSelection,
  CommercePurchaseType,
} from '../types'
import CommerceItemSummaryList from './CommerceItemSummaryList.vue'
import CommercePaymentAction from './CommercePaymentAction.vue'
import CommercePaymentMethodPicker from './CommercePaymentMethodPicker.vue'

const props = withDefaults(defineProps<{
  show?: boolean
  items: CommercePurchaseSelection[]
  initialPurchaseType?: CommercePurchaseType | null
}>(), {
  show: false,
  initialPurchaseType: null,
})

const emit = defineEmits<{
  close: []
  success: [results: CommerceCreateOrderResult[]]
}>()

const { apiPath, publicRoute } = useStorefront()
const api = createCommerceApi(useRuntimeConfig(), apiPath)
const specialEquipmentCartApi = createSpecialEquipmentCartApi(useRuntimeConfig(), apiPath)
const step = ref(1)
const purchaseType = ref<CommercePurchaseType>('reservation')
const paymentMethod = ref<CommercePaymentMethod>('sbp')
const downPaymentPercent = ref('10')
const resolvedLines = ref<CommercePurchaseLine[]>([])
const resolvedRootLines = ref<CommercePurchaseLine[]>([])
const resolvedGroups = ref<CommercePurchaseLine[][]>([])
const loading = ref(false)
const loadError = ref('')
const processing = ref(false)
const submitError = ref('')
const results = ref<CommerceCreateOrderResult[]>([])
interface CommercePurchaseTarget {
  line: CommercePurchaseLine
  lines: CommercePurchaseLine[]
  selectionIndex: number
  selection: CommercePurchaseSelection
}
const failedTargets = ref<CommercePurchaseTarget[]>([])

const itemSignature = computed(() => props.items.map((selection) => [
  selection.item.type,
  selection.item.id,
  selection.quantity,
  selection.cart_item_ids?.join(',') ?? '',
  selection.group_items?.map(item => `${item.item.type}:${item.item.id}:${item.quantity}:${item.price ?? ''}`).join(',') ?? '',
].join(':')).join('|'))
const hasOrderResults = computed(() => results.value.length > 0)
const createdOrderEntries = computed(() => results.value.flatMap((result, resultIndex) => {
  const primaryPayment = result.payments.find((payment) => result.orders.some((order) => order.id === payment.order.id))
  return result.orders.map((order) => ({
    order,
    payment: result.payments.find((payment) => payment.order.id === order.id) ?? null,
    widgetData: order.id === primaryPayment?.order.id ? result.widgetData : null,
    sbpData: order.id === primaryPayment?.order.id ? result.sbpData : null,
    resultIndex,
  }))
}))
const expectedOrderCount = computed(() => resolvedRootLines.value.length)
const hasVehicleItems = computed(() => resolvedLines.value.some((line) => line.item.ref.type === 'vehicle'))
const hasOnOrderItems = computed(() => resolvedLines.value.some((line) => line.item.availability === 'on_order'))
const hasAvailableItems = computed(() => resolvedLines.value.some((line) => line.item.availability !== 'on_order'))
const canPrepay = computed(() =>
  resolvedLines.value.length > 0 && resolvedLines.value.every(line => line.item.capabilities.can_preorder))
const canFullPurchase = computed(() =>
  resolvedLines.value.length > 0 && resolvedLines.value.every(line => line.item.capabilities.can_buy))
const prepaymentPurchaseType = computed<CommercePurchaseType>(() =>
  hasOnOrderItems.value && !hasAvailableItems.value ? 'preorder' : 'reservation')
const prepaymentTitle = computed(() => {
  if (!hasOnOrderItems.value) return 'Предоплата и резерв'
  return hasAvailableItems.value ? 'Предоплата и предзаказ' : 'Предзаказ с предоплатой'
})
const prepaymentDescription = computed(() => hasOnOrderItems.value
  ? 'Техника под заказ оформляется как независимый предзаказ без изменения статуса объявления.'
  : 'Закрепить конкретную единицу и оплатить остаток позже.')
const purchaseTargets = computed<CommercePurchaseTarget[]>(() => resolvedGroups.value.flatMap(
  (lines, selectionIndex) => lines[0] ? [{
    line: lines[0],
    lines,
    selectionIndex,
    selection: props.items[selectionIndex]!,
  }] : [],
))
const isComplete = computed(() => hasOrderResults.value && failedTargets.value.length === 0 && createdOrderEntries.value.length === expectedOrderCount.value)
const fullAmount = computed(() => sumCommercePurchaseLines(resolvedLines.value))
const payableAmount = computed(() => purchaseType.value !== 'full_purchase'
  ? percentageOfMoney(fullAmount.value, downPaymentPercent.value)
  : fullAmount.value)
const normalizedDownPaymentPercent = computed(() => normalizeMoney(downPaymentPercent.value))
const percentError = computed(() => purchaseType.value !== 'full_purchase' && !isValidPercent(downPaymentPercent.value, { maxInclusive: false })
  ? 'Введите значение от 1 до 99,99.'
  : '')
const paymentMethodLabel = computed(() => ({
  sbp: 'СБП',
  card: 'Банковская карта',
  bank_transfer: 'По реквизитам',
})[paymentMethod.value])
const purchaseSummaryLabel = computed(() =>
  purchaseType.value === 'full_purchase' ? 'Полная покупка' : prepaymentTitle.value)
const modalTitle = computed(() => {
  if (hasOrderResults.value) return isComplete.value ? (createdOrderEntries.value.length === 1 ? 'Заказ создан' : 'Заказы созданы') : 'Заказы созданы частично'
  if (step.value === 1) return 'Покупка техники'
  if (step.value === 2) return 'Способ оплаты'
  return 'Подтверждение'
})

const loadItems = async (): Promise<void> => {
  if (!props.show || props.items.length === 0) {
    resolvedLines.value = []
    resolvedRootLines.value = []
    resolvedGroups.value = []
    loadError.value = props.show ? 'Не выбрана техника для оформления.' : ''
    return
  }
  loading.value = true
  loadError.value = ''
  try {
    const requestedItems = props.items.flatMap(selection => (
      selection.group_items?.length
        ? selection.group_items
        : [{ item: selection.item, quantity: selection.quantity, price: null }]
    ))
    if (requestedItems.some((selection) => (
      !Number.isSafeInteger(selection.quantity)
      || selection.quantity < 1
      || (selection.item.type === 'vehicle' && selection.quantity !== 1)
    ))) {
      throw new Error('Сейчас один заказ может содержать только одну конкретную единицу техники. Уменьшите количество до 1 и повторите оформление.')
    }
    const groups = await Promise.all(props.items.map(async (selection) => {
      const groupItems = selection.group_items?.length
        ? selection.group_items
        : [{ item: selection.item, quantity: selection.quantity, price: null }]
      const responses = await Promise.all(groupItems.map(item => api.getItem(item.item)))
      return responses.map((response, index) => {
        const groupItem = groupItems[index]!
        return {
          item: groupItem.price === null
            ? response.item
            : { ...response.item, price: groupItem.price },
          quantity: groupItem.quantity,
        }
      })
    }))
    resolvedLines.value = groups.flat()
    resolvedRootLines.value = groups.flatMap(group => group[0] ? [group[0]] : [])
    resolvedGroups.value = groups
    if (!props.initialPurchaseType && !canFullPurchase.value && canPrepay.value) {
      purchaseType.value = prepaymentPurchaseType.value
    }
  } catch (error: unknown) {
    resolvedLines.value = []
    resolvedRootLines.value = []
    resolvedGroups.value = []
    loadError.value = commerceFailureMessage(error, 'Проверьте подключение и доступность выбранной техники.')
  } finally {
    loading.value = false
  }
}

const reset = (): void => {
  step.value = props.initialPurchaseType ? 2 : 1
  purchaseType.value = props.initialPurchaseType ?? 'reservation'
  paymentMethod.value = 'sbp'
  downPaymentPercent.value = '10'
  loadError.value = ''
  submitError.value = ''
  results.value = []
  failedTargets.value = []
  processing.value = false
}

const goToPaymentMethod = (): void => {
  if (percentError.value) return
  step.value = 2
}

const submitOrders = async (): Promise<void> => {
  submitError.value = ''
  if (purchaseType.value === 'full_purchase' && !canFullPurchase.value) {
    submitError.value = 'Полная покупка недоступна для выбранной техники.'
    step.value = 1
    return
  }
  if (purchaseType.value !== 'full_purchase' && !canPrepay.value) {
    submitError.value = 'Предоплата недоступна для выбранной техники.'
    step.value = 1
    return
  }
  if (percentError.value || payableAmount.value === null) {
    submitError.value = percentError.value || 'Для выбранной техники не указана стоимость.'
    return
  }
  if (hasVehicleItems.value && paymentMethod.value === 'bank_transfer') {
    submitError.value = 'Для автомобилей выберите оплату картой или через СБП.'
    step.value = 2
    return
  }
  if (purchaseTargets.value.some(target => (
    target.line.item.ref.type === 'vehicle' && target.line.quantity !== 1
  ))) {
    submitError.value = 'Сейчас один заказ может содержать только одну конкретную единицу техники. Уменьшите количество до 1 и повторите оформление.'
    return
  }
  const reservationPercent = purchaseType.value !== 'full_purchase'
    ? normalizedDownPaymentPercent.value
    : null
  if (purchaseType.value !== 'full_purchase' && reservationPercent === null) {
    submitError.value = 'Введите корректный размер предоплаты.'
    return
  }
  processing.value = true
  const created: CommerceCreateOrderResult[] = []
  const failures: Array<{ target: CommercePurchaseTarget; message: string }> = []
  const targets = failedTargets.value.length > 0 ? [...failedTargets.value] : [...purchaseTargets.value]

  for (const target of targets) {
    const { line, selectionIndex, selection } = target
    const targetPurchaseType = resolveCommerceGroupPurchaseType(
      purchaseType.value,
      target.lines.map(groupLine => groupLine.item),
    )
    const percentToken = reservationPercent ?? 'full'
    const cartSelectionToken = selection.cart_item_ids?.join(',') ?? line.item.ref.id
    const operationKey = `order:${line.item.ref.type}:${cartSelectionToken}:${selectionIndex}:${targetPurchaseType}:${paymentMethod.value}:${percentToken}`
    try {
      const result = line.item.ref.type === 'special_equipment' && selection.cart_item_ids?.length
        ? specialEquipmentCreateOrderResult(await specialEquipmentCartApi.createOrder({
            cart_item_ids: selection.cart_item_ids,
            purchase_type: targetPurchaseType,
            payment_method: paymentMethod.value,
            ...(targetPurchaseType !== 'full_purchase' && reservationPercent
              ? { down_payment_percent: reservationPercent }
              : {}),
          }, getCommerceIdempotencyKey(operationKey)))
        : await api.createOrder({
            item: line.item.ref,
            quantity: 1,
            purchase_type: targetPurchaseType,
            payment_method: paymentMethod.value,
            ...(targetPurchaseType !== 'full_purchase' && reservationPercent
              ? { down_payment_percent: reservationPercent }
              : {}),
          }, getCommerceIdempotencyKey(operationKey))
      if (result.orders.length !== 1) {
        throw new Error('Сервер вернул некорректное количество заказов для единицы техники.')
      }
      created.push(result)
      clearCommerceIdempotencyKey(operationKey)
    } catch (error: unknown) {
      failures.push({ target, message: `${line.item.title}: ${commerceFailureMessage(error, 'не удалось создать заказ')}` })
    }
  }

  results.value = [...results.value, ...created]
  failedTargets.value = failures.map((failure) => failure.target)
  processing.value = false
  if (failures.length > 0) {
    submitError.value = failures.map((failure) => failure.message).join(' ')
    return
  }
  emit('success', results.value)
}

const handleResultPaymentStatus = async (resultIndex: number, payment: CommercePayment): Promise<void> => {
  const result = results.value[resultIndex]
  if (!result) return
  let orders = result.orders
  if (payment.status === 'completed') {
    try {
      const response = await api.getOrder(payment.order.type, payment.order.id)
      orders = orders.map((order) => order.id === response.order.id ? response.order : order)
    } catch (error: unknown) {
      submitError.value = commerceFailureMessage(error, 'Оплата подтверждена, но данные заказа обновятся после перезагрузки.')
    }
  }
  results.value[resultIndex] = {
    ...result,
    orders,
    payments: result.payments.map((current) => current.id === payment.id ? payment : current),
  }
}

const handleClose = (): void => {
  if (processing.value) return
  emit('close')
}

watch(
  [() => props.show, itemSignature],
  ([isShown]) => {
    if (!isShown) return
    reset()
    void loadItems()
  },
  { immediate: true },
)

</script>
