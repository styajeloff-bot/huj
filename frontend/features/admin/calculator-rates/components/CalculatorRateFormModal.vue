<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-gray-600 bg-opacity-50 px-4">
    <div class="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl">
      <div class="mb-6 flex items-center justify-between gap-4">
        <h3 class="text-lg font-medium text-gray-900">
          {{ isEditing ? 'Редактировать ставку' : 'Создать ставку' }}
        </h3>
        <button
          type="button"
          class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          title="Закрыть"
          @click="$emit('close')"
        >
          <XMarkIcon class="h-6 w-6" />
        </button>
      </div>

      <form @submit.prevent="handleSubmit">
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">
              Дата начала <span class="text-red-500">*</span>
            </label>
            <input
              v-model="form.date_from"
              type="date"
              class="input-field"
              required
            >
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">
              Дата окончания
            </label>
            <input
              v-model="form.date_to"
              type="date"
              class="input-field"
            >
          </div>

          <div v-for="field in percentFields" :key="field.key">
            <label class="mb-1 block text-sm font-medium text-gray-700">
              {{ field.label }} <span class="text-red-500">*</span>
            </label>
            <div class="relative">
              <input
                v-model.number="form[field.key]"
                type="number"
                min="0"
                max="100"
                step="0.01"
                class="input-field pr-8"
                required
              >
              <span class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-400">%</span>
            </div>
          </div>
        </div>

        <p v-if="validationError" class="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {{ validationError }}
        </p>

        <p v-if="error" class="mt-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
          {{ error }}
        </p>

        <div class="mt-6 flex justify-end gap-3">
          <button type="button" class="btn-secondary" @click="$emit('close')">
            Отмена
          </button>
          <button
            type="submit"
            class="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="submitting || Boolean(validationError) || (isEditing && !isDirty)"
          >
            <span v-if="submitting">Сохранение...</span>
            <span v-else>{{ isEditing ? 'Сохранить' : 'Создать' }}</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/24/outline'
import {
  createCalculatorRatesAdminApi,
  type CalculatorRate,
  type CalculatorRatePayload,
  type CalculatorRatePatchPayload
} from '~/features/admin/calculator-rates/api/calculatorRatesAdminApi'

type PercentKey = 'key_rate' | 'surcharge' | 'vat_rate' | 'profit_tax_rate'

const props = defineProps<{
  rate?: CalculatorRate | null
}>()

const emit = defineEmits<{
  close: []
  success: []
}>()

const config = useRuntimeConfig()
const api = createCalculatorRatesAdminApi(config)

const todayIso = () => new Date().toISOString().slice(0, 10)

const isEditing = computed(() => Boolean(props.rate))

const percentFields: Array<{ key: PercentKey; label: string }> = [
  { key: 'key_rate', label: 'Ключевая ставка' },
  { key: 'surcharge', label: 'Надбавка' },
  { key: 'vat_rate', label: 'НДС' },
  { key: 'profit_tax_rate', label: 'Налог на прибыль' }
]

const initialForm = (): CalculatorRatePayload => ({
  date_from: props.rate?.date_from ?? todayIso(),
  date_to: props.rate?.date_to ?? null,
  key_rate: props.rate?.key_rate ?? 0,
  surcharge: props.rate?.surcharge ?? 0,
  vat_rate: props.rate?.vat_rate ?? 20,
  profit_tax_rate: props.rate?.profit_tax_rate ?? 25
})

const form = ref({
  ...initialForm(),
  date_to: initialForm().date_to ?? ''
})

const error = ref('')
const submitting = ref(false)

const normalizedPayload = computed<CalculatorRatePayload>(() => ({
  date_from: form.value.date_from,
  date_to: form.value.date_to || null,
  key_rate: Number(form.value.key_rate),
  surcharge: Number(form.value.surcharge),
  vat_rate: Number(form.value.vat_rate),
  profit_tax_rate: Number(form.value.profit_tax_rate)
}))

const isDirty = computed(() => {
  const initial = initialForm()
  const current = normalizedPayload.value
  return percentFields.some(({ key }) => initial[key] !== current[key])
    || initial.date_from !== current.date_from
    || initial.date_to !== current.date_to
})

const validationError = computed(() => {
  if (!form.value.date_from) return 'Укажите дату начала периода'
  if (form.value.date_to && form.value.date_to <= form.value.date_from) {
    return 'Дата окончания должна быть позже даты начала'
  }

  for (const field of percentFields) {
    const value = Number(form.value[field.key])
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      return `${field.label}: укажите значение от 0 до 100`
    }
  }

  return ''
})

const extractError = (err: unknown): string => {
  const data = (err as { data?: { detail?: unknown; error?: string } }).data
  if (typeof data?.error === 'string') return data.error
  if (typeof data?.detail === 'string') return data.detail
  return 'Ошибка при сохранении ставки'
}

const buildPatchPayload = (): CalculatorRatePatchPayload => {
  const initial = initialForm()
  const current = normalizedPayload.value
  const patch: CalculatorRatePatchPayload = {}

  if (initial.date_from !== current.date_from) patch.date_from = current.date_from
  if (initial.date_to !== current.date_to) patch.date_to = current.date_to

  for (const field of percentFields) {
    if (initial[field.key] !== current[field.key]) {
      patch[field.key] = current[field.key]
    }
  }

  return patch
}

const handleSubmit = async () => {
  if (validationError.value) return

  error.value = ''
  submitting.value = true

  try {
    if (props.rate) {
      await api.updateRate(props.rate.id, buildPatchPayload())
    } else {
      await api.createRate(normalizedPayload.value)
    }
    emit('success')
  } catch (err: unknown) {
    error.value = extractError(err)
  } finally {
    submitting.value = false
  }
}
</script>
