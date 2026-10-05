<template>
  <Modal 
    :show="true" 
    @close="$emit('close')"
    title="Расчет лизингового платежа"
    size="2xl"
    :show-footer="false"
  >
    <div data-storefront-block="client.cabinet" v-if="car" class="mb-6 p-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg">
      <div class="flex items-center">
        <img 
          :src="getCarImage(car)" 
          :alt="`${car.mark_name} ${car.model_name}`"
          class="w-16 h-12 object-cover rounded mr-4"
          onerror="this.src='/images/car-placeholder.png'"
        >
        <div>
          <h4 class="font-semibold text-[color:var(--storefront-title,#111827)]">
            {{ car.mark_name }} {{ car.model_name }}
          </h4>
          <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            {{ car.year_from || car.year_start || 'Новинка' }} год, 
            {{ formatPrice(car.price_from || car.price || 0) }} ₽
          </p>
        </div>
      </div>
    </div>

    <form data-storefront-block="client.cabinet" @submit.prevent="calculate" class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="space-y-4">
        <div>
          <div class="flex items-center space-x-2 mb-3">
            <label class="text-sm font-medium text-[color:var(--storefront-label,#374151)] whitespace-nowrap">
              Стоимость автомобиля:
            </label>
            <input
              v-model.number="form.carPrice"
              type="number"
              min="500000"
              max="10000000"
              step="50000"
              class="storefront-control flex-1 rounded-md border-[color:var(--storefront-border,#d1d5db)] shadow-sm focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
              placeholder="2 500 000"
            >
            <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">₽</span>
          </div>
          <div>
            <input
              v-model.number="form.carPrice"
              type="range"
              min="500000"
              max="10000000"
              step="50000"
              class="storefront-control w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider"
            >
            <div class="flex justify-between text-xs text-[color:var(--storefront-text-muted,#6b7280)] mt-1">
              <span>500 тыс ₽</span>
              <span>10 млн ₽</span>
            </div>
          </div>
        </div>

        <div>
          <div class="flex items-center space-x-2 mb-3">
            <label class="text-sm font-medium text-[color:var(--storefront-label,#374151)] whitespace-nowrap">
              Аванс:
            </label>
            <input
              v-model.number="downPaymentPercent"
              @input="updateDownPaymentFromPercent"
              type="number"
              min="3"
              max="100"
              step="1"
              class="storefront-control w-20 rounded-md border-[color:var(--storefront-border,#d1d5db)] shadow-sm focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
              placeholder="20"
            >
            <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">%</span>
            <input
              v-model.number="form.downPayment"
              @input="updateDownPaymentFromAmount"
              type="number"
              :min="Math.round(form.carPrice * 0.03)"
              :max="form.carPrice"
              step="10000"
              class="storefront-control flex-1 rounded-md border-[color:var(--storefront-border,#d1d5db)] shadow-sm focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
              :placeholder="formatPrice(Math.round(form.carPrice * 0.03))"
            >
            <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">₽</span>
          </div>
          <div class="relative group">
            <div class="slider-container">
              <input
                v-model.number="downPaymentPercent"
                @input="updateDownPaymentFromPercent"
                type="range" :min="minDownPaymentPercent"
                max="49" step="1" class="storefront-control w-full h-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider" :style="sliderTrackStyle">
            </div>
            <div class="flex justify-between text-xs text-[color:var(--storefront-text-muted,#6b7280)] mt-1">
              <span v-if="distributorPercent > 0" class="text-[color:var(--storefront-success-text,#16a34a)] font-medium">{{ distributorPercent }}%</span>
              <span v-else>0%</span>
              <span>30%</span>
              <span>50%</span>
              <span>70%</span>
              <span>100%</span>
            </div>
          </div>
        </div>

        <div>
          <div class="flex items-center space-x-2 mb-3">
            <label class="text-sm font-medium text-[color:var(--storefront-label,#374151)] whitespace-nowrap">
              Срок лизинга:
            </label>
            <input
              v-model.number="form.term"
              type="number"
              min="12"
              max="84"
              step="6"
              class="storefront-control w-24 rounded-md border-[color:var(--storefront-border,#d1d5db)] shadow-sm focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
              placeholder="36"
            >
            <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ getMonthWord(form.term) }}</span>
          </div>
          <div>
            <input
              v-model.number="form.term"
              type="range"
              min="12"
              max="84"
              step="6"
              class="storefront-control w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider"
            >
            <div class="flex justify-between text-xs text-[color:var(--storefront-text-muted,#6b7280)] mt-1">
              <span>1 год</span>
              <span>3 года</span>
              <span>5 лет</span>
              <span>7 лет</span>
            </div>
          </div>
        </div>

        <div>
          <div class="flex items-center space-x-2 mb-3">
            <label class="text-sm font-medium text-[color:var(--storefront-label,#374151)] whitespace-nowrap">
              Выкупная стоимость:
            </label>
            <input
              v-model.number="buyoutPercent"
              @input="updateBuyoutFromPercent"
              type="number"
              min="0"
              max="50"
              step="1"
              class="storefront-control w-20 rounded-md border-[color:var(--storefront-border,#d1d5db)] shadow-sm focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
              placeholder="0"
            >
            <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">%</span>
            <input
              v-model.number="form.buyoutAmount"
              @input="updateBuyoutFromAmount"
              type="number"
              min="0"
              :max="Math.max(0, form.carPrice - form.downPayment)"
              step="10000"
              class="storefront-control flex-1 rounded-md border-[color:var(--storefront-border,#d1d5db)] shadow-sm focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
              placeholder="0"
            >
            <span class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">₽</span>
          </div>
          <div>
            <input
              v-model.number="buyoutPercent"
              @input="updateBuyoutFromPercent"
              type="range"
              min="0"
              max="50"
              step="1"
              class="storefront-control w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider"
            >
            <div class="flex justify-between text-xs text-[color:var(--storefront-text-muted,#6b7280)] mt-1">
              <span>0%</span>
              <span>10%</span>
              <span>25%</span>
              <span>50%</span>
            </div>
          </div>
        </div>
      </div>

      <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg p-4">
        <h4 class="font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Результат расчета</h4>
        <div class="mb-4 p-3 bg-[color:rgb(var(--storefront-warning-rgb,254_252_232)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fef08a)] rounded-md">
          <div class="flex">
            <svg class="w-5 h-5 text-[color:var(--storefront-warning-icon,#facc15)] mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
            </svg>
            <div class="text-sm">
              <p class="font-medium text-[color:var(--storefront-warning-text,#854d0e)]">Примерный расчет</p>
              <p class="text-[color:var(--storefront-warning-text,#a16207)]">Итоговые условия и ставки определяются лизинговой компанией индивидуально.</p>
            </div>
          </div>
        </div>

        <div v-if="result" class="space-y-3">
          <div class="text-center mb-4">
            <div class="text-3xl font-bold text-[color:var(--storefront-text-muted,#2563eb)]">
              {{ formatPrice(result.monthlyPayment) }} ₽
            </div>
            <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">ежемесячный платеж</div>
          </div>
          
          <div class="space-y-2 text-sm">
            <div class="flex justify-between">
              <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Ставка удорожания:</span>
              <span class="font-medium">{{ result.rate }}%</span>
            </div>
            <div class="flex justify-between">
              <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Коэффициент аннуитета:</span>
              <span class="font-medium">{{ ((result.annuityFactor ?? 0) * 100).toFixed(2) }}%</span>
            </div>
            <div class="flex justify-between">
              <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Сумма лизинга:</span>
              <span class="font-medium">{{ formatPrice(result.loanAmount) }} ₽</span>
            </div>
            <div class="flex justify-between">
              <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Сумма договора:</span>
              <span class="font-medium">{{ formatPrice(result.totalAmount) }} ₽</span>
            </div>
            <div class="flex justify-between">
              <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Удорожание:</span>
              <span class="font-medium">{{ formatPrice(result.totalInterest) }} ₽</span>
            </div>
            <div v-if="result.buyoutAmount > 0" class="flex justify-between">
              <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Выкупная стоимость:</span>
              <span class="font-medium">{{ formatPrice(result.buyoutAmount) }} ₽</span>
            </div>
            <div class="flex justify-between">
              <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Страхование:</span>
              <span class="font-medium">{{ formatPrice(Math.round(form.carPrice * 0.025)) }} ₽</span>
            </div>
          </div>

          <div class="mt-4 pt-4 border-t border-[color:var(--storefront-border,#d1d5db)]">
            <h5 class="font-semibold text-[color:var(--storefront-title,#111827)] mb-3 flex items-center">
              <svg class="w-5 h-5 mr-2 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              Ваша экономия
            </h5>
            <div class="space-y-2 text-sm">
              <div class="flex justify-between items-start">
                <div class="flex items-center">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Возврат НДС</span>
                  <button 
                    type="button"
                    class="storefront-action-ghost ml-1 text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)]"
                    title="Транспортное средство, взятое в лизинг, считается в бухгалтерской отчетности пассивом, что снижает налоговое бремя. Более того, компания имеет право на возврат НДС."
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                  </button>
                </div>
                <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(result.vatRefund) }} ₽</span>
              </div>
              <div class="flex justify-between items-start">
                <div class="flex items-center">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Снижение налога на прибыль</span>
                  <button 
                    type="button"
                    class="storefront-action-ghost ml-1 text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)]"
                    title="Приобретая транспортное средство в лизинг, компания имеет право на вычет НДС, включенного в лизинговый платеж. Так как покупка оформляется как аренда с правом выкупа, организация, помимо прочего, снижает налог на прибыль, поскольку выплаты по факту являются расходом организации."
                  >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                  </button>
                </div>
                <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(result.profitTaxSavings) }} ₽</span>
              </div>
              <div class="flex justify-between pt-2 border-t border-[color:var(--storefront-border,#e5e7eb)]">
                <span class="text-[color:var(--storefront-text,#111827)] font-semibold">Итого экономия:</span>
                <span class="font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(result.totalSavings) }} ₽</span>
              </div>
            </div>
          </div>

          <div class="pt-4 border-t border-[color:var(--storefront-border,#e5e7eb)]">
            <button
              @click="proceedToApplication"
              class="w-full btn-primary"
            >
              Оформить заявку с этими условиями
            </button>
          </div>
        </div>

        <div v-else class="text-center text-[color:var(--storefront-text-muted,#6b7280)] py-8">
          <svg class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z"></path>
          </svg>
          <p>Заполните параметры для расчета</p>
        </div>

        <div v-if="error" class="mt-4 p-3 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)] rounded text-sm">
          {{ error }}
        </div>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import { getMonthWord } from '~/utils'
