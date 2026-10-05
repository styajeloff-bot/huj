<template>
  <div class="bg-white rounded-lg shadow-sm p-6">
    <div class="flex items-center justify-between mb-4 flex-wrap gap-3">
      <h2 class="text-lg font-semibold text-gray-900">
        {{ kind === 'preliminary' ? 'Предварительное КП' : 'Итоговое КП' }}
      </h2>
      <span v-if="disabled" class="text-xs text-gray-500">
        {{ disabledReason || 'Расчёт зафиксирован.' }}
      </span>
    </div>

    <form
      class="space-y-4"
      :aria-label="kind === 'preliminary' ? 'Предварительное КП' : 'Итоговое КП'"
      @input="dirty = true"
      @submit.prevent="onSubmit"
    >
      <!-- Стоимость имущества (read-only) -->
      <div class="p-3 bg-gray-50 rounded-lg border border-gray-200 flex justify-between items-center">
        <span class="text-sm font-semibold text-gray-800">
          Стоимость имущества
        </span>
        <span class="text-base font-bold text-gray-900 tabular-nums">
          {{ formatPrice(totalAmount) }}
        </span>
      </div>

      <!-- Первоначальный взнос -->
      <div class="bg-white rounded-lg p-3 border border-gray-200">
        <label class="text-sm font-semibold text-gray-800 block mb-2">
          Первоначальный взнос
        </label>
        <div class="flex space-x-2">
          <div class="flex items-center bg-white rounded-lg border-2 border-gray-200 focus-within:border-blue-500 transition-colors flex-shrink-0">
            <input
              v-model.number="downPaymentPercent"
              type="number"
              min="0"
              max="49"
              step="1"
              :disabled="disabled"
              class="w-16 px-2 py-2 rounded-lg focus:outline-none text-sm font-medium text-center"
              @input="syncDownPaymentFromPercent"
            >
            <span class="px-1 text-gray-600 font-medium text-sm">%</span>
          </div>
          <div class="flex-1 flex items-center bg-white rounded-lg border-2 border-gray-200 focus-within:border-blue-500 transition-colors">
            <input
              v-model.number="downPaymentAmount"
              type="number"
              min="0"
              :max="totalAmount"
              step="any"
              :disabled="disabled"
              class="flex-1 px-3 py-2 rounded-lg focus:outline-none text-sm font-medium min-w-0"
              @input="syncDownPaymentFromAmount"
            >
            <span class="px-2 text-gray-600 font-medium text-sm">₽</span>
          </div>
        </div>
        <input
          v-model.number="downPaymentPercent"
          type="range"
          min="0"
          max="49"
          step="1"
          :disabled="disabled"
          class="mt-3 w-full h-3 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
          @input="syncDownPaymentFromPercent"
        >
        <div class="flex justify-between text-xs text-gray-600 font-medium mt-1">
          <span>0%</span><span>15%</span><span>20%</span><span>40%</span><span>49%</span>
        </div>
      </div>

      <!-- Срок договора -->
      <div class="bg-white rounded-lg p-3 border border-gray-200">
        <label class="text-sm font-semibold text-gray-800 block mb-2">
          Срок договора
        </label>
        <div class="flex items-center bg-white rounded-lg border-2 border-gray-200 focus-within:border-blue-500 transition-colors w-fit">
          <input
            v-model.number="leaseTerm"
            type="number"
            aria-label="Срок договора"
            min="1"
            max="84"
            step="any"
            :disabled="disabled"
            class="w-20 px-3 py-2 rounded-lg focus:outline-none text-sm font-medium text-center"
          >
          <span class="px-2 text-gray-600 font-medium text-sm">{{ getMonthWord(leaseTerm) }}</span>
        </div>
        <input
          v-model.number="leaseTerm"
          type="range"
          min="12"
          max="84"
          step="6"
          :disabled="disabled"
          class="mt-3 w-full h-3 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
        >
        <div class="flex justify-between text-xs text-gray-600 font-medium mt-1">
          <span>1 год</span><span>3 года</span><span>5 лет</span><span>7 лет</span>
        </div>
      </div>

      <!-- Выкупная стоимость -->
      <div class="bg-white rounded-lg p-3 border border-gray-200">
        <label class="text-sm font-semibold text-gray-800 block mb-2">
          Выкупная стоимость
        </label>
        <div class="flex space-x-2">
          <div class="flex items-center bg-white rounded-lg border-2 border-gray-200 focus-within:border-blue-500 transition-colors flex-shrink-0">
            <input
              v-model.number="buyoutPercent"
              type="number"
              min="0"
              max="50"
              step="1"
              :disabled="disabled"
              class="w-16 px-2 py-2 rounded-lg focus:outline-none text-sm font-medium text-center"
              @input="syncBuyoutFromPercent"
            >
            <span class="px-1 text-gray-600 font-medium text-sm">%</span>
          </div>
          <div class="flex-1 flex items-center bg-white rounded-lg border-2 border-gray-200 focus-within:border-blue-500 transition-colors">
            <input
              v-model.number="buyoutAmount"
              type="number"
              min="0"
              :max="totalAmount"
              step="any"
              :disabled="disabled"
              class="flex-1 px-3 py-2 rounded-lg focus:outline-none text-sm font-medium min-w-0"
              @input="syncBuyoutFromAmount"
            >
            <span class="px-2 text-gray-600 font-medium text-sm">₽</span>
          </div>
        </div>
        <input
          v-model.number="buyoutPercent"
          type="range"
          min="0"
          max="50"
          step="1"
          :disabled="disabled"
          class="mt-3 w-full h-3 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
          @input="syncBuyoutFromPercent"
        >
        <div class="flex justify-between text-xs text-gray-600 font-medium mt-1">
          <span>0%</span><span>10%</span><span>25%</span><span>50%</span>
        </div>
      </div>

      <!-- Размер ежемесячного платежа (вводится ЛК вручную) -->
      <div class="bg-white rounded-lg p-3 border border-blue-200 ring-1 ring-blue-100">
        <div class="flex justify-between items-center mb-2">
          <label class="text-sm font-semibold text-gray-800">
            Размер ежемесячного платежа
          </label>
          <span class="text-xs text-gray-500">вводится ЛК</span>
        </div>
        <div class="flex items-center bg-white rounded-lg border-2 border-gray-200 focus-within:border-blue-500 transition-colors">
          <input
            v-model.number="monthlyPayment"
            type="number"
            aria-label="Размер ежемесячного платежа"
            min="0"
            :max="monthlyPaymentMax"
            step="any"
            :disabled="disabled"
            class="flex-1 px-3 py-2 rounded-lg focus:outline-none text-sm font-medium min-w-0"
          >
          <span class="px-2 text-gray-600 font-medium text-sm">₽</span>
        </div>
        <input
          v-model.number="monthlyPayment"
          type="range"
          :min="0"
          :max="monthlyPaymentMax"
          :step="monthlyPaymentStep"
          :disabled="disabled"
          class="mt-3 w-full h-3 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
        >
        <div class="flex justify-between text-xs text-gray-600 font-medium mt-1">
          <span>0 ₽</span>
          <span>{{ formatPrice(Math.round(monthlyPaymentMax / 2)) }}</span>
          <span>{{ formatPrice(monthlyPaymentMax) }}</span>
        </div>
      </div>

      <!-- PDF -->
      <div class="bg-white rounded-lg p-3 border border-gray-200">
        <label class="text-sm font-semibold text-gray-800 block mb-2">
          PDF документ к КП
        </label>
        <div v-if="pdf?.pdf_file_name || pdf?.file_name" class="mb-2 flex items-center gap-3 text-sm">
          <a
            :href="pdfUrl"
            target="_blank"
            rel="noopener"
            class="text-blue-600 hover:text-blue-800 underline"
          >
            Посмотреть
          </a>
          <span class="text-gray-700">{{ pdf.pdf_file_name || pdf.file_name }}</span>
          <button
            type="button"
            class="text-red-600 hover:text-red-700"
            :disabled="disabled || working"
            @click="$emit('remove-pdf')"
          >
            Удалить
          </button>
        </div>
        <input
          type="file"
          accept="application/pdf"
          :disabled="disabled || working"
          class="block text-sm text-gray-700"
          @change="onPdfPicked"
        >
      </div>

      <!-- Комментарий (только для итогового) -->
      <div v-if="kind === 'final'" class="bg-white rounded-lg p-3 border border-gray-200">
        <label class="text-sm font-semibold text-gray-800 block mb-2">
          Комментарий к финальному решению
        </label>
        <textarea
          v-model="decisionComment"
          rows="3"
          :disabled="disabled"
          placeholder="Например, условия одобрения, особые требования или сопроводительная информация для клиента."
          class="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 text-sm"
        />
      </div>

      <!-- Submit -->
      <div v-if="!disabled" class="flex items-center gap-3 pt-2">
        <button
          type="submit"
          class="btn-primary"
          :disabled="!canSubmit || working || Boolean(submitDisabledReason)"
        >
          <span v-if="working">Отправляем…</span>
          <span v-else>
            {{ kind === 'preliminary' ? 'Отправить предварительный расчёт' : 'Отправить итоговый расчёт' }}
          </span>
        </button>
        <p v-if="submitDisabledReason" role="status" class="text-sm text-gray-600">
          {{ submitDisabledReason }}
        </p>
        <p v-else-if="!canSubmit" class="text-xs text-gray-500">
          Заполните все обязательные поля.
        </p>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getMonthWord } from '~/utils'
