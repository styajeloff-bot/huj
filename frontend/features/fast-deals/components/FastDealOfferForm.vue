<template>
  <Modal
    :show="true"
    title="Коммерческое предложение"
    :subtitle="deal.display_number"
    size="3xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-offer-form" class="space-y-5" novalidate @submit.prevent="submit">
      <p v-if="!application" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
        Приглашение вашей компании не найдено: КП отправить нельзя.
      </p>
      <p class="text-sm text-gray-600">
        На одно приглашение в цикле согласования отправляется одно КП; после отправки изменить его нельзя.
        Обязательны сумма финансирования, аванс, срок, ежемесячный платёж и стоимость договора.
      </p>

      <div class="flex items-center justify-between gap-3 rounded-lg bg-gray-50 p-3 text-sm">
        <span class="text-gray-700">Запрошено: аванс {{ formatMoney(deal.requested_terms.down_payment) }}, срок {{ deal.requested_terms.lease_term_months ?? '—' }} мес., платёж {{ formatMoney(deal.requested_terms.monthly_payment) }}</span>
        <button type="button" class="btn-outline text-sm px-3 py-1.5 shrink-0" :disabled="ctx.busy.value" @click="fillFromRequested">
          Перенести запрошенные условия
        </button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FastDealCardField
          v-for="field in FIELDS"
          :key="field.key"
          :label="field.label"
          :required="field.required"
          :for-id="`fast-deal-offer-${field.key}`"
          :error="errorOf(field.key)"
        >
          <input
            :id="`fast-deal-offer-${field.key}`"
            v-model="form[field.key]"
            type="text"
            :inputmode="field.kind === 'term' ? 'numeric' : 'decimal'"
            autocomplete="off"
            class="input-field tabular-nums"
            :class="errorOf(field.key) ? 'border-red-500' : ''"
            :disabled="ctx.busy.value"
          />
        </FastDealCardField>
      </div>

      <fieldset class="space-y-2">
        <legend class="text-sm font-medium text-gray-700">Дополнительные условия</legend>
        <p class="text-xs text-gray-500">Необязательные показатели в виде «название — значение».</p>
        <div v-for="(row, index) in extras" :key="index" class="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
          <input v-model="row.key" type="text" maxlength="64" class="input-field" placeholder="Название" :aria-label="`Название условия ${index + 1}`" :disabled="ctx.busy.value" />
          <input v-model="row.value" type="text" maxlength="255" class="input-field" placeholder="Значение" :aria-label="`Значение условия ${index + 1}`" :disabled="ctx.busy.value" />
          <button type="button" class="px-2 py-2 text-red-600 hover:text-red-700" :disabled="ctx.busy.value" :aria-label="`Убрать условие ${index + 1}`" @click="extras.splice(index, 1)">×</button>
        </div>
        <p v-if="extrasError" role="alert" class="text-xs text-red-600">{{ extrasError }}</p>
        <button v-if="extras.length < 10" type="button" class="text-sm text-blue-600 hover:text-blue-700" :disabled="ctx.busy.value" @click="extras.push({ key: '', value: '' })">
          + Добавить условие
        </button>
      </fieldset>

      <FastDealCardField label="PDF коммерческого предложения" for-id="fast-deal-offer-pdf" hint="Необязательно" :error="errorOf('pdf_file_id') || errorOf('files') || pdfError">
        <input
          id="fast-deal-offer-pdf"
          type="file"
          accept=".pdf,application/pdf"
          class="block w-full text-sm text-gray-700 file:mr-3 file:rounded-lg file:border-0 file:bg-gray-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-gray-200"
          :disabled="ctx.busy.value"
          @change="onPdf"
        />
        <p v-if="uploadedPdfId" class="mt-1 text-xs text-green-700">Файл загружен и будет приложен к КП.</p>
      </FastDealCardField>

      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="submit" form="fast-deal-offer-form" class="btn-primary" :disabled="ctx.busy.value || !application" :aria-busy="ctx.busy.value">
        {{ ctx.busy.value ? 'Отправляем…' : 'Отправить КП' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import {
  formatMoney,
  moneyToInput,
  parseMoneyInput,
  parsePercentInput,
  parseTermInput,
  requestedFinancingAmount,
} from '../composables/fastDealCardFormat'
import type { FastDealCard, OfferBody } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const MAX_PDF_BYTES = 50 * 1024 * 1024

const FIELDS = [
  { key: 'financing_amount', label: 'Сумма финансирования, ₽', required: true, kind: 'money' },
  { key: 'down_payment', label: 'Аванс, ₽', required: true, kind: 'money' },
  { key: 'down_payment_percent', label: 'Аванс, %', required: false, kind: 'percent' },
  { key: 'lease_term_months', label: 'Срок лизинга, мес.', required: true, kind: 'term' },
  { key: 'monthly_payment', label: 'Ежемесячный платёж, ₽', required: true, kind: 'money' },
  { key: 'total_cost', label: 'Стоимость договора, ₽', required: true, kind: 'money' },
  { key: 'buyout_amount', label: 'Выкупной платёж, ₽', required: false, kind: 'money' },
  { key: 'rate', label: 'Ставка, % годовых', required: false, kind: 'percent' },
  { key: 'markup', label: 'Удорожание, ₽', required: false, kind: 'money' },
  { key: 'total_interest', label: 'Общая переплата, ₽', required: false, kind: 'money' },
  { key: 'vat_refund', label: 'Возврат НДС, ₽', required: false, kind: 'money' },
  { key: 'profit_tax_savings', label: 'Экономия на налоге на прибыль, ₽', required: false, kind: 'money' },
  { key: 'total_savings', label: 'Общая экономия, ₽', required: false, kind: 'money' },
] as const

type FieldKey = (typeof FIELDS)[number]['key']

/** The server may name an amount differently from the request body. */
const ALIASES: Record<string, FieldKey> = { total_amount: 'financing_amount', contract_cost: 'total_cost' }
const KNOWN = new Set<string>([...FIELDS.map(field => field.key), ...Object.keys(ALIASES), 'pdf_file_id', 'files', 'optional_financial_terms'])

const props = defineProps<{ deal: FastDealCard; prefill: boolean }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const application = computed(() => ctx.ownApplication.value)

const form = reactive<Record<FieldKey, string>>({
  financing_amount: '',
  down_payment: '',
  down_payment_percent: '',
  lease_term_months: '',
  monthly_payment: '',
  total_cost: '',
  buyout_amount: '',
  rate: '',
  markup: '',
  total_interest: '',
  vat_refund: '',
  profit_tax_savings: '',
  total_savings: '',
})
const extras = ref<{ key: string; value: string }[]>([])
const pdf = ref<File | null>(null)
const uploadedPdfId = ref('')
const local = reactive<Record<string, string>>({})
const extrasError = ref('')
const pdfError = ref('')
const serverError = ref<ActionFailure | null>(null)

/** Copies the requested terms of the dealer into the offer; the leasing company then adjusts them. */
function fillFromRequested() {
  const terms = props.deal.requested_terms
  form.financing_amount = moneyToInput(requestedFinancingAmount(props.deal))
  form.down_payment = moneyToInput(terms.down_payment)
  form.down_payment_percent = moneyToInput(terms.down_payment_percent)
  form.lease_term_months = terms.lease_term_months != null ? String(terms.lease_term_months) : ''
  form.monthly_payment = moneyToInput(terms.monthly_payment)
  form.total_cost = moneyToInput(terms.total_cost)
  form.buyout_amount = moneyToInput(terms.buyout_amount)
}

if (props.prefill) fillFromRequested()

const errorOf = (field: string): string => {
  if (local[field]) return local[field]
  const failure = serverError.value
  if (!failure?.field) return ''
  return failure.field === field || ALIASES[failure.field] === field ? failure.detail : ''
}
const generalError = computed(() => (serverError.value && !(serverError.value.field && KNOWN.has(serverError.value.field)) ? serverError.value : null))

function onPdf(event: Event) {
  const input = event.target as HTMLInputElement
  pdf.value = input.files?.[0] ?? null
  uploadedPdfId.value = ''
  pdfError.value = ''
}

function buildBody(): OfferBody | null {
  for (const key of Object.keys(local)) delete local[key]
  extrasError.value = ''
  const body: Record<string, unknown> = {}

  for (const field of FIELDS) {
    const raw = form[field.key].trim()
    if (!raw) {
      if (field.required) local[field.key] = 'Обязательное поле'
      continue
    }
    if (field.kind === 'term') {
      const term = parseTermInput(raw)
      if (term === null || term < 12 || term > 84) local[field.key] = 'Срок — целое число от 12 до 84 месяцев'
      else body[field.key] = term
    } else if (field.kind === 'percent') {
      const percent = parsePercentInput(raw)
      if (percent === null) local[field.key] = 'Укажите процент, например 12.5'
      else body[field.key] = percent
    } else {
      const amount = parseMoneyInput(raw)
      if (amount === null) local[field.key] = 'Укажите сумму, например 2500000.00'
      else body[field.key] = amount
    }
  }

  const optional: Record<string, string> = {}
  for (const row of extras.value) {
    const key = row.key.trim()
    const value = row.value.trim()
    if (!key && !value) continue
    if (!key || !value) {
      extrasError.value = 'У каждого дополнительного условия должны быть название и значение'
      break
    }
    optional[key] = value
  }
  if (Object.keys(optional).length) body.optional_financial_terms = optional

  if (pdf.value && pdf.value.size === 0) pdfError.value = 'Файл пустой'
  else if (pdf.value && pdf.value.size > MAX_PDF_BYTES) pdfError.value = 'Размер файла не должен превышать 50 МБ'
  else pdfError.value = ''

  if (Object.keys(local).length > 0 || extrasError.value || pdfError.value) return null
  return body as unknown as OfferBody
}

async function submit() {
  serverError.value = null
  const app = application.value
  if (!app) return
  const body = buildBody()
  if (!body) return

  // The PDF is uploaded first (bound to this invitation) and referenced from the offer.
  if (pdf.value && !uploadedPdfId.value) {
    const file = pdf.value
    const uploaded = await ctx.run((etag, card) =>
      ctx.api.uploadFiles(card.id, etag, { kind: 'lc_offer_pdf', files: [file], leasingApplicationId: app.id }),
    )
    if (!uploaded.ok) {
      serverError.value = uploaded.error
      return
    }
    const stored = [...uploaded.value.files].reverse().find(item => item.kind === 'lc_offer_pdf')
    if (!stored) {
      pdfError.value = 'Не удалось получить загруженный файл. Повторите попытку.'
      return
    }
    uploadedPdfId.value = stored.id
  }
  if (uploadedPdfId.value) body.pdf_file_id = uploadedPdfId.value

  const result = await ctx.run((etag) => ctx.api.submitOffer(app.id, etag, body))
  if (result.ok) emit('close')
  else serverError.value = result.error
}
</script>
