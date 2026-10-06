<template>
  <div class="space-y-4">
    <form class="flex items-end gap-3" novalidate @submit.prevent="search">
      <FastDealCardField class="flex-1" label="VIN" for-id="fast-deal-vin-search" :error="vinError">
        <input
          id="fast-deal-vin-search"
          v-model="vin"
          type="text"
          maxlength="32"
          autocomplete="off"
          class="input-field font-mono uppercase"
          :class="vinError ? 'border-red-500' : ''"
          :disabled="searching || busy"
          placeholder="17 символов"
        />
      </FastDealCardField>
      <button type="submit" class="btn-primary" :disabled="searching || busy || !vin.trim()">
        {{ searching ? 'Ищем…' : 'Найти' }}
      </button>
    </form>

    <template v-if="result">
      <div
        v-if="!result.found"
        class="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 space-y-3"
        role="status"
      >
        <p class="font-medium">{{ notFoundText }}</p>
        <button type="button" class="btn-outline text-sm px-3 py-1.5" :disabled="busy" @click="emit('manual', searchedVin)">
          Добавить вручную
        </button>
      </div>

      <div v-else-if="candidate" class="rounded-lg border border-gray-200 p-4 space-y-3">
        <div>
          <p class="font-medium text-gray-900">{{ candidate.title }}</p>
          <p class="text-sm text-gray-600">
            <span v-if="candidate.vin" class="font-mono">{{ candidate.vin }}</span>
            <span v-else>VIN не указан в объявлении</span>
            <span v-if="candidate.warehouseName"> · {{ candidate.warehouseName }}</span>
            <span v-if="candidate.ownerName"> · {{ candidate.ownerName }}</span>
          </p>
          <p v-if="candidate.price && !candidate.priceOnRequest" class="text-sm text-gray-900 tabular-nums">{{ formatMoney(candidate.price) }}</p>
          <p v-else-if="candidate.priceOnRequest" class="text-sm text-gray-600">Цена по запросу</p>
        </div>

        <p v-if="blockedReason" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
          {{ blockedReason }}
        </p>
        <template v-else>
          <FastDealCardField
            v-if="needsVin"
            label="VIN единицы"
            required
            for-id="fast-deal-vin-manual"
            hint="Объявление без VIN или «под заказ»: VIN вводится вручную, единица не резервируется"
            :error="manualVinError"
          >
            <input
              id="fast-deal-vin-manual"
              v-model="manualVin"
              type="text"
              maxlength="32"
              autocomplete="off"
              class="input-field font-mono uppercase"
              :class="manualVinError ? 'border-red-500' : ''"
              :disabled="busy"
            />
          </FastDealCardField>
          <FastDealCardField
            v-if="candidate.priceOnRequest"
            label="Согласованная цена, ₽"
            required
            for-id="fast-deal-vin-price"
            :error="priceError"
          >
            <input
              id="fast-deal-vin-price"
              v-model="price"
              type="text"
              inputmode="decimal"
              autocomplete="off"
              class="input-field tabular-nums"
              :class="priceError ? 'border-red-500' : ''"
              :disabled="busy"
            />
          </FastDealCardField>
          <FastDealCardError :error="otherError" />
          <div class="flex justify-end">
            <button type="button" class="btn-primary" :disabled="busy" :aria-busy="busy" @click="pick">
              {{ busy ? 'Добавляем…' : actionLabel }}
            </button>
          </div>
        </template>
      </div>
    </template>
    <p v-if="lookupError" role="alert" class="text-sm text-red-600">{{ lookupError }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { parseFastDealError } from '../api/fastDealsApi'
import {
  formatMoney,
  isPositiveMoney,
  parseMoneyInput,
  toVehicleCandidate,
  type VehicleCandidate,
} from '../composables/fastDealCardFormat'
import type { AddVehicleBody, VinLookupResult } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/

const props = withDefaults(defineProps<{
  initialVin?: string
  busy?: boolean
  error?: ActionFailure | null
  actionLabel?: string
  /** VINs of the active positions: such a unit is already in the deal. */
  existingVins?: string[]
}>(), {
  initialVin: '',
  busy: false,
  error: null,
  actionLabel: 'Добавить в сделку',
  existingVins: () => [],
})

const emit = defineEmits<{ pick: [body: AddVehicleBody]; manual: [vin: string] }>()

const ctx = useFastDealCardContext()
const vin = ref(props.initialVin)
const searching = ref(false)
const searchedVin = ref('')
const result = ref<VinLookupResult | null>(null)
const candidate = ref<VehicleCandidate | null>(null)
const lookupError = ref('')
const vinError = ref('')
const manualVin = ref('')
const manualVinError = ref('')
const price = ref('')
const priceError = ref('')

const needsVin = computed(() => !!candidate.value && candidate.value.requiresManualVin)
const notFoundText = computed(
  () => result.value?.reason || (ctx.isDD.value ? 'Не найдено на ваших складах' : 'Не найдено среди опубликованных объявлений'),
)

/** A unit that cannot be added: already in this deal, claimed elsewhere or not sellable (the server says why). */
const blockedReason = computed(() => {
  const unit = candidate.value
  if (!unit) return ''
  if (unit.vin && props.existingVins.includes(unit.vin)) return 'Эта единица уже добавлена в сделку.'
  if (!unit.selectable) {
    return unit.reason || result.value?.reason || 'Единица недоступна для регистрации сделки.'
  }
  return ''
})

// A server error about an input that is on screen is shown at that input; every other error below the form.
const otherError = computed(() => {
  const failure = props.error
  if (!failure) return null
  if (failure.field === 'vin' && needsVin.value) return null
  if (failure.field === 'price' && candidate.value?.priceOnRequest) return null
  return failure
})
const serverVinError = computed(() => (props.error?.field === 'vin' ? props.error.detail : ''))
const serverPriceError = computed(() => (props.error?.field === 'price' ? props.error.detail : ''))

async function search() {
  const value = vin.value.trim().toUpperCase()
  vinError.value = ''
  lookupError.value = ''
  if (!value) {
    vinError.value = 'Введите VIN'
    return
  }
  searching.value = true
  result.value = null
  candidate.value = null
  manualVin.value = ''
  price.value = ''
  try {
    const response = await ctx.api.vinLookup(value)
    searchedVin.value = value
    result.value = response
    candidate.value = response.found ? toVehicleCandidate(response.product) : null
    if (response.found && !candidate.value) lookupError.value = 'Сервер вернул объявление в неожиданном виде. Обновите страницу и повторите поиск.'
  } catch (error) {
    const parsed = parseFastDealError(error)
    if (parsed.status === 400) vinError.value = parsed.detail
    else lookupError.value = parsed.detail
  } finally {
    searching.value = false
  }
}

function pick() {
  const unit = candidate.value
  if (!unit) return
  manualVinError.value = serverVinError.value
  priceError.value = ''
  const body: AddVehicleBody = { vehicle_source_type: 'product', product_id: unit.id }

  if (needsVin.value) {
    const typed = manualVin.value.trim().toUpperCase()
    if (!VIN_PATTERN.test(typed)) {
      manualVinError.value = 'VIN — 17 символов: латинские буквы (кроме I, O, Q) и цифры'
      return
    }
    body.vin = typed
  }
  if (unit.priceOnRequest) {
    const parsed = parseMoneyInput(price.value)
    if (parsed === null || !isPositiveMoney(parsed)) {
      priceError.value = 'Укажите согласованную цену, например 2500000.00'
      return
    }
    body.price = parsed
  }
  manualVinError.value = ''
  emit('pick', body)
}

// Server messages reach the inputs through the same slots as local ones.
watch([serverVinError, serverPriceError], ([vinMessage, priceMessage]) => {
  if (vinMessage) manualVinError.value = vinMessage
  if (priceMessage) priceError.value = priceMessage
})
</script>