import type { LeasingProposal, ProposalParams } from '~/features/leasing/api/leasingApi'
import { createLeasingApi } from '~/features/leasing/api/leasingApi'

const props = defineProps<{
  applicationId: string
  kind: 'preliminary' | 'final'
  totalAmount: number
  initialProposal?: LeasingProposal | null
  pdf?: { pdf_file_name?: string | null; pdf_size?: number | null; pdf_uploaded_at?: string | null; file_name?: string | null } | null
  pdfUrl: string
  disabled?: boolean
  disabledReason?: string
  submitDisabledReason?: string
}>()

const emit = defineEmits<{
  (e: 'submitted'): void
  (e: 'upload-pdf', file: File, params: ProposalParams): void
  (e: 'remove-pdf'): void
  (e: 'error', message: string): void
}>()

const config = useRuntimeConfig()
const route = useRoute()
const api = createLeasingApi(config, () => route.query.leasing_company_id)
const toast = useToast()

const downPaymentPercent = ref<number>(20)
const downPaymentAmount = ref<number>(0)
const leaseTerm = ref<number>(36)
const buyoutPercent = ref<number>(0)
const buyoutAmount = ref<number>(0)
const monthlyPayment = ref<number>(0)
const decisionComment = ref<string>('')
const working = ref(false)
const dirty = ref(false)

