<template>
  <section data-storefront-block="client.order"
    v-if="widgetData || sbpData || payment"
    class="rounded-xl border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4"
    :aria-labelledby="paymentTitleId"
  >
    <h3 :id="paymentTitleId" class="text-base font-semibold text-[color:var(--storefront-title,#030712)]">
      {{ widgetData || sbpData ? 'Продолжите оплату' : 'Статус платежа' }}
    </h3>
    <p class="mt-1 text-sm leading-relaxed text-[color:var(--storefront-text,#374151)]">
      {{ widgetData || sbpData
        ? 'Заказ уже создан. Откройте защищённую страницу платёжного провайдера.'
        : 'Для этого заказа создан отдельный платёж. Откройте заказ, чтобы продолжить оплату или проверить её состояние.' }}
    </p>

    <form
      v-if="safeFormUrl && widgetData"
      class="mt-4"
      method="post"
      :action="safeFormUrl"
    >
      <input class="storefront-control"
        v-for="(value, name) in widgetData.formParams"
        :key="name"
        type="hidden"
        :name="name"
        :value="value"
      >
      <button
        type="submit"
        class="storefront-action-primary inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2 sm:w-auto"
      >
        Перейти к оплате картой
      </button>
    </form>

    <div v-else-if="safeSbpUrl" class="mt-4 flex flex-col gap-3 sm:flex-row">
      <a
        :href="safeSbpUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="storefront-action-primary inline-flex min-h-11 items-center justify-center rounded-lg bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] focus-visible:ring-offset-2"
      >
        Открыть СБП
      </a>
      <button
        type="button"
        class="storefront-action-secondary min-h-11 rounded-lg border border-[color:var(--storefront-primary-border,#93c5fd)] bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-5 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#1e3a8a)] hover:bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
        @click="copySbpLink"
      >
        Скопировать ссылку
      </button>
    </div>

    <p v-else-if="widgetData || sbpData" class="mt-3 text-sm leading-relaxed text-[color:var(--storefront-error-text,#991b1b)]" role="alert">
      Платёжная ссылка отклонена проверкой безопасности. Откройте заказ и повторите оплату.
    </p>
    <p v-if="payment && !isPending" class="mt-3 text-sm font-medium text-[color:var(--storefront-text,#1f2937)]" role="status">
      {{ paymentStatusLabel }}
    </p>
    <p v-if="copyMessage" class="mt-3 text-sm font-medium text-[color:var(--storefront-success-text,#065f46)]" role="status">
      {{ copyMessage }}
    </p>
    <div v-if="payment && isPending" class="mt-4 border-t border-[color:var(--storefront-border,#bfdbfe)] pt-4">
      <button
        type="button"
        class="storefront-action-secondary inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-[color:var(--storefront-primary-border,#93c5fd)] bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 text-sm font-semibold text-[color:var(--storefront-primary-foreground,#1e3a8a)] hover:bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)] disabled:cursor-wait disabled:opacity-60"
        :disabled="checkingStatus"
        @click="checkStatus(false)"
      >
        <ArrowPathIcon v-if="checkingStatus" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        {{ checkingStatus ? 'Проверяем…' : 'Проверить статус платежа' }}
      </button>
      <p v-if="statusMessage" class="mt-2 text-sm text-[color:var(--storefront-text,#172554)]" role="status">{{ statusMessage }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import { useId } from 'vue'
import { createCommerceApi } from '../api/commerceApi'
import { commerceFailureMessage } from '../composables/commerceErrors'
import type { CommercePayment, CommercePaymentSbpData, CommercePaymentWidgetData } from '../types'

const props = defineProps<{
  widgetData?: CommercePaymentWidgetData | null
  sbpData?: CommercePaymentSbpData | null
  payment?: CommercePayment | null
}>()

const emit = defineEmits<{
  status: [payment: CommercePayment]
}>()

const copyMessage = ref('')
const checkingStatus = ref(false)
const statusMessage = ref('')
const paymentTitleId = `commerce-online-payment-title-${useId()}`
const api = createCommerceApi(useRuntimeConfig())
const POLL_INTERVAL_MS = 5_000
const MAX_POLL_ATTEMPTS = 12
let pollTimer: number | null = null
let pollAttempts = 0

const httpsUrl = (value: string | undefined): string | null => {
  if (!value) return null
  try {
    return new URL(value).protocol === 'https:' ? value : null
  } catch {
    return null
  }
}

const safeFormUrl = computed(() => httpsUrl(props.widgetData?.formUrl))
const safeSbpUrl = computed(() => httpsUrl(props.sbpData?.sbpLink))
const isPending = computed(() => props.payment?.status === 'pending' || props.payment?.status === 'pending_payment' || props.payment?.status === 'processing')
const shouldPoll = computed(() => isPending.value && (props.payment?.payment_method === 'card' || props.payment?.payment_method === 'sbp'))
const paymentStatusLabel = computed(() => ({
  completed: 'Оплата подтверждена.',
  failed: 'Платёж завершился ошибкой.',
  error: 'Платёж завершился ошибкой.',
  expired: 'Срок действия платежа истёк.',
  refunded: 'Платёж возвращён.',
})[props.payment?.status ?? ''] ?? `Статус: ${props.payment?.status ?? 'неизвестен'}`)

const copySbpLink = async (): Promise<void> => {
  if (!safeSbpUrl.value || !navigator.clipboard) return
  try {
    await navigator.clipboard.writeText(safeSbpUrl.value)
    copyMessage.value = 'Ссылка СБП скопирована.'
  } catch {
    copyMessage.value = 'Не удалось скопировать ссылку.'
  }
}

const stopPolling = (): void => {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

const schedulePolling = (): void => {
  stopPolling()
  if (!import.meta.client || !shouldPoll.value || document.hidden || pollAttempts >= MAX_POLL_ATTEMPTS) return
  pollTimer = window.setTimeout(() => {
    pollTimer = null
    void checkStatus(true)
  }, POLL_INTERVAL_MS)
}

const checkStatus = async (automated = false): Promise<void> => {
  if (!props.payment || checkingStatus.value) return
  if (automated && (!shouldPoll.value || document.hidden || pollAttempts >= MAX_POLL_ATTEMPTS)) return
  if (automated) pollAttempts += 1
  checkingStatus.value = true
  statusMessage.value = ''
  let remainsPending = shouldPoll.value
  try {
    const response = await api.getPaymentStatus(
      props.payment.order.type,
      props.payment.order.id,
      props.payment.id,
    )
    emit('status', response.payment)
    remainsPending = ['pending', 'pending_payment', 'processing'].includes(response.payment.status)
    statusMessage.value = response.payment.status === 'completed'
      ? 'Оплата подтверждена.'
      : response.payment.status === 'failed' || response.payment.status === 'error'
        ? 'Платёж не завершён. Выберите повторную оплату в заказе.'
        : 'Банк ещё не подтвердил платёж. Проверьте статус позже.'
  } catch (error: unknown) {
    statusMessage.value = commerceFailureMessage(error, 'Не удалось проверить статус платежа.')
  } finally {
    checkingStatus.value = false
    if (automated && remainsPending) schedulePolling()
  }
}

const handleVisibilityChange = (): void => {
  if (document.hidden) {
    stopPolling()
    return
  }
  schedulePolling()
}

watch(
  () => [props.payment?.id, props.payment?.status, props.payment?.payment_method] as const,
  ([paymentId], previous) => {
    const previousPaymentId = previous?.[0]
    if (paymentId !== previousPaymentId) pollAttempts = 0
    if (!shouldPoll.value) {
      stopPolling()
      return
    }
    schedulePolling()
  },
  { immediate: true },
)

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  schedulePolling()
})

onBeforeUnmount(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>
