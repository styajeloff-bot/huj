<template>
  <section v-if="visible" id="fast-deal-offers" class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-offers-title">
    <div class="flex items-center justify-between gap-3 flex-wrap mb-4">
      <div>
        <h2 id="fast-deal-offers-title" class="text-lg font-semibold text-gray-900">Запрос и коммерческие предложения</h2>
        <p class="text-sm text-gray-500">
          {{ deal.party === 'leasing' ? 'Ваше КП в сравнении с запросом дилера.' : 'Условия запроса и КП лизинговых компаний.' }}
        </p>
      </div>
      <div v-if="ctx.can('submit_offer')" class="flex gap-2">
        <button type="button" class="btn-outline text-sm px-3 py-1.5" @click="ctx.openOfferDialog(true)">Перенести запрошенные условия</button>
        <button type="button" class="btn-primary text-sm px-3 py-1.5" @click="ctx.openOfferDialog(false)">Сделать КП</button>
      </div>
    </div>

    <p v-if="selectedApplication && deal.party === 'initiator'" class="mb-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-900">
      Выбрано КП: {{ selectedApplication.leasing_company.name }}. Чтобы выбрать другое предложение, сначала снимите выбор.
    </p>

    <div class="overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead>
          <tr class="border-b border-gray-200 text-left align-bottom">
            <th scope="col" class="py-2 pr-4 font-medium text-gray-500">Параметр</th>
            <th scope="col" class="py-2 px-3 font-medium text-gray-900 bg-gray-50">Запрошено</th>
            <th
              v-for="application in deal.lc_applications"
              :key="application.id"
              scope="col"
              class="py-2 px-3 min-w-[11rem] font-medium text-gray-900"
              :class="application.selected ? 'bg-indigo-50' : ''"
            >
              <span class="block">{{ application.leasing_company.name }}</span>
              <span class="mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium" :class="lcStatusTone(application.status)">
                {{ lcStatusLabel(application.status) }}
              </span>
              <span v-if="application.rejection_reason" class="block mt-1 text-xs font-normal text-red-700">
                Причина: {{ application.rejection_reason }}
              </span>
            </th>
          </tr>
          <tr v-if="canSelectAny" class="border-b border-gray-200">
            <td class="py-2 pr-4"></td>
            <td class="bg-gray-50"></td>
            <td v-for="application in deal.lc_applications" :key="application.id" class="py-2 px-3" :class="application.selected ? 'bg-indigo-50' : ''">
              <button
                v-if="canSelect(application)"
                type="button"
                class="btn-primary text-sm px-3 py-1.5"
                @click="selecting = application"
              >
                Выбрать КП
              </button>
            </td>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          <tr v-for="row in rows" :key="row.key">
            <th scope="row" class="py-2 pr-4 text-left font-normal text-gray-500">{{ row.label }}</th>
            <td class="py-2 px-3 bg-gray-50 tabular-nums text-gray-900">{{ row.requested }}</td>
            <td
              v-for="application in deal.lc_applications"
              :key="application.id"
              class="py-2 px-3 tabular-nums"
              :class="[application.selected ? 'bg-indigo-50' : '', cellTone(row, application)]"
            >
              {{ cellText(row, application) }}
            </td>
          </tr>
          <tr v-if="hasPdf">
            <th scope="row" class="py-2 pr-4 text-left font-normal text-gray-500">PDF коммерческого предложения</th>
            <td class="py-2 px-3 bg-gray-50 text-gray-400">—</td>
            <td v-for="application in deal.lc_applications" :key="application.id" class="py-2 px-3" :class="application.selected ? 'bg-indigo-50' : ''">
              <button
                v-if="pdfFile(application)"
                type="button"
                class="text-blue-600 hover:text-blue-700"
                @click="download(pdfFile(application)!)"
              >
                Скачать
              </button>
              <span v-else class="text-gray-400">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="downloadError" role="alert" class="mt-2 text-sm text-red-600">{{ downloadError }}</p>
    <p v-if="!hasOffers && deal.party === 'initiator'" class="mt-3 text-sm text-gray-500">Коммерческих предложений пока нет.</p>

    <FastDealActionDialog
      v-if="selecting"
      title="Выбрать коммерческое предложение"
      :message="`Выбрать КП лизинговой компании «${selecting.leasing_company.name}»?`"
      :warnings="[
        'Остальные приглашения будут закрыты, а выбранная компания должна окончательно подтвердить сделку.',
        'Выбор можно снять, пока она не подтвердила сделку.',
      ]"
      confirm-text="Выбрать"
      :busy="ctx.busy.value"
      :error="selectError"
      @confirm="select"
      @close="selecting = null"
    />
    <FastDealOfferForm v-if="ctx.offerDialog.value" :deal="deal" :prefill="ctx.offerDialog.value.prefill" @close="ctx.closeOfferDialog()" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { parseFastDealError } from '../api/fastDealsApi'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import {
  formatMoney,
  formatPercent,
  lcStatusLabel,
  lcStatusTone,
  requestedFinancingAmount,
  sameDecimal,
} from '../composables/fastDealCardFormat'
import type { FastDealCard, FastDealFile, FastDealLcApplication, FastDealOffer } from '../types'
import FastDealActionDialog from './FastDealActionDialog.vue'
import FastDealOfferForm from './FastDealOfferForm.vue'

type RowKind = 'money' | 'percent' | 'term' | 'text'

interface RowSpec {
  key: string
  label: string
  kind: RowKind
  /** Raw requested value, to highlight a different offered one. */
  requestedRaw: string | null | undefined
  pick: (offer: FastDealOffer) => string | number | null | undefined
}