import type { CalculatorModalResult } from '~/types/domains'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

interface CarProp {
  mark_name?: string
  model_name?: string
  year_from?: number
  year_start?: number
  price_from?: number
  price?: number
  images?: string[]
}

const props = defineProps<{
  car?: CarProp | null
}>()

const emit = defineEmits(['close'])
const config = useRuntimeConfig()

const form = ref({
  carPrice: 2500000,
  downPayment: 500000,
  term: 36,
  buyoutAmount: 0
})

const result = ref<CalculatorModalResult | null>(null)
const loading = ref(false)
const error = ref('')
const downPaymentPercent = ref(20)
const buyoutPercent = ref(0)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const { formatPrice } = useFormatPrice()

const getCarImage = (car: CarProp) => {
  if (car.images && Array.isArray(car.images) && car.images.length > 0) {
    return vehicleImageUrl(car.images[0])
  }
  
  return '/images/car-placeholder.png'
}

// These are referenced from the template slider but have no distributor in this context
const minDownPaymentPercent = computed(() => 3)
const distributorPercent = computed(() => 0)
const sliderTrackStyle = computed(() => ({}))

const updateDownPaymentFromPercent = () => {
  const percent = Number(downPaymentPercent.value) || 0
  if (percent >= 3 && percent <= 100) {
    form.value.downPayment = Math.round(form.value.carPrice * percent / 100)
  }
}

