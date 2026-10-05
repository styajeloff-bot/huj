<template>
  <Modal
    :show="show"
    title="График платежей"
    :subtitle="modalSubtitle"
    :show-footer="false"
    size="full"
    body-class="p-0"
    @close="$emit('close')"
  >
    <div data-storefront-block="client.checkout" class="mx-auto max-w-[1920px] px-5 py-5 sm:px-6">
      <section class="overflow-hidden rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-sm">
        <div class="border-b border-[color:var(--storefront-border,#e5e7eb)] px-4 py-4 sm:px-5">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div class="text-xs font-medium uppercase tracking-wide text-[color:var(--storefront-text-muted,#6b7280)]">Источник условий</div>
              <div class="mt-1 text-lg font-semibold text-[color:var(--storefront-text,#111827)]">{{ scheduleSourceLabel }}</div>
              <div class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Первый платеж: {{ firstPaymentPeriod }}</div>
            </div>
            <div class="flex flex-wrap gap-2">
              <div
                v-for="stat in compactScheduleStats"
                :key="stat.label"
                class="rounded-md border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-3 py-2"
              >
                <div class="text-[11px] font-medium uppercase tracking-wide text-[color:var(--storefront-text-muted,#6b7280)]">{{ stat.label }}</div>
                <div class="mt-0.5 whitespace-nowrap text-sm font-semibold text-[color:var(--storefront-text,#111827)]">{{ stat.value }}</div>
              </div>
            </div>
          </div>
        </div>

        <p v-if="loading" class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-10 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
          Загружаем условия КП...
        </p>
        <p v-else-if="error" class="m-4 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
          {{ error }}
        </p>
        <p v-else-if="paymentRows.length === 0" class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-4 py-10 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
          Для графика платежей не хватает срока или ежемесячного платежа.
        </p>

        <div v-else>
          <div class="border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-4 py-3 sm:px-5">
            <div class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <div class="font-semibold text-[color:var(--storefront-text,#111827)]">Помесячный график</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ paymentRows.length }} платежей</div>
            </div>
          </div>
          <div class="max-h-[62vh] overflow-auto">
            <div
              class="sticky top-0 z-10 grid grid-cols-[80px_minmax(180px,1fr)_minmax(140px,180px)_minmax(140px,180px)] border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-xs font-semibold uppercase tracking-wide text-[color:var(--storefront-text-muted,#4b5563)]"
            >
              <div class="px-4 py-2">Месяц</div>
              <div class="px-4 py-2">Период</div>
              <div class="px-4 py-2 text-right">Платеж</div>
              <div class="px-4 py-2 text-right">Остаток</div>
            </div>
            <div
              v-for="row in paymentRows"
              :key="row.number"
              class="grid grid-cols-[80px_minmax(180px,1fr)_minmax(140px,180px)_minmax(140px,180px)] border-b border-[color:var(--storefront-border,#f3f4f6)] text-sm last:border-b-0 hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/0.4)]"
            >
              <div class="px-4 py-2 font-medium text-[color:var(--storefront-text,#111827)]">{{ row.number }}</div>
              <div class="px-4 py-2 text-[color:var(--storefront-text,#374151)]">{{ row.period }}</div>
              <div class="px-4 py-2 text-right font-medium text-[color:var(--storefront-text,#111827)]">{{ formatPrice(row.amount) }}</div>
              <div class="px-4 py-2 text-right text-[color:var(--storefront-text-muted,#4b5563)]">
                {{ row.remaining === null ? '—' : formatPrice(row.remaining) }}
              </div>
            </div>
          </div>
          <div
            class="grid grid-cols-[80px_minmax(180px,1fr)_minmax(140px,180px)_minmax(140px,180px)] border-t border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] text-sm"
          >
            <div class="px-4 py-3" />
            <div class="px-4 py-3 font-semibold text-[color:var(--storefront-text,#111827)]">Итого</div>
            <div class="px-4 py-3 text-right font-semibold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(totalPaymentsWithAdvance) }}</div>
            <div class="px-4 py-3 text-right text-[color:var(--storefront-text-muted,#6b7280)]">—</div>
          </div>
        </div>
      </section>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { useNotificationCompanyRequest } from '~/features/notifications'
const { request: notificationRequest } = useNotificationCompanyRequest()
import { computed, ref, watch } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import type { Application } from '@/types'
import type { ClientLeasingResponsesResponse, LeasingProposal } from '~/features/leasing/api/leasingApi'

type ApplicationCompatible = Application & Record<string, unknown>
type ScheduleSourceKind = 'requested' | 'preliminary' | 'final'

interface LcaListItem {
  id: string
  application_id: string
  leasing_company_id: string
  leasing_company_name?: string | null
  display_number?: string | null
}

interface PaymentRow {
  number: number | 'Аванс'
  period: string
  amount: number
  remaining: number | null
}

interface SummaryCard {
  label: string
  value: string
  hint?: string
}

const props = defineProps<{
  show: boolean
  item: LcaListItem
  application: ApplicationCompatible | null
  sourceKind?: ScheduleSourceKind | null
  sourceProposal?: LeasingProposal | null
}>()

defineEmits<{ close: [] }>()

const config = useRuntimeConfig()
const { formatPrice } = useFormatPrice()

const clientResponses = ref<ClientLeasingResponsesResponse | null>(null)
const loading = ref(false)
const error = ref('')

const field = (source: Record<string, unknown> | null | undefined, name: string): unknown => source?.[name]

const numberLikeField = (source: Record<string, unknown> | null | undefined, name: string): number | string | null => {
  const value = field(source, name)
  return typeof value === 'number' || typeof value === 'string' ? value : null
}

