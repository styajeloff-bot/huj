<template>
  <div
    class="storefront-builder-widget rounded-xl border storefront-builder-border storefront-builder-surface p-6 shadow-sm sm:p-8"
    :style="containerStyle"
  >
    <div class="mb-8 text-center">
      <h2 class="text-2xl font-bold tracking-tight storefront-builder-text sm:text-3xl">
        {{ config.title || 'Лизинговый калькулятор' }}
      </h2>
      <p v-if="config.subtitle" class="mt-2 text-base storefront-builder-text-muted">
        {{ config.subtitle }}
      </p>
    </div>

    <div class="grid grid-cols-1 gap-8 lg:grid-cols-12">
      <!-- Sliders / Controls (col-span-7) -->
      <div class="space-y-6 lg:col-span-7">
        <!-- Cost -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium storefront-builder-text">Стоимость имущества</label>
            <div class="flex items-center rounded-lg border storefront-builder-border px-3 py-1.5 storefront-builder-focus focus-within:ring-1">
              <input
                v-model.number="cost"
                type="number"
                :min="minCost"
                :max="maxCost"
                step="50000"
                class="w-32 text-right font-semibold storefront-builder-text focus:outline-none"
              />
              <span class="ml-1 storefront-builder-text-muted">₽</span>
            </div>
          </div>
          <input
            v-model.number="cost"
            type="range"
            :min="minCost"
            :max="maxCost"
            step="50000"
            class="storefront-builder-slider h-2 w-full cursor-pointer appearance-none rounded-lg"
          />
          <div class="flex justify-between text-xs storefront-builder-text-muted">
            <span>{{ formatRubles(minCost) }}</span>
            <span>{{ formatRubles(maxCost) }}</span>
          </div>
        </div>

        <!-- Down payment -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium storefront-builder-text">Первоначальный взнос</label>
            <div class="flex items-center space-x-2">
              <div class="flex items-center rounded-lg border storefront-builder-border px-2 py-1.5 storefront-builder-focus">
                <input
                  v-model.number="downPaymentPercent"
                  type="number"
                  :min="minDownPaymentPercent"
                  :max="maxDownPaymentPercent"
                  class="w-12 text-right font-semibold storefront-builder-text focus:outline-none"
                />
                <span class="ml-0.5 storefront-builder-text-muted">%</span>
              </div>
              <div class="text-sm font-semibold storefront-builder-text-muted">
                {{ formatRubles(downPaymentAmount) }}
              </div>
            </div>
          </div>
          <input
            v-model.number="downPaymentPercent"
            type="range"
            :min="minDownPaymentPercent"
            :max="maxDownPaymentPercent"
            step="1"
            class="storefront-builder-slider h-2 w-full cursor-pointer appearance-none rounded-lg"
          />
          <div class="flex justify-between text-xs storefront-builder-text-muted">
            <span>{{ minDownPaymentPercent }}%</span>
            <span>{{ maxDownPaymentPercent }}%</span>
          </div>
        </div>

        <!-- Term -->
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium storefront-builder-text">Срок лизинга</label>
            <div class="flex items-center rounded-lg border storefront-builder-border px-3 py-1.5 storefront-builder-focus">
              <input
                v-model.number="termMonths"
                type="number"
                :min="minTermMonths"
                :max="maxTermMonths"
                step="6"
                class="w-16 text-right font-semibold storefront-builder-text focus:outline-none"
              />
              <span class="ml-1 storefront-builder-text-muted">мес.</span>
            </div>
          </div>
          <input
            v-model.number="termMonths"
            type="range"
            :min="minTermMonths"
            :max="maxTermMonths"
            step="6"
            class="storefront-builder-slider h-2 w-full cursor-pointer appearance-none rounded-lg"
          />
          <div class="flex justify-between text-xs storefront-builder-text-muted">
            <span>{{ minTermMonths }} мес.</span>
            <span>{{ maxTermMonths }} мес.</span>
          </div>
        </div>
      </div>

      <!-- Calculation Result Card (col-span-5) -->
      <div class="flex flex-col justify-between rounded-xl storefront-builder-surface-muted p-6 lg:col-span-5">
        <div class="space-y-4">
          <div>
            <span class="text-xs font-semibold uppercase tracking-wider storefront-builder-text-muted">
              Ежемесячный платёж
            </span>
            <div class="mt-1 text-3xl font-extrabold storefront-builder-primary-text sm:text-4xl">
              {{ formatRubles(monthlyPayment) }}
            </div>
            <span class="text-xs storefront-builder-text-muted">включая НДС</span>
          </div>

          <div class="border-t storefront-builder-border pt-4 space-y-2 text-sm">
            <div class="flex justify-between storefront-builder-text-muted">
              <span>Сумма финансирования:</span>
              <span class="font-medium storefront-builder-text">{{ formatRubles(financedAmount) }}</span>
            </div>
            <div class="flex justify-between storefront-builder-text-muted">
              <span>Экономия по налогам (до):</span>
              <span class="font-medium text-emerald-600">{{ formatRubles(taxSavings) }}</span>
            </div>
          </div>
        </div>

        <div v-if="config.show_apply_button ?? true" class="mt-6">
          <button
            type="button"
            class="w-full rounded-lg storefront-builder-primary py-3.5 px-4 text-center text-base font-semibold storefront-builder-primary-foreground shadow-sm transition storefront-builder-hover-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 storefront-builder-focus"
            @click="handleApply"
          >
            {{ config.cta_text || 'Подать заявку' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { widgetColorStyles } from '../utils/widgetStyles'
import { ref, computed } from 'vue'
import type { LeasingCalculatorWidgetProps, WidgetStyles } from '../types'

const props = defineProps<{
  props?: LeasingCalculatorWidgetProps
  styles?: WidgetStyles
}>()

const emit = defineEmits<{
  (e: 'apply', data: { cost: number; downPayment: number; termMonths: number; monthlyPayment: number }): void
}>()

const config = computed<LeasingCalculatorWidgetProps>(() => ({
  title: 'Лизинговый калькулятор',
  subtitle: 'Рассчитайте ежемесячный платёж и выгоду по налогам',
  default_cost: 3000000,
  min_cost: 500000,
  max_cost: 20000000,
  default_term_months: 36,
  min_term_months: 12,
  max_term_months: 60,
  default_down_payment_percent: 20,
  min_down_payment_percent: 5,
  max_down_payment_percent: 49,
  interest_rate_percent: 14.5,
  show_apply_button: true,
  cta_text: 'Подать заявку',
  cta_action: 'scroll_to_form',
  ...props.props,
}))

const minCost = computed(() => config.value.min_cost ?? 500000)
const maxCost = computed(() => config.value.max_cost ?? 20000000)
const minTermMonths = computed(() => config.value.min_term_months ?? 12)
const maxTermMonths = computed(() => config.value.max_term_months ?? 60)
const minDownPaymentPercent = computed(() => config.value.min_down_payment_percent ?? 5)
const maxDownPaymentPercent = computed(() => config.value.max_down_payment_percent ?? 49)

const cost = ref(config.value.default_cost ?? 3000000)
const downPaymentPercent = ref(config.value.default_down_payment_percent ?? 20)
const termMonths = ref(config.value.default_term_months ?? 36)

const downPaymentAmount = computed(() =>
  Math.round((cost.value * downPaymentPercent.value) / 100),
)

const financedAmount = computed(() =>
  Math.max(0, cost.value - downPaymentAmount.value),
)

const monthlyPayment = computed(() => {
  const principal = financedAmount.value
  const annualRate = (config.value.interest_rate_percent ?? 14.5) / 100
  const monthlyRate = annualRate / 12
  const n = termMonths.value
  if (n <= 0 || principal <= 0) return 0
  const factor = Math.pow(1 + monthlyRate, n)
  const pmt = (principal * (monthlyRate * factor)) / (factor - 1)
  return Math.round(pmt)
})

const taxSavings = computed(() => {
  // Estimated 40% tax benefits (VAT 20% deduction + corporate profit tax reduction 20%)
  const totalCost = monthlyPayment.value * termMonths.value + downPaymentAmount.value
  return Math.round(totalCost * 0.35)
})

const formatRubles = (val: number) => {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(val)
}

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})

const router = useRouter()

const handleApply = () => {
  emit('apply', {
    cost: cost.value,
    downPayment: downPaymentAmount.value,
    termMonths: termMonths.value,
    monthlyPayment: monthlyPayment.value,
  })

  if (config.value.cta_action === 'scroll_to_form') {
    const el = document.querySelector('#lead-form') || document.querySelector('[data-widget="lead_form"]')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
      return
    }
  }

  if (config.value.cta_link) {
    router.push(config.value.cta_link)
  }
}
</script>
