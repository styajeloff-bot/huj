<template>
  <div 
    :class="cardClass"
    class="border rounded-lg p-4 cursor-pointer transition-all duration-200 hover:shadow-md"
    @click="toggleSelection"
  >
    <div class="flex items-start space-x-4">
      <!-- Selection Checkbox -->
      <div class="flex items-center pt-1">
        <input 
          :id="`company-${company.id}`"
          type="checkbox" 
          :checked="selected"
          @click.stop
          @change="$emit('toggle', company.id)"
          class="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
        >
      </div>

      <!-- Company Logo Placeholder -->
      <div class="flex-shrink-0">
        <div class="w-12 h-12 bg-gray-100 rounded-lg flex items-center justify-center">
          <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H9m0 0H5m0 0h2M7 7h10M7 11h10M7 15h10"/>
          </svg>
        </div>
      </div>

      <!-- Company Details -->
      <div class="flex-1 min-w-0">
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <!-- Company Name -->
            <h3 class="text-lg font-medium text-gray-900">
              {{ company.name }}
            </h3>
            
            <!-- Company Parameters -->
            <div class="mt-2 grid grid-cols-3 gap-4 text-sm">
              <div class="text-center">
                <div class="text-lg font-semibold text-blue-600">
                  {{ company.average_down_payment_percent }}%
                </div>
                <div class="text-xs text-gray-500">Ср. первонач. взнос</div>
              </div>
              
              <div class="text-center">
                <div class="text-lg font-semibold text-green-600">
                  {{ formatTerm(company.average_lease_term_months) }}
                </div>
                <div class="text-xs text-gray-500">Ср. срок</div>
              </div>
              
              <div class="text-center">
                <div class="text-lg font-semibold text-orange-600">
                  {{ company.average_markup_percent }}%
                </div>
                <div class="text-xs text-gray-500">Ср. удорожание</div>
              </div>
            </div>

            <!-- Additional Info -->
            <div class="mt-3 space-y-1 text-xs text-gray-600">
              <div class="flex justify-between">
                <span>Мин. первонач. взнос:</span>
                <span class="font-medium">{{ company.min_down_payment_percent || 10 }}%</span>
              </div>
              <div class="flex justify-between">
                <span>Макс. срок:</span>
                <span class="font-medium">{{ formatTerm(company.max_lease_term_months || 84) }}</span>
              </div>
            </div>

            <!-- Features/Benefits -->
            <div v-if="companyFeatures.length > 0" class="mt-3">
              <div class="flex flex-wrap gap-1">
                <span 
                  v-for="feature in companyFeatures" 
                  :key="feature"
                  class="inline-flex items-center px-2 py-1 rounded-full text-xs bg-green-100 text-green-800"
                >
                  {{ feature }}
                </span>
              </div>
            </div>
          </div>

          <!-- Selection Indicator -->
          <div v-if="selected" class="ml-4">
            <div class="w-6 h-6  rounded-full flex items-center justify-center">
              <svg class="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick Stats Preview (when selected) -->
    <div v-if="selected && estimatedPayment" class="mt-4 pt-4 border-t border-gray-200">
      <div class="bg-blue-50 rounded-lg p-3">
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-blue-800">Ориентировочный платеж:</span>
          <span class="text-lg font-bold text-blue-900">
            {{ formatPrice(estimatedPayment) }}/мес
          </span>
        </div>
        <p class="text-xs text-blue-600 mt-1">
          При стандартных условиях данной компании
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { LeasingCompanyCard } from '~/features/leasing/types'

const props = defineProps<{
  company: LeasingCompanyCard
  selected?: boolean
  applicationAmount?: number
}>()

const emit = defineEmits(['toggle'])

// Computed
const cardClass = computed(() => {
  return {
    'border-blue-500 bg-blue-50': props.selected,
    'border-gray-200 bg-white': !props.selected
  }
})

const companyFeatures = computed(() => {
  const features = []
  
  if ((props.company.min_down_payment_percent ?? 100) <= 15) {
    features.push('Низкий первонач. взнос')
  }

  if ((props.company.max_lease_term_months ?? 0) >= 72) {
    features.push('Долгий срок')
  }
  
  if (props.company.average_markup_percent <= 8) {
    features.push('Выгодные условия')
  }
  
  // Add more features based on company data
  if (props.company.special_offers && Object.keys(props.company.special_offers).length > 0) {
    features.push('Спец. предложения')
  }
  
  return features
})

const estimatedPayment = computed(() => {
  if (!props.applicationAmount || props.applicationAmount <= 0) return null
  
  // Simple estimation based on company's average parameters
  const downPayment = props.applicationAmount * (props.company.average_down_payment_percent / 100)
  const principal = props.applicationAmount - downPayment
  const annualRate = (props.company.average_markup_percent / 100) + 0.05 // Base rate estimation
  const monthlyRate = annualRate / 12
  const termMonths = props.company.average_lease_term_months
  
  if (principal <= 0) return 0
  
  const monthlyPayment = principal * 
    (monthlyRate * Math.pow(1 + monthlyRate, termMonths)) / 
    (Math.pow(1 + monthlyRate, termMonths) - 1)
  
  return Math.round(monthlyPayment)
})

// Methods
const { formatPrice } = useFormatPrice()

const formatTerm = (months: number): string => {
  if (months < 12) {
    return `${months} мес`
  } else if (months % 12 === 0) {
    const years = months / 12
    return `${years} ${years === 1 ? 'год' : years < 5 ? 'года' : 'лет'}`
  } else {
    const years = Math.floor(months / 12)
    const remainingMonths = months % 12
    return `${years}г ${remainingMonths}м`
  }
}

const toggleSelection = () => {
  emit('toggle', props.company.id)
}
</script>

<style scoped>
/* Custom styles for leasing company card */
</style>