const monthlyPaymentMax = computed(() => {
  const total = Number(props.totalAmount) || 0
  if (total <= 0) return 1_000_000
  return Math.max(50_000, Math.round(total))
})
const monthlyPaymentStep = computed(() => {
  const max = monthlyPaymentMax.value
  return Math.max(1000, Math.round(max / 1000))
})

const hydrateFromProposal = (p: LeasingProposal | null | undefined) => {
  const total = Number(props.totalAmount) || 0
  const pp = (p ?? {}) as Record<string, unknown>
  downPaymentAmount.value = Number(pp.down_payment) || 0
  downPaymentPercent.value =
    Number(pp.down_payment_percent)
    || (total > 0 ? Math.round((downPaymentAmount.value / total) * 100) : 20)
  if (downPaymentAmount.value === 0 && total > 0 && downPaymentPercent.value > 0) {
    downPaymentAmount.value = Math.round(total * downPaymentPercent.value / 100)
  }
  leaseTerm.value = Number(pp.lease_term_months) || 36
  buyoutAmount.value = Number(pp.buyout_amount) || 0
  const loanAmount = Math.max(0, total - downPaymentAmount.value)
  buyoutPercent.value = loanAmount > 0
    ? Math.round((buyoutAmount.value / loanAmount) * 100)
    : 0
  monthlyPayment.value = Number(pp.monthly_payment) || 0
}

