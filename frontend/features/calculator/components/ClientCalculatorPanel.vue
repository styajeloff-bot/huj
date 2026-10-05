<template>
  <div data-storefront-block="client.cabinet">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">
        Калькулятор лизинга
      </h2>
      <div class="flex space-x-3">
        <button @click="saveCalculation" v-if="calculation.monthly_payment" class="btn-secondary">
          Сохранить расчет
        </button>
        <button @click="createApplicationFromCalculation" v-if="calculation.monthly_payment" class="btn-primary">
          Подать заявку
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <!-- Параметры расчета -->
      <div class="space-y-6">
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
          <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Параметры лизинга</h3>
          
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Стоимость автомобиля
              </label>
              <input
                v-model.number="params.vehicle_price"
                type="number"
                class="storefront-control input-field"
                placeholder="Введите стоимость автомобиля"
                @input="calculate"
              >
            </div>

            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Первоначальный взнос ({{ params.down_payment_percent }}%)
              </label>
              <div class="space-y-2">
                <input
                  v-model.number="params.down_payment"
                  type="number"
                  class="storefront-control input-field"
                  placeholder="Сумма первоначального взноса"
                  @input="updateDownPaymentPercent"
                >
                <div class="relative group">
                  <div class="slider-container">
                    <input
                      v-model.number="params.down_payment_percent"
                      type="range"
                      min="0"
                      max="49"
                      class="storefront-control w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider"
                      @input="updateDownPayment"
                    >
                  </div>
                </div>
                <div class="flex justify-between text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  <span class="text-[color:var(--storefront-success-text,#16a34a)] font-bold">0%</span>
                  <span>15%</span>
                  <span>30%</span>
                  <span>49%</span>
                </div>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Срок лизинга ({{ params.lease_term_months }} мес.)
              </label>
              <div class="space-y-2">
                <input
                  v-model.number="params.lease_term_months"
                  type="range"
                  min="12"
                  max="84"
                  step="12"
                  class="storefront-control w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider"
                  @input="calculate"
                >
                <div class="flex justify-between text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  <span>1 год</span>
                  <span>3 года</span>
                  <span>5 лет</span>
                  <span>7 лет</span>
                </div>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Остаточная стоимость ({{ params.residual_value_percent }}%)
              </label>
              <div class="space-y-2">
                <input
                  v-model.number="params.residual_value"
                  type="number"
                  class="storefront-control input-field"
                  placeholder="Остаточная стоимость"
                  @input="updateResidualPercent"
                >
                <input
                  v-model.number="params.residual_value_percent"
                  type="range"
                  min="10"
                  max="50"
                  class="storefront-control w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider"
                  @input="updateResidualValue"
                >
                <div class="flex justify-between text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  <span>10%</span>
                  <span>30%</span>
                  <span>50%</span>
                </div>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Процентная ставка ({{ params.interest_rate }}% годовых)
              </label>
              <input
                v-model.number="params.interest_rate"
                type="range"
                min="1"
                max="20"
                step="0.1"
                class="storefront-control w-full h-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider"
                @input="calculate"
              >
              <div class="flex justify-between text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                <span>1%</span>
                <span>10%</span>
                <span>20%</span>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Тип лизингополучателя
              </label>
              <select v-model="params.lessee_type" class="storefront-control select-field" @change="calculate">
                <option value="individual">Физическое лицо</option>
                <option value="legal">Юридическое лицо</option>
              </select>
            </div>

            <div v-if="params.lessee_type === 'legal'">
              <label class="flex items-center">
                <input
                  v-model="params.include_vat"
                  type="checkbox"
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                  @change="calculate"
                >
                <span class="ml-2 text-sm text-[color:var(--storefront-text,#374151)]">Включить НДС</span>
              </label>
            </div>
          </div>
        </div>

        <!-- Дополнительные параметры -->
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
          <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Дополнительные услуги</h3>
          
          <div class="space-y-4">
            <div>
              <label class="flex items-center">
                <input
                  v-model="params.include_insurance"
                  type="checkbox"
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                  @change="calculate"
                >
                <span class="ml-2 text-sm text-[color:var(--storefront-text,#374151)]">Страхование КАСКО</span>
              </label>
              <div v-if="params.include_insurance" class="mt-2 ml-6">
                <input
                  v-model.number="params.insurance_cost"
                  type="number"
                  class="storefront-control input-field"
                  placeholder="Стоимость страхования в год"
                  @input="calculate"
                >
              </div>
            </div>

            <div>
              <label class="flex items-center">
                <input
                  v-model="params.include_maintenance"
                  type="checkbox"
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                  @change="calculate"
                >
                <span class="ml-2 text-sm text-[color:var(--storefront-text,#374151)]">Техническое обслуживание</span>
              </label>
              <div v-if="params.include_maintenance" class="mt-2 ml-6">
                <input
                  v-model.number="params.maintenance_cost"
                  type="number"
                  class="storefront-control input-field"
                  placeholder="Стоимость ТО в год"
                  @input="calculate"
                >
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Другие расходы
              </label>
              <input
                v-model.number="params.other_costs"
                type="number"
                class="storefront-control input-field"
                placeholder="Дополнительные расходы"
                @input="calculate"
              >
            </div>
          </div>
        </div>
      </div>

      <!-- Результаты расчета -->
      <div class="space-y-6">
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
          <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Результаты расчета</h3>
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

          <div v-if="calculation.monthly_payment" class="space-y-4">
            <!-- Основные показатели -->
            <div class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4 rounded-lg">
              <div class="text-center">
                <div class="text-3xl font-bold text-[color:var(--storefront-text-muted,#2563eb)]">
                  {{ formatMoney(calculation.monthly_payment) }}
                </div>
                <div class="text-sm text-[color:var(--storefront-text,#1e40af)]">Ежемесячный платеж</div>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3 rounded-lg">
                <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Сумма лизинга</div>
                <div class="text-lg font-semibold">{{ formatMoney(calculation.lease_amount) }}</div>
              </div>
              <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3 rounded-lg">
                <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Сумма договора</div>
                <div class="text-lg font-semibold">{{ formatMoney(calculation.total_cost) }}</div>
              </div>
              <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3 rounded-lg">
                <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Удорожание</div>
                <div class="text-lg font-semibold">{{ formatMoney(calculation.overpayment) }}</div>
              </div>
              <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3 rounded-lg">
                <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Выкупная стоимость</div>
                <div class="text-lg font-semibold">{{ formatMoney(calculation.buyout_price) }}</div>
              </div>
              <div class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3 rounded-lg">
                <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Страхование</div>
                <div class="text-lg font-semibold">{{ formatMoney(Math.round(params.vehicle_price * 0.025)) }}</div>
              </div>
            </div>

            <!-- Детализация -->
            <div class="border-t pt-4">
              <h4 class="font-medium text-[color:var(--storefront-title,#111827)] mb-3">Детализация расчета</h4>
              <div class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Стоимость автомобиля:</span>
                  <span>{{ formatMoney(params.vehicle_price) }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Первоначальный взнос:</span>
                  <span>{{ formatMoney(params.down_payment) }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Остаточная стоимость:</span>
                  <span>{{ formatMoney(params.residual_value) }}</span>
                </div>
                <div v-if="params.include_insurance" class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Страхование (в год):</span>
                  <span>{{ formatMoney(params.insurance_cost) }}</span>
                </div>
                <div v-if="params.include_maintenance" class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">ТО (в год):</span>
                  <span>{{ formatMoney(params.maintenance_cost) }}</span>
                </div>
                <div v-if="params.include_vat" class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">НДС:</span>
                  <span>{{ formatMoney(calculation.vat_amount) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="text-center py-8 text-[color:var(--storefront-text-muted,#6b7280)]">
            <svg class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)] mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 7h6m0 0l-3-3m3 3l-3 3m6 2a9 9 0 11-18 0 9 9 0 0118 0z">
              </path>
            </svg>
            <p>Введите параметры для расчета</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Сохраненные расчеты -->
    <div v-if="savedCalculations.length > 0" class="mt-8">
      <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Сохраненные расчеты</h3>
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
            <thead class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                  Название
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                  Стоимость авто
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                  Ежемесячный платеж
                </th>
                <th class="px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                  Дата сохранения
                </th>
                <th class="px-6 py-3 text-right text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider">
                  Действия
                </th>
              </tr>
            </thead>
            <tbody class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
              <tr v-for="saved in savedCalculations" :key="saved.id" class="hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
                <td class="px-6 py-4 whitespace-nowrap">
                  <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">{{ saved.name }}</div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-[color:var(--storefront-text,#111827)]">
                  {{ formatMoney(saved.vehicle_price) }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-[color:var(--storefront-text,#111827)]">
                  {{ formatMoney(saved.monthly_payment) }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  {{ formatDate(saved.created_at) }}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    @click="loadCalculation(saved)"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)] mr-3"
                  >
                    Загрузить
                  </button>
                  <button
                    @click="deleteCalculation(saved.id)"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#7f1d1d)]"
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { ClientCalculation, PaymentScheduleRow } from '~/types/domains'
import type { SavedCalculation } from '~/features/calculator/api/calculatorApi'
import type { UUID } from '~/types/ids'

const config = useRuntimeConfig()
const { showToast } = useToast()
const logger = useLogger()

const params = ref({
  vehicle_price: 2000000,
  down_payment: 400000,
  down_payment_percent: 20,
  lease_term_months: 36,
  residual_value: 800000,
  residual_value_percent: 40,
  interest_rate: 8.5,
  lessee_type: 'individual',
  include_vat: false,
  include_insurance: false,
  insurance_cost: 100000,
  include_maintenance: false,
  maintenance_cost: 50000,
  other_costs: 0
})

const calculation = ref<Partial<ClientCalculation>>({})
const paymentSchedule = ref<PaymentScheduleRow[]>([])
const savedCalculations = ref<SavedCalculation[]>([])

// Вычисляемые свойства для синхронизации полей
const updateDownPayment = () => {
  params.value.down_payment = Math.round(params.value.vehicle_price * params.value.down_payment_percent / 100)
  calculate()
}

const updateDownPaymentPercent = () => {
  if (params.value.vehicle_price > 0) {
    params.value.down_payment_percent = Math.round(params.value.down_payment / params.value.vehicle_price * 100)
  }
  calculate()
}

const updateResidualValue = () => {
  params.value.residual_value = Math.round(params.value.vehicle_price * params.value.residual_value_percent / 100)
  calculate()
}

const updateResidualPercent = () => {
  if (params.value.vehicle_price > 0) {
    params.value.residual_value_percent = Math.round(params.value.residual_value / params.value.vehicle_price * 100)
  }
  calculate()
}

const calculate = () => {
  if (!params.value.vehicle_price || params.value.vehicle_price <= 0) {
    calculation.value = {}
    return
  }

  const vehiclePrice = params.value.vehicle_price
  const downPayment = params.value.down_payment
  const residualValue = params.value.residual_value
  const months = params.value.lease_term_months
  const rate = params.value.interest_rate / 100 / 12

  // Сумма лизинга (сумма к финансированию)
  const leaseAmount = vehiclePrice - downPayment - residualValue

  // Дополнительные расходы в месяц
  let additionalCosts = 0
  if (params.value.include_insurance) {
    additionalCosts += (params.value.insurance_cost || 0) / 12
  }
  if (params.value.include_maintenance) {
    additionalCosts += (params.value.maintenance_cost || 0) / 12
  }
  additionalCosts += (params.value.other_costs || 0) / 12

  // Расчет ежемесячного платежа (аннуитет)
  const monthlyPayment = leaseAmount * (rate * Math.pow(1 + rate, months)) / (Math.pow(1 + rate, months) - 1) + additionalCosts

  // Общая стоимость
  const totalCost = monthlyPayment * months + downPayment + residualValue

  // Переплата
  const overpayment = totalCost - vehiclePrice

  // НДС (если применимо)
  const vatAmount = params.value.include_vat ? monthlyPayment * 0.2 : 0

  calculation.value = {
    lease_amount: leaseAmount,
    monthly_payment: monthlyPayment + vatAmount,
    total_cost: totalCost,
    overpayment: overpayment,
    buyout_price: residualValue,
    vat_amount: vatAmount * months
  }

  // Генерируем график платежей
  generatePaymentSchedule()
}

const generatePaymentSchedule = () => {
  const schedule: Array<{ month: number; payment: number; principal: number; interest: number; balance: number }> = []
  let balance = calculation.value.lease_amount || 0
  const monthlyPayment = calculation.value.monthly_payment || 0
  const rate = params.value.interest_rate / 100 / 12

  for (let month = 1; month <= params.value.lease_term_months; month++) {
    const interestPayment = balance * rate
    const principalPayment = monthlyPayment - interestPayment
    balance -= principalPayment

    schedule.push({
      month,
      payment: monthlyPayment,
      principal: principalPayment,
      interest: interestPayment,
      balance: Math.max(0, balance)
    })
  }

  paymentSchedule.value = schedule
}

const saveCalculation = async () => {
  const name = prompt('Введите название для сохранения расчета:')
  if (!name) return

  try {
    const response = await $fetch<{ calculation: SavedCalculation }>('/api/v1/client/calculations', {
      method: 'POST',
      body: {
        name,
        params: params.value,
        calculation: calculation.value
      },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    savedCalculations.value.push(response.calculation)
    showToast.success('Расчет сохранен')
  } catch (err: unknown) {
    logger.error('Error saving calculation', err)
    const fetchErr = err as { data?: { error?: string } }
    showToast.error(fetchErr.data?.error || 'Ошибка при сохранении расчета')
  }
}

const loadCalculation = (saved: SavedCalculation) => {
  Object.assign(params.value, saved.params)
  calculation.value = saved.calculation as unknown as ClientCalculation
  generatePaymentSchedule()
  showToast.success('Расчет загружен')
}

const deleteCalculation = async (id: UUID) => {
  if (!confirm('Удалить сохраненный расчет?')) return

  try {
    await $fetch(`/api/v1/client/calculations/${id}`, {
      method: 'DELETE',
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    savedCalculations.value = savedCalculations.value.filter(c => c.id !== id)
    showToast.success('Расчет удален')
  } catch (err) {
    logger.error('Error deleting calculation', err)
    showToast.error('Ошибка при удалении расчета')
  }
}

const createApplicationFromCalculation = () => {
  navigateTo('/applications/create')
}

const fetchSavedCalculations = async () => {
  try {
    const response = await $fetch<{ calculations: SavedCalculation[] }>('/api/v1/client/calculations', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    savedCalculations.value = response.calculations
  } catch (err: unknown) {
    logger.error('Error fetching saved calculations', err)
  }
}

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

const formatMoney = (amount: string | number | undefined) => {
  if (!amount) return '0 ₽'
  return formatSharedPrice(amount)
}

const formatDate = (dateString: string | null | undefined) => {
  if (!dateString) return '-'
  return formatSharedDate(dateString)
}

// Инициализация
onMounted(() => {
  calculate()
  fetchSavedCalculations()
})

// Автоматический пересчет при изменении стоимости автомобиля
watch(() => params.value.vehicle_price, () => {
  updateDownPayment()
  updateResidualValue()
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
  width: 6.38%;
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

.group:hover .distributor-tooltip {
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
  background: linear-gradient(to right, var(--storefront-success,#22c55e) 0%, var(--storefront-success,#22c55e) 6.38%, var(--storefront-surface,#e5e7eb) 6.38%, var(--storefront-surface,#e5e7eb) 100%);
  border-radius: 4px;
}

.slider::-moz-range-track {
  height: 8px;
  background: linear-gradient(to right, var(--storefront-success,#22c55e) 0%, var(--storefront-success,#22c55e) 6.38%, var(--storefront-surface,#e5e7eb) 6.38%, var(--storefront-surface,#e5e7eb) 100%);
  border-radius: 4px;
}
</style>