interface Row extends RowSpec {
  /** The requested value as shown in the «Запрошено» column. */
  requested: string
}

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const selecting = ref<FastDealLcApplication | null>(null)
const selectError = ref<ActionFailure | null>(null)
const downloadError = ref('')

/** DD only; a draft has no invitations yet. */
const visible = computed(() => ctx.isDD.value && props.deal.lc_applications.length > 0)
const selectedApplication = computed(() => props.deal.lc_applications.find(item => item.selected) ?? null)
const hasOffers = computed(() => props.deal.lc_applications.some(item => item.offer))
const canSelect = (application: FastDealLcApplication) =>
  ctx.can('select_offer') && application.status === 'offer_sent' && !!application.offer
const canSelectAny = computed(() => props.deal.lc_applications.some(canSelect))

const formatters: Record<RowKind, (value: string | number | null | undefined) => string> = {
  money: value => (value == null ? '—' : formatMoney(String(value))),
  percent: value => (value == null ? '—' : formatPercent(String(value))),
  term: value => (value == null ? '—' : `${value} мес.`),
  text: value => (value == null || value === '' ? '—' : String(value)),
}

const rows = computed<Row[]>(() => {
  const terms = props.deal.requested_terms
  const required: RowSpec[] = [
    { key: 'financing_amount', label: 'Сумма финансирования', kind: 'money', requestedRaw: requestedFinancingAmount(props.deal), pick: offer => offer.financing_amount },
    { key: 'down_payment', label: 'Аванс', kind: 'money', requestedRaw: terms.down_payment, pick: offer => offer.down_payment },
    { key: 'down_payment_percent', label: 'Аванс, %', kind: 'percent', requestedRaw: terms.down_payment_percent, pick: offer => offer.down_payment_percent },
    { key: 'lease_term_months', label: 'Срок лизинга', kind: 'term', requestedRaw: terms.lease_term_months != null ? String(terms.lease_term_months) : null, pick: offer => offer.lease_term_months },
    { key: 'monthly_payment', label: 'Ежемесячный платёж', kind: 'money', requestedRaw: terms.monthly_payment, pick: offer => offer.monthly_payment },
    { key: 'buyout_amount', label: 'Выкупной платёж', kind: 'money', requestedRaw: terms.buyout_amount, pick: offer => offer.buyout_amount },
    { key: 'total_cost', label: 'Стоимость договора', kind: 'money', requestedRaw: terms.total_cost, pick: offer => offer.total_cost },
  ]
  const optionalCandidates: RowSpec[] = [
    { key: 'rate', label: 'Ставка', kind: 'percent', requestedRaw: null, pick: offer => offer.rate },
    { key: 'markup', label: 'Удорожание', kind: 'money', requestedRaw: null, pick: offer => offer.markup },
    { key: 'total_interest', label: 'Общая переплата', kind: 'money', requestedRaw: null, pick: offer => offer.total_interest },
    { key: 'vat_refund', label: 'Возврат НДС', kind: 'money', requestedRaw: null, pick: offer => offer.vat_refund },
    { key: 'profit_tax_savings', label: 'Экономия на налоге на прибыль', kind: 'money', requestedRaw: null, pick: offer => offer.profit_tax_savings },
    { key: 'total_savings', label: 'Общая экономия', kind: 'money', requestedRaw: null, pick: offer => offer.total_savings },
  ]
  const optional = optionalCandidates.filter(row => props.deal.lc_applications.some(item => item.offer && row.pick(item.offer) != null))

  const extraKeys: string[] = []
  for (const application of props.deal.lc_applications) {
    for (const key of Object.keys(application.offer?.optional_financial_terms ?? {})) {
      if (!extraKeys.includes(key)) extraKeys.push(key)
    }
  }
  const extra: RowSpec[] = extraKeys.map(key => ({
    key: `extra:${key}`,
    label: key,
    kind: 'text' as const,
    requestedRaw: null,
    pick: (offer: FastDealOffer) => {
      const value = offer.optional_financial_terms?.[key]
      return typeof value === 'string' || typeof value === 'number' ? value : null
    },
  }))

  return [...required, ...optional, ...extra].map(row => ({
    ...row,
    requested: row.requestedRaw == null ? '—' : formatters[row.kind](row.kind === 'term' ? Number(row.requestedRaw) : row.requestedRaw),
  }))
})

function cellText(row: Row, application: FastDealLcApplication): string {
  return application.offer ? formatters[row.kind](row.pick(application.offer)) : '—'
}

/** An offered value that differs from the requested one is highlighted. */
function cellTone(row: Row, application: FastDealLcApplication): string {
  if (!application.offer || row.requestedRaw == null) return 'text-gray-900'
  const offered = row.pick(application.offer)
  if (offered == null) return 'text-gray-900'
  return sameDecimal(String(offered), row.requestedRaw) ? 'text-gray-900' : 'text-amber-700 font-medium'
}

const pdfFile = (application: FastDealLcApplication): FastDealFile | undefined =>
  application.offer?.pdf_file_id ? props.deal.files.find(file => file.id === application.offer?.pdf_file_id) : undefined
const hasPdf = computed(() => props.deal.lc_applications.some(item => pdfFile(item)))

async function select() {
  const application = selecting.value
  if (!application) return
  selectError.value = null
  const result = await ctx.run((etag) => ctx.api.selectOffer(application.id, etag))
  if (result.ok) selecting.value = null
  else selectError.value = result.error
}

async function download(file: FastDealFile) {
  downloadError.value = ''
  try {
    await ctx.api.downloadFile(props.deal.id, file.id, file.filename)
  } catch (error) {
    downloadError.value = parseFastDealError(error).detail
  }
}
</script>