watch(
  () => [props.initialProposal, props.totalAmount],
  () => { if (!dirty.value) hydrateFromProposal(props.initialProposal) },
  { immediate: true, deep: true },
)

const syncDownPaymentFromPercent = () => {
  const total = Number(props.totalAmount) || 0
  if (total > 0) {
    downPaymentAmount.value = Math.round(total * (Number(downPaymentPercent.value) || 0) / 100)
  }
}
const syncDownPaymentFromAmount = () => {
  const total = Number(props.totalAmount) || 0
  if (total > 0) {
    downPaymentPercent.value = Math.round((Number(downPaymentAmount.value) || 0) / total * 100)
  }
}
const syncBuyoutFromPercent = () => {
  const total = Number(props.totalAmount) || 0
  const loan = Math.max(0, total - (Number(downPaymentAmount.value) || 0))
  buyoutAmount.value = Math.round(loan * (Number(buyoutPercent.value) || 0) / 100)
}
const syncBuyoutFromAmount = () => {
  const total = Number(props.totalAmount) || 0
  const loan = Math.max(0, total - (Number(downPaymentAmount.value) || 0))
  buyoutPercent.value = loan > 0
    ? Math.round((Number(buyoutAmount.value) || 0) / loan * 100)
    : 0
}

const onPdfPicked = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (file.type !== 'application/pdf') {
    toast.error('Только PDF-файлы')
    input.value = ''
    return
  }
  emit('upload-pdf', file, buildParams())
  input.value = ''
}

const { formatPrice } = useFormatPrice()

const canSubmit = computed(() => {
  const total = Number(props.totalAmount) || 0
  if (total <= 0) return false
  if (!(Number(leaseTerm.value) > 0)) return false
  if (!(Number(monthlyPayment.value) > 0)) return false
  if (downPaymentAmount.value < 0 || downPaymentAmount.value > total) return false
  if (buyoutAmount.value < 0 || buyoutAmount.value > total) return false
  return true
})

const buildParams = (): ProposalParams => {
  const total = Number(props.totalAmount) || 0
  return {
    total_amount: total,
    down_payment: Number(downPaymentAmount.value) || 0,
    down_payment_percent: Number(downPaymentPercent.value) || 0,
    lease_term_months: Number(leaseTerm.value) || 0,
    buyout_amount: Number(buyoutAmount.value) || 0,
    monthly_payment: Number(monthlyPayment.value) || 0,
    total_cost:
      (Number(downPaymentAmount.value) || 0)
      + (Number(monthlyPayment.value) || 0) * (Number(leaseTerm.value) || 0)
      + (Number(buyoutAmount.value) || 0),
    rate: null,
    markup: null,
    total_interest: null,
    vat_refund: null,
    profit_tax_savings: null,
    total_savings: null,
  }
}

const onSubmit = async () => {
  if (props.disabled || props.submitDisabledReason || !canSubmit.value || working.value) return
  working.value = true
  try {
    await api.upsertProposal(props.applicationId, props.kind, buildParams())
    await api.submitDecision(
      props.applicationId,
      'approve',
      decisionComment.value.trim() || null,
      props.kind,
    )
    dirty.value = false
    emit('submitted')
  } catch (err: unknown) {
    const detail = (err as { data?: { detail?: string }; message?: string })
    const msg = detail?.data?.detail || detail?.message || 'Не удалось отправить расчёт'
    emit('error', msg)
  } finally {
    working.value = false
  }
}
</script>

<style scoped>
.slider {
  appearance: none;
}
.slider::-webkit-slider-thumb {
  appearance: none;
  height: 20px;
  width: 20px;
  border-radius: 50%;
  background: #ffffff;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  border: 2px solid #3b82f6;
  transition: all 0.2s ease;
}
.slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}
.slider::-moz-range-thumb {
  height: 20px;
  width: 20px;
  border-radius: 50%;
  background: #ffffff;
  cursor: pointer;
  border: 2px solid #3b82f6;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
}
.slider:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