const toNumber = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const modalSubtitle = computed(() => {
  const applicationNumber = props.item.display_number || String(field(props.application, 'display_number') || '—')
  return `Заявка ${applicationNumber}`
})

const matchedResponse = computed(() => {
  const responses = clientResponses.value?.responses || []
  return responses.find(response => String(response.leasing_company?.id || '') === String(props.item.leasing_company_id)) || null
})

const proposalByKind = (kind: 'preliminary' | 'final'): LeasingProposal | null => {
  if (props.sourceProposal?.kind === kind) return props.sourceProposal
  const proposals = matchedResponse.value?.proposals || []
  const matching = proposals.filter(proposal => proposal.kind === kind)
  matching.sort((a, b) => b.position - a.position)
  return matching[0] || null
}

const finalProposal = computed(() => proposalByKind('final'))
const preliminaryProposal = computed(() => proposalByKind('preliminary'))

const sourceKind = computed<ScheduleSourceKind | null>(() => props.sourceKind || null)

const scheduleSource = computed<Record<string, unknown> | null>(() => {
  if (sourceKind.value === 'requested') return props.application
  if (sourceKind.value === 'preliminary') return preliminaryProposal.value as Record<string, unknown> | null
  if (sourceKind.value === 'final') return finalProposal.value as Record<string, unknown> | null
  return (
    (finalProposal.value as Record<string, unknown> | null)
    || (preliminaryProposal.value as Record<string, unknown> | null)
    || props.application
  )
})

const scheduleSourceLabel = computed(() => {
  if (sourceKind.value === 'final') return 'Итоговое КП'
  if (sourceKind.value === 'preliminary') return 'Предварительное КП'
  if (sourceKind.value === 'requested') return 'Запрошенные условия'
  if (finalProposal.value) return 'Итоговое КП'
  if (preliminaryProposal.value) return 'Предварительное КП'
  return 'Запрошенные условия'
})

const termMonths = computed(() => toNumber(numberLikeField(scheduleSource.value, 'lease_term_months')))
const monthlyPayment = computed(() => toNumber(numberLikeField(scheduleSource.value, 'monthly_payment')))
const downPaymentPercent = computed(() => toNumber(numberLikeField(scheduleSource.value, 'down_payment_percent')))
const downPayment = computed(() => toNumber(numberLikeField(scheduleSource.value, 'down_payment')))

const addMonths = (date: Date, months: number): Date => {
  const next = new Date(date)
  next.setMonth(next.getMonth() + months)
  return next
}

const formatPeriod = (date: Date): string => {
  return date.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
}

const monthlyRows = computed<PaymentRow[]>(() => {
  const term = termMonths.value
  const payment = monthlyPayment.value
  if (!term || !payment || term <= 0 || payment <= 0) return []

  const start = new Date()
  start.setDate(1)

  return Array.from({ length: term }, (_, index) => {
    const number = index + 1
    return {
      number,
      period: formatPeriod(addMonths(start, number)),
      amount: payment,
      remaining: payment * (term - number),
    }
  })
})

const advanceRow = computed<PaymentRow | null>(() => {
  const advance = downPayment.value
  if (advance === null || advance <= 0) return null
  return {
    number: 'Аванс',
    period: 'Авансовый платёж',
    amount: advance,
    remaining: null,
  }
})

const paymentRows = computed<PaymentRow[]>(() => {
  const rows = monthlyRows.value
  return advanceRow.value ? [advanceRow.value, ...rows] : rows
})

const totalPayments = computed(() => monthlyRows.value.reduce((sum, row) => sum + row.amount, 0))
const totalPaymentsWithAdvance = computed(() => paymentRows.value.reduce((sum, row) => sum + row.amount, 0))
const firstPaymentPeriod = computed(() => paymentRows.value[0]?.period || '—')

const formatMoneyOrDash = (value: number | null) => (value === null ? '—' : formatPrice(value))
const formatMonthsOrDash = (value: number | null) => (value === null ? '—' : `${value} мес.`)
const formatPercentOrDash = (value: number | null) => (value === null ? '—' : `${value}%`)

const scheduleSummaryCards = computed<SummaryCard[]>(() => [
  {
    label: 'Срок',
    value: formatMonthsOrDash(termMonths.value),
    hint: 'Количество ежемесячных платежей',
  },
  {
    label: 'Ежемесячный платеж',
    value: formatMoneyOrDash(monthlyPayment.value),
    hint: 'Без учета дополнительных комиссий',
  },
  {
    label: 'Аванс',
    value: downPayment.value !== null ? formatPrice(downPayment.value) : formatPercentOrDash(downPaymentPercent.value),
    hint: downPayment.value !== null && downPaymentPercent.value !== null ? `${downPaymentPercent.value}%` : undefined,
  },
  {
    label: 'Сумма платежей',
    value: paymentRows.value.length > 0 ? formatPrice(totalPaymentsWithAdvance.value) : '—',
    hint: 'Сумма по графику с авансом',
  },
])

const compactScheduleStats = computed<SummaryCard[]>(() => scheduleSummaryCards.value)

const loadResponses = async () => {
  if (!props.show || !props.item.application_id) return
  loading.value = true
  error.value = ''
  try {
    const response = await notificationRequest<ClientLeasingResponsesResponse>(
      `/api/v1/applications/${props.item.application_id}/leasing-responses`,
      { baseURL: config.public.apiBase, credentials: 'include' },
    )
    clientResponses.value = response
  } catch {
    clientResponses.value = null
    error.value = 'Не удалось загрузить условия КП для графика платежей.'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.show, props.item.application_id, props.item.leasing_company_id, props.sourceProposal?.id],
  () => {
    if (props.show) void loadResponses()
  },
  { immediate: true },
)
</script>
