<template>
  <section data-storefront-block="home.calculator" class="py-6 sm:py-10 lg:py-16 bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))]" id="calculator">
    <div class="max-w-7xl mx-auto px-3 sm:px-4 lg:px-6">
      <div class="text-center mb-6 lg:mb-10">
        <h2 class="text-2xl sm:text-3xl lg:text-4xl font-bold text-[color:var(--storefront-title,#1f2937)] mb-2 sm:mb-4 tracking-tight">
          Лизинговый калькулятор
        </h2>
        <p class="text-sm sm:text-base lg:text-lg text-[color:var(--storefront-text-muted,#6b7280)] max-w-xl mx-auto">
          Рассчитайте платёж и экономию по налогам
        </p>
      </div>

      <form @submit.prevent="calculate" class="grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-6">
        <div class="space-y-3 sm:space-y-4">
          <div class="calc-card">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
              <label class="calc-label">Стоимость имущества</label>
              <div class="calc-input-group">
                <input v-model.number="form.carPrice" @input="updateCarPrice" type="number" min="500000"
                  max="10000000" step="50000" class="storefront-control calc-input" placeholder="2 500 000">
                <span class="calc-suffix">₽</span>
              </div>
            </div>
            <input v-model.number="form.carPrice" @input="updateCarPrice" type="range" min="500000" max="10000000"
              step="50000" class="storefront-control calc-slider">
            <div class="flex justify-between text-xs text-[color:var(--storefront-text-muted,#9ca3af)] mt-1">
              <span>500 тыс.</span>
              <span>10 млн</span>
            </div>
          </div>

          <div class="calc-card">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
              <label class="calc-label">Первоначальный взнос</label>
              <div class="flex gap-2">
                <div class="calc-input-group calc-input-small">
                  <input v-model.number="downPaymentPercent" @input="updateDownPaymentFromPercent" type="number"
                    min="3" max="49" step="1" class="storefront-control calc-input text-center" placeholder="20">
                  <span class="calc-suffix">%</span>
                </div>
                <div class="calc-input-group">
                  <input v-model.number="form.downPayment" @input="updateDownPaymentFromAmount" type="number"
                    :min="Math.round(form.carPrice * 0.03)" :max="form.carPrice" step="10000"
                    class="storefront-control calc-input" :placeholder="formatCurrency(Math.round(form.carPrice * 0.03))">
                  <span class="calc-suffix">₽</span>
                </div>
              </div>
            </div>
            <div class="relative group">
              <input v-model.number="downPaymentPercent" @input="updateDownPaymentFromPercent" type="range" min="0"
                max="49" step="1" class="storefront-control calc-slider calc-slider-dp">
            </div>
            <div class="flex justify-between text-xs mt-1">
              <span class="text-[color:var(--storefront-text-muted,#9ca3af)] font-semibold">0%</span>
              <span class="text-[color:var(--storefront-text-muted,#9ca3af)]">49%</span>
            </div>
          </div>

          <div class="calc-card">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
              <label class="calc-label">Срок договора</label>
              <div class="calc-input-group calc-input-small">
                <input v-model.number="form.term" type="number" min="12" max="84" step="6"
                  class="storefront-control calc-input text-center" placeholder="36">
                <span class="calc-suffix">мес.</span>
              </div>
            </div>
            <input v-model.number="form.term" type="range" min="12" max="84" step="6" class="storefront-control calc-slider">
            <div class="flex justify-between text-xs text-[color:var(--storefront-text-muted,#9ca3af)] mt-1">
              <span>12 мес.</span>
              <span>84 мес.</span>
            </div>
          </div>

          <div class="calc-card">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
              <label class="calc-label">Выкупная стоимость</label>
              <div class="flex gap-2">
                <div class="calc-input-group calc-input-small">
                  <input v-model.number="buyoutPercent" @input="updateBuyoutFromPercent" type="number" min="0"
                    max="5" step="1" class="storefront-control calc-input text-center" placeholder="0">
                  <span class="calc-suffix">%</span>
                </div>
                <div class="calc-input-group">
                  <input v-model.number="form.buyoutAmount" @input="updateBuyoutFromAmount" type="number" min="0"
                    :max="form.carPrice" step="10000" class="storefront-control calc-input" placeholder="0">
                  <span class="calc-suffix">₽</span>
                </div>
              </div>
            </div>
            <input v-model.number="buyoutPercent" @input="updateBuyoutFromPercent" type="range" min="0" max="5"
              step="1" class="storefront-control calc-slider">
            <div class="flex justify-between text-xs text-[color:var(--storefront-text-muted,#9ca3af)] mt-1">
              <span>0%</span>
              <span>5%</span>
            </div>
          </div>
        </div>

        <div class="lg:sticky lg:top-4 lg:self-start space-y-3 sm:space-y-4">
          <div v-if="result" class="result-card">
            <div class="result-main">
              <div class="text-[color:var(--storefront-text-muted,#6b7280)] text-xs sm:text-sm uppercase tracking-wide mb-1">Ежемесячный платёж</div>
              <div class="text-3xl sm:text-4xl lg:text-5xl font-black text-[color:var(--storefront-text,#1f2937)] tracking-tight">
                {{ formatCurrency(result.calculation.monthlyPayment) }}
                <span class="text-xl sm:text-2xl">₽</span>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2 sm:gap-3 mt-4">
              <div class="result-item">
                <div class="result-item-label">Аванс</div>
                <div class="result-item-value">{{ downPaymentPercent }}%</div>
              </div>
              <div class="result-item">
                <div class="result-item-label">Сумма договора</div>
                <div class="result-item-value">{{ formatCurrency(result.calculation.totalCost) }} ₽</div>
              </div>
              <div class="result-item col-span-2">
                <div class="result-item-label">Страхование</div>
                <div class="result-item-value">{{ formatCurrency(Math.round(form.carPrice * 0.025)) }} ₽</div>
              </div>
            </div>
          </div>

          <div v-if="result" class="savings-card">
            <div class="flex items-center gap-2 mb-3">
              <div class="w-6 h-6 rounded-full bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] flex items-center justify-center">
                <svg class="w-3.5 h-3.5 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"></path>
                </svg>
              </div>
              <span class="text-sm font-semibold text-[color:var(--storefront-success-text,#16a34a)] uppercase tracking-wide">Ваша экономия</span>
            </div>

            <div class="space-y-2">
              <div class="savings-row">
                <div class="flex items-center gap-1.5">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)] text-sm">Возврат НДС</span>
                  <button type="button" @click="showTooltip('vat')" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#2563eb)] transition-colors">
                    <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
                    </svg>
                  </button>
                </div>
                <span class="text-[color:var(--storefront-success-text,#16a34a)] font-bold">{{ formatCurrency(result.calculation.vatRefund) }} ₽</span>
              </div>
              <div class="savings-row">
                <div class="flex items-center gap-1.5">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)] text-sm">Налог на прибыль</span>
                  <button type="button" @click="showTooltip('profit')" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#2563eb)] transition-colors">
                    <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
                    </svg>
                  </button>
                </div>
                <span class="text-[color:var(--storefront-success-text,#16a34a)] font-bold">{{ formatCurrency(result.calculation.profitTaxSavings) }} ₽</span>
              </div>
            </div>

            <div class="mt-3 pt-3 border-t border-[color:var(--storefront-success-border,#bbf7d0)]">
              <div class="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:justify-between">
                <span class="text-[color:var(--storefront-text,#374151)] font-semibold">Итого экономия</span>
                <span class="text-xl sm:text-2xl font-black text-[color:var(--storefront-success-text,#16a34a)]">{{ formatCurrency(result.calculation.totalSavings) }} ₽</span>
              </div>
            </div>
          </div>

          <div v-if="!result" class="empty-state">
            <div class="w-12 h-12 rounded-xl bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] flex items-center justify-center mb-3">
              <svg class="w-6 h-6 text-[color:var(--storefront-icon,#9ca3af)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                  d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path>
              </svg>
            </div>
            <p class="text-[color:var(--storefront-text-muted,#6b7280)] text-sm">Укажите параметры для расчёта</p>
          </div>

          <div v-if="error" class="error-card">
            <svg class="w-4 h-4 text-[color:var(--storefront-error-icon,#ef4444)] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <span class="text-sm text-[color:var(--storefront-error-text,#dc2626)]">{{ error }}</span>
          </div>

          <div class="notice-card">
            <svg class="w-4 h-4 text-[color:var(--storefront-warning-icon,#f59e0b)] flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
            </svg>
            <p class="text-xs sm:text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
              <span class="text-[color:var(--storefront-warning-text,#d97706)] font-medium">Расчёт предварительный.</span>
              Актуальный расчет предложит лизинговая компания после подачи заявки.
            </p>
          </div>

          <button v-if="result" @click="proceedWithCalculation" type="button" class="btn text-sm font-medium transition-colors duration-200 btn-primary w-full py-3 sm:py-4 rounded-xl">
            <span>Создать заявку</span>
            <svg class="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"></path>
            </svg>
          </button>
        </div>
      </form>
    </div>

    <AuthModal v-if="showAuthModal" @close="handleAuthModalClose" />

    <Teleport to="body">
      <div v-if="tooltipModal" class="fixed inset-0 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="closeTooltip">
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-2xl shadow-2xl max-w-sm w-full p-5 border border-[color:var(--storefront-border,#e5e7eb)]">
          <div class="flex justify-between items-start mb-3">
            <h3 class="text-base font-semibold text-[color:var(--storefront-title,#1f2937)]">{{ currentTooltip.title }}</h3>
            <button @click="closeTooltip" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] transition-colors p-1">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </button>
          </div>
          <p class="text-[color:var(--storefront-text-muted,#4b5563)] text-sm leading-relaxed">{{ currentTooltip.content }}</p>
          <button @click="closeTooltip" class="btn btn-primary mt-4 w-full py-2.5 text-sm font-medium rounded-lg">
            Понятно
          </button>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import AuthModal from '~/features/auth/components/AuthModal.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { getMonthWord } from '~/utils'
import type { TooltipInfo } from '~/types/domains'
import type { UUID } from '~/types/ids'

const { debounce } = useLodash()

const props = defineProps<{
  vehiclePrice?: number | null
  vehicleIds?: UUID[]
  embedded?: boolean
}>()

const emit = defineEmits(['calculation-result'])

const config = useRuntimeConfig()
const router = useRouter()
const { publicRoute } = useStorefront()
const authStore = useAuthStore()

const form = ref({
  carPrice: props.vehiclePrice || 2500000,
  downPayment: 0,
  term: 36,
  buyoutAmount: 0
})

const downPaymentPercent = ref(20)
const buyoutPercent = ref(0)
interface CalculationResult {
  calculation: {
    monthlyPayment: number
    totalCost: number
    totalInterest?: number
    vatRefund?: number
    profitTaxSavings?: number
    totalSavings?: number
    buyoutAmount?: number
    rate?: number
    markup?: number
  }
  [key: string]: unknown
}
const result = ref<CalculationResult | null>(null)
const loading = ref(false)
const error = ref('')
const showAuthModal = ref(false)
const tooltipModal = ref<boolean | null>(null)
const currentTooltip = ref<TooltipInfo>({ title: '', content: '' })

// Computed properties

// Methods
const formatCurrency = (amount: number | undefined) => {
  if (amount == null) return '0'
  return new Intl.NumberFormat('ru-RU').format(amount)
}

const showTooltip = (type: string) => {
  const tooltips: Record<string, TooltipInfo> = {
    vat: {
      title: 'Возврат НДС',
      content: 'Транспортное средство, взятое в лизинг, считается в бухгалтерской отчетности пассивом, что снижает налоговое бремя. Более того, компания имеет право на возврат НДС.'
    },
    profit: {
      title: 'Снижение налога на прибыль',
      content: 'Приобретая транспортное средство в лизинг, компания имеет право на вычет НДС, включенного в лизинговый платеж. Так как покупка оформляется как аренда с правом выкупа, организация, помимо прочего, снижает налог на прибыль, поскольку выплаты по факту являются расходом организации.'
    }
  }

  currentTooltip.value = tooltips[type] || { title: '', content: '' }
  tooltipModal.value = true
}

const closeTooltip = () => {
  tooltipModal.value = false
  currentTooltip.value = { title: '', content: '' }
}


const updateCarPrice = () => {
  form.value.downPayment = Math.round(form.value.carPrice * downPaymentPercent.value / 100)
  debouncedCalculate()
}

const updateDownPaymentFromPercent = () => {
  const percent = Number(downPaymentPercent.value) || 0

  if (percent >= 3 && percent <= 49) {
    form.value.downPayment = Math.round(form.value.carPrice * percent / 100)
    debouncedCalculate()
  }
}

const updateDownPaymentFromAmount = () => {
  const amount = Number(form.value.downPayment) || 0
  const carPrice = Number(form.value.carPrice) || 0

  if (carPrice > 0 && amount >= 0 && amount <= carPrice) {
    downPaymentPercent.value = Math.round((amount / carPrice) * 100)
    debouncedCalculate()
  }
}

const updateBuyoutFromPercent = () => {
  const percent = Number(buyoutPercent.value) || 0

  if (percent >= 0 && percent <= 5) {
    form.value.buyoutAmount = Math.round(form.value.carPrice * percent / 100)
    debouncedCalculate()
  }
}

const updateBuyoutFromAmount = () => {
  const amount = Number(form.value.buyoutAmount) || 0

  if (form.value.carPrice > 0 && amount >= 0 && amount <= form.value.carPrice) {
    buyoutPercent.value = Math.round((amount / form.value.carPrice) * 100)
    debouncedCalculate()
  }
}


const calculate = async () => {
  if (!form.value.carPrice || downPaymentPercent.value < 0) {
    return
  }

  loading.value = true
  error.value = ''

  try {
    const requestData: Record<string, unknown> = {
      total_amount: form.value.carPrice,
      down_payment: form.value.downPayment,
      down_payment_percent: downPaymentPercent.value,
      lease_term_months: form.value.term,
      buyout_amount: form.value.buyoutAmount
    }

    if (props.vehicleIds && props.vehicleIds.length > 0) {
      requestData.vehicle_ids = props.vehicleIds
    }

    const response = await $fetch<CalculationResult>('/api/v1/calculator/calculate', {
      method: 'POST',
      body: requestData,
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    result.value = response

    emit('calculation-result', {
      form: form.value,
      downPaymentPercent: downPaymentPercent.value,
      buyoutPercent: buyoutPercent.value,
      result: response
    })

  } catch (err: unknown) {
    const fetchErr = err as { data?: { error?: string } }
    error.value = fetchErr.data?.error || 'Ошибка при расчете'
  } finally {
    loading.value = false
  }
}

// Debounced version of calculate - waits 500ms after last input change
const debouncedCalculate = debounce(() => {
  calculate()
}, 500)

const proceedWithCalculation = () => {
  if (!authStore.isAuthenticated) {
    showAuthModal.value = true
    return
  }

  if (!authStore.canCreateApplications) {
    error.value = 'У вас нет прав для создания заявок'
    return
  }

  // Для авторизованных пользователей перенаправляем в каталог
  router.push(publicRoute('/special-equipment'))
}

const handleAuthModalClose = () => {
  showAuthModal.value = false
  if (authStore.isAuthenticated && authStore.canCreateApplications) {
    const calculationQuery: Record<string, string> = {
      total_amount: String(form.value.carPrice),
      down_payment: String(form.value.downPayment),
      down_payment_percent: String(downPaymentPercent.value),
      lease_term_months: String(form.value.term),
      buyout_amount: String(form.value.buyoutAmount)
    }

    if (result.value) {
      calculationQuery.calculation = JSON.stringify(result.value)
    }

    if (props.vehicleIds && props.vehicleIds.length > 0) {
      calculationQuery.vehicles = props.vehicleIds.join(',')
    }

    router.push({
      path: '/applications/create',
      query: calculationQuery
    })
  }
}

watch(() => form.value.carPrice, (newPrice) => {
  if (newPrice > 0) {
    form.value.downPayment = Math.round(newPrice * downPaymentPercent.value / 100)

    if (form.value.buyoutAmount > newPrice) {
      form.value.buyoutAmount = 0
      buyoutPercent.value = 0
    }

    debouncedCalculate()
  }
}, { immediate: true })

watch(() => form.value.downPayment, () => {
  if (form.value.buyoutAmount > form.value.carPrice) {
    form.value.buyoutAmount = Math.min(form.value.buyoutAmount, form.value.carPrice)
    if (form.value.carPrice > 0) {
      buyoutPercent.value = Math.round((form.value.buyoutAmount / form.value.carPrice) * 100)
    }
  }
})

watch(() => props.vehiclePrice, (newPrice) => {
  if (newPrice && newPrice !== form.value.carPrice) {
    form.value.carPrice = newPrice
  }
})

watch([() => form.value.term, () => form.value.buyoutAmount], () => {
  debouncedCalculate()
})

// Initial calculation
onMounted(() => {
  if (form.value.carPrice > 0) {
    updateDownPaymentFromPercent()
  }
})
</script>

<style scoped>

.calc-card {
  @apply bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-xl p-3 sm:p-4 border border-[color:var(--storefront-border,#e5e7eb)] shadow-sm;
}

.calc-label {
  @apply text-sm font-medium text-[color:var(--storefront-text,#374151)];
}

.calc-input-group {
  @apply flex items-center bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#d1d5db)] focus-within:border-[color:var(--storefront-input-focus-border,#3b82f6)] focus-within:ring-2 focus-within:ring-[color:rgb(var(--storefront-focus-rgb,59_130_246)/0.2)] transition-colors;
}

.calc-input-small {
  @apply w-20 sm:w-24;
}

.calc-input {
  @apply w-full min-w-0 px-3 py-2 bg-transparent text-[color:var(--storefront-text,#1f2937)] text-sm font-medium focus:outline-none;
}

.calc-input::placeholder {
  @apply text-[color:var(--storefront-text-muted,#9ca3af)];
}

.calc-suffix {
  @apply px-2 text-[color:var(--storefront-text-muted,#6b7280)] text-sm font-medium flex-shrink-0;
}

.calc-slider {
  @apply w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-full appearance-none cursor-pointer;
}

.calc-slider::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--storefront-primary, #3367bd);
  cursor: pointer;
  border: 2px solid var(--storefront-border,#fff);
  box-shadow: 0 2px 6px rgb(var(--storefront-shadow-rgb,51 103 189) / 0.3);
  transition: transform 0.15s;
}

.calc-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.calc-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--storefront-primary, #3367bd);
  cursor: pointer;
  border: 2px solid var(--storefront-border,#fff);
}

.calc-slider-dp {
  position: relative;
  z-index: 2;
}

.calc-slider-dp::-webkit-slider-track {
  background: linear-gradient(to right, var(--storefront-success,#16a34a) 0%, var(--storefront-success,#16a34a) 6.52%, var(--storefront-surface,#e5e7eb) 6.52%, var(--storefront-surface,#e5e7eb) 100%);
}

.calc-slider-dp::-moz-range-track {
  background: linear-gradient(to right, var(--storefront-success,#16a34a) 0%, var(--storefront-success,#16a34a) 6.52%, var(--storefront-surface,#e5e7eb) 6.52%, var(--storefront-surface,#e5e7eb) 100%);
}

.distributor-tooltip {
  @apply absolute left-0 bottom-full mb-2 px-2 py-1 bg-[color:rgb(var(--storefront-success-rgb,22_163_74)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)] text-xs rounded-md whitespace-nowrap opacity-0 invisible transition-all;
  z-index: 10;
}

.distributor-tooltip::after {
  content: '';
  @apply absolute top-full left-3 border-4 border-transparent;
  border-top-color: var(--storefront-success-border,#16a34a);
}

.group:hover .distributor-tooltip {
  @apply opacity-100 visible;
}

.result-card {
  @apply bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-xl p-4 sm:p-5 border border-[color:var(--storefront-border,#e5e7eb)] shadow-sm;
}

.result-main {
  @apply text-center pb-4 border-b border-[color:var(--storefront-border,#f3f4f6)];
}

.result-item {
  @apply bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg p-2.5 sm:p-3;
}

.result-item-label {
  @apply text-xs text-[color:var(--storefront-text-muted,#6b7280)] mb-0.5;
}

.result-item-value {
  @apply text-sm sm:text-base font-semibold text-[color:var(--storefront-text,#1f2937)];
}

.savings-card {
  @apply bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-xl p-4 border border-[color:var(--storefront-success-border,#bbf7d0)];
}

.savings-row {
  @apply flex flex-col items-start gap-1 py-1.5 sm:flex-row sm:items-center sm:justify-between;
}

.empty-state {
  @apply bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-xl p-6 text-center border border-[color:var(--storefront-border,#e5e7eb)];
}

.error-card {
  @apply flex items-center gap-2 p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg;
}

.notice-card {
  @apply flex items-start gap-2 p-3 bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fde68a)] rounded-lg;
}

input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

input[type="number"] {
  -moz-appearance: textfield;
}
</style>