const updateDownPaymentFromAmount = () => {
  const amount = Number(form.value.downPayment) || 0
  const carPrice = Number(form.value.carPrice) || 0
  if (carPrice > 0 && amount >= 0 && amount <= carPrice) {
    downPaymentPercent.value = Math.round((amount / carPrice) * 100)
  }
}

const updateBuyoutFromPercent = () => {
  const percent = Number(buyoutPercent.value) || 0
  const loanAmount = form.value.carPrice - form.value.downPayment
  if (percent >= 0 && percent <= 50) {
    form.value.buyoutAmount = Math.round(loanAmount * percent / 100)
  }
}

const updateBuyoutFromAmount = () => {
  const amount = Number(form.value.buyoutAmount) || 0
  const loanAmount = form.value.carPrice - form.value.downPayment
  if (loanAmount > 0 && amount >= 0 && amount <= loanAmount) {
    buyoutPercent.value = Math.round((amount / loanAmount) * 100)
  }
}

const calculate = async () => {
  loading.value = true
  error.value = ''
  
  try {
    const requestBody = {
      total_amount: form.value.carPrice,
      down_payment: form.value.downPayment,
      down_payment_percent: downPaymentPercent.value,
      lease_term_months: form.value.term,
      buyout_amount: form.value.buyoutAmount
    }

    const response = await $fetch<{ calculation: Record<string, unknown> }>('/api/v1/calculator/calculate', {
      method: 'POST',
      body: requestBody,
      baseURL: config.public.apiBase
    })

    const calculation = response.calculation

    result.value = {
      monthlyPayment: calculation.monthlyPayment as number,
      monthlyPrincipalPayment: calculation.monthlyPrincipalPayment as number,
      monthlyInterestPayment: calculation.monthlyInterestPayment as number,
      loanAmount: requestBody.total_amount - requestBody.down_payment,
      totalAmount: calculation.totalCost as number,
      totalInterest: calculation.totalInterest as number,
      rate: calculation.rate as number,
      buyoutAmount: calculation.buyoutAmount as number,
      vatRefund: calculation.vatRefund as number,
      profitTaxSavings: calculation.profitTaxSavings as number,
      totalSavings: calculation.totalSavings as number
    }
  } catch (err: unknown) {
    const fetchErr = err as { data?: { error?: string } }
    error.value = fetchErr.data?.error || 'Ошибка при расчете'
  } finally {
    loading.value = false
  }
}

const debouncedCalculate = () => {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  
  loading.value = true
  
  debounceTimer = setTimeout(() => {
    if (form.value.carPrice && form.value.downPayment !== null && form.value.term) {
      calculate()
    } else {
      loading.value = false
    }
  }, 500)
}

const proceedToApplication = () => {
  emit('close')
}

onMounted(() => {
  if (props.car) {
    const price = props.car.price_from || props.car.price || 2500000
    form.value.carPrice = price
    form.value.downPayment = Math.round(price * 0.2)
  }
  nextTick(() => {
    debouncedCalculate()
  })
})

watch(() => form.value.carPrice, (newPrice) => {
  const minDownPayment = Math.round(newPrice * 0.03)
  if (form.value.downPayment < minDownPayment) {
    form.value.downPayment = minDownPayment
  }
  if (form.value.downPayment > newPrice) {
    form.value.downPayment = Math.round(newPrice * 0.2)
  }
  
  const maxBuyout = newPrice - form.value.downPayment
  if (form.value.buyoutAmount > maxBuyout) {
    form.value.buyoutAmount = 0
  }
})

watch(() => form.value.downPayment, () => {
  const maxBuyout = form.value.carPrice - form.value.downPayment
  if (form.value.buyoutAmount > maxBuyout) {
    form.value.buyoutAmount = Math.min(form.value.buyoutAmount, Math.max(0, maxBuyout))
  }
})

watch(() => [form.value.carPrice, form.value.downPayment, form.value.term, form.value.buyoutAmount], () => {
  debouncedCalculate()
}, { deep: true })

onUnmounted(() => {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
})
</script>

<style scoped>
.slider-container {
  position: relative;
  width: 100%;
}

.slider-distributor-zone {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3.09%;
  height: 8px;
  background: linear-gradient(to right, var(--storefront-success,#22c55e), var(--storefront-success,#4ade80));
  border-radius: 4px 0 0 4px;
  z-index: 1;
  pointer-events: none;
}

.distributor-tooltip {
  position: absolute;
  left: 0;
  bottom: 100%;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: var(--storefront-success,#166534);
  color: var(--storefront-text,white);
  font-size: 12px;
  border-radius: 6px;
  white-space: nowrap;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s, visibility 0.2s;
  z-index: 10;
}

.distributor-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 12px;
  border: 5px solid transparent;
  border-top-color: var(--storefront-success-border,#166534);
}

.group:hover .distributor-tooltip,
.slider-distributor-zone:hover + input + .distributor-tooltip {
  opacity: 1;
  visibility: visible;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  height: 20px;
  width: 20px;
  border-radius: 50%;
  background: var(--storefront-primary,#3b82f6);
  cursor: pointer;
  border: 2px solid var(--storefront-border,#ffffff);
  box-shadow: 0 2px 4px rgb(var(--storefront-shadow-rgb,0 0 0) / 0.1);
  position: relative;
  z-index: 2;
}

.slider::-webkit-slider-thumb:hover {
  background: var(--storefront-primary-hover,#2563eb);
  transform: scale(1.1);
}

.slider::-moz-range-thumb {
  height: 20px;
  width: 20px;
  border-radius: 50%;
  background: var(--storefront-primary,#3b82f6);
  cursor: pointer;
  border: 2px solid var(--storefront-border,#ffffff);
  box-shadow: 0 2px 4px rgb(var(--storefront-shadow-rgb,0 0 0) / 0.1);
  position: relative;
  z-index: 2;
}

.slider::-moz-range-thumb:hover {
  background: var(--storefront-primary-hover,#2563eb);
  transform: scale(1.1);
}

.slider::-webkit-slider-track {
  height: 8px;
  background: linear-gradient(to right, var(--storefront-success,#22c55e) 0%, var(--storefront-success,#22c55e) 3.09%, var(--storefront-surface,#e5e7eb) 3.09%, var(--storefront-surface,#e5e7eb) 100%);
  border-radius: 4px;
}

.slider::-moz-range-track {
  height: 8px;
  background: linear-gradient(to right, var(--storefront-success,#22c55e) 0%, var(--storefront-success,#22c55e) 3.09%, var(--storefront-surface,#e5e7eb) 3.09%, var(--storefront-surface,#e5e7eb) 100%);
  border-radius: 4px;
}

.slider::-moz-range-progress {
  height: 8px;
  background: var(--storefront-primary,#3b82f6);
  border-radius: 4px;
}
</style>
