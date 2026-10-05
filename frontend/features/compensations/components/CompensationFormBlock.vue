<template>
  <div data-storefront-block="client.cabinet" class="border-t pt-4 mt-4">
    <div class="flex items-center justify-between mb-4">
      <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">Компенсации</h4>
      <button
        v-if="compensations.length < 4"
        type="button"
        class="storefront-action-ghost text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
        @click="addCompensation"
      >
        + Добавить компенсацию
      </button>
    </div>

    <div v-if="compensations.length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] italic mb-4">
      Компенсации не добавлены
    </div>

    <div
      v-for="(comp, index) in compensations"
      :key="index"
      class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg p-4 mb-4"
    >
      <div class="flex items-center justify-between mb-3">
        <span class="text-sm font-medium text-[color:var(--storefront-text,#374151)]">Компенсация {{ Number(index) + 1 }}</span>
        <button
          type="button"
          class="storefront-action-ghost text-xs text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)]"
          @click="removeCompensation(index)"
        >
          Удалить
        </button>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Кто платит</label>
          <select v-model="comp.payer" class="storefront-control select-field text-sm">
            <option v-for="p in payerOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Кому платит</label>
          <select v-model="comp.recipient" class="storefront-control select-field text-sm">
            <option v-for="r in recipientOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">База расчета</label>
          <select
            v-model="comp.calculation_base"
            class="storefront-control select-field text-sm"
            @change="updateBaseAmount(index)"
          >
            <option v-for="b in calculationBaseOptions" :key="b.value" :value="b.value">{{ b.label }}</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Сумма базы расчета</label>
          <input
            :value="formatRub(comp.calculation_base_amount)"
            type="text"
            class="storefront-control input-field text-sm bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
            readonly
          />
        </div>

        <div class="sm:col-span-2 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Тип значения</label>
            <select v-model="comp.value_type" class="storefront-control select-field text-sm" @change="onValueTypeChange(index)">
              <option value="percent">Процент</option>
              <option value="sum">Сумма</option>
            </select>
          </div>

          <div>
            <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Значение</label>
            <input
              v-model.number="comp.value"
              type="number"
              min="0"
              step="any"
              class="storefront-control input-field text-sm"
              @input="recalcAmount(index)"
            />
          </div>

          <template v-if="comp.value_type === 'percent'">
            <div>
              <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Мин. сумма</label>
              <input
                v-model.number="comp.min_amount"
                type="number"
                min="0"
                class="storefront-control input-field text-sm"
                @input="recalcAmount(index)"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Макс. сумма</label>
              <input
                v-model.number="comp.max_amount"
                type="number"
                min="0"
                class="storefront-control input-field text-sm"
                @input="recalcAmount(index)"
              />
            </div>
          </template>

          <template v-if="comp.value_type === 'sum'">
            <div>
              <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Мин. %</label>
              <input
                v-model.number="comp.min_percent"
                type="number"
                min="0"
                step="any"
                class="storefront-control input-field text-sm"
                @input="recalcAmount(index)"
              />
            </div>
            <div>
              <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Макс. %</label>
              <input
                v-model.number="comp.max_percent"
                type="number"
                min="0"
                step="any"
                class="storefront-control input-field text-sm"
                @input="recalcAmount(index)"
              />
            </div>
          </template>
        </div>
      </div>

      <div
        class="mt-3 grid grid-cols-1 gap-3"
        :class="isPeriodSchedule(comp.payment_schedule_type) ? 'sm:grid-cols-4' : 'sm:grid-cols-[2fr_1fr_1fr]'"
      >
        <div>
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Тип графика</label>
          <select
            v-model="comp.payment_schedule_type"
            class="storefront-control select-field text-sm"
            @change="onScheduleTypeChange(index)"
          >
            <option v-for="s in scheduleTypeOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>
        <div v-if="isPeriodSchedule(comp.payment_schedule_type)">
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Период</label>
          <select
            v-model="comp.payment_schedule_period"
            class="storefront-control select-field text-sm"
            @change="onSchedulePeriodChange(index)"
          >
            <option v-for="p in schedulePeriodOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">
            {{ scheduleValueLabel(comp) }}
          </label>
          <input
            v-model="comp.payment_schedule_value"
            :type="comp.payment_schedule_type === 'fixed_date' ? 'date' : 'number'"
            class="storefront-control input-field text-sm"
            :min="scheduleInputMin(comp)"
            :max="scheduleInputMax(comp)"
            step="1"
            required
            @input="normalizeScheduleValue(index)"
            @blur="normalizeScheduleValue(index)"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Расчетный срок</label>
          <input
            :value="computeDueDate(comp)"
            type="text"
            class="storefront-control input-field text-sm bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
            readonly
          />
        </div>
      </div>

      <div class="mt-3">
        <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Комментарий</label>
        <input
          v-model="comp.comment"
          type="text"
          class="storefront-control input-field text-sm"
          placeholder="Необязательно"
        />
      </div>

      <div class="mt-3 flex items-center justify-between">
        <span class="text-sm font-medium text-[color:var(--storefront-text,#374151)]">
          Итого: <span class="text-[color:var(--storefront-text,#1d4ed8)] font-semibold">{{ formatCompensationTotal(comp) }}</span>
        </span>
      </div>
    </div>

    <div v-if="compensations.length > 0" class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)] rounded-lg p-3">
      <div class="text-sm space-y-1">
        <div class="flex justify-between">
          <span class="text-[color:var(--storefront-text,#374151)]">Компенсации:</span>
          <span class="font-medium">{{ totalCompensationsLabel }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  CompensationCalculationBase,
  CompensationCreateItem,
  CompensationPayer,
  CompensationRecipient,
  CompensationSchedulePeriod
} from '../api/compensationApi'

type EditableCompensation = CompensationCreateItem & {
  calculation_base_amount: number
  amount: number
}

const props = defineProps<{
  modelValue: EditableCompensation[]
  baseAmounts: Partial<Record<CompensationCalculationBase, number>>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: EditableCompensation[]]
}>()

const compensations = computed({
  get: () => props.modelValue,
  set: (val: EditableCompensation[]) => emit('update:modelValue', val)
})

const payerOptions: Array<{ value: CompensationPayer; label: string }> = [
  { value: 'distributor', label: 'Дистрибьютор' },
  { value: 'dealer', label: 'Дилер' },
  { value: 'carcraft', label: 'CarCraft' },
  { value: 'minpromtorg', label: 'Минпромторг' },
  { value: 'client', label: 'Клиент' }
]

const recipientOptions: Array<{ value: CompensationRecipient; label: string }> = [
  { value: 'leasing_company', label: 'Лизинговая компания' },
  { value: 'dealer', label: 'Дилер' },
  { value: 'carcraft', label: 'CarCraft' },
  { value: 'client', label: 'Клиент' }
]

const calculationBaseOptions: Array<{ value: CompensationCalculationBase; label: string }> = [
  { value: 'base_price', label: 'РРЦ' },
  { value: 'special_price', label: 'Специальная цена' },
  { value: 'application_price', label: 'Цена в заявке' },
  { value: 'down_payment', label: 'Первый взнос' },
  { value: 'support_amount', label: 'Сумма поддержки' }
]

const scheduleTypeOptions = [
  { value: 'fixed_date', label: 'Фиксированная дата' },
  { value: 'days_count', label: 'Через N дней' },
  { value: 'reporting_period', label: 'Раз в период' },
  { value: 'weekly', label: 'Раз в неделю' },
  { value: 'quarterly', label: 'Раз в квартал' }
] as const

const schedulePeriodOptions: Array<{ value: CompensationSchedulePeriod; label: string }> = [
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'two_months', label: 'Два месяца' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'half_year', label: 'Полугодие' },
  { value: 'year', label: 'Год' }
]

const isPeriodSchedule = (type: EditableCompensation['payment_schedule_type']): boolean =>
  type === 'reporting_period'

const scheduleValueLabel = (comp: EditableCompensation): string => {
  const type = comp.payment_schedule_type
  if (isPeriodSchedule(type) && schedulePeriod(comp) === 'week') {
    return 'День недели (1-7)'
  }

  const labels: Record<string, string> = {
    fixed_date: 'Дата',
    days_count: 'Кол-во дней',
    reporting_period: 'Расчетный день',
    weekly: 'День недели (1-7)',
    quarterly: 'День в квартале'
  }
  return labels[type || ''] || 'Значение'
}

const formatRub = (n: number | null | undefined): string => {
  if (n == null || Number.isNaN(Number(n))) return '0'
  return new Intl.NumberFormat('ru-RU').format(Math.round(Number(n)))
}

const formatPercent = (n: number | null | undefined): string => {
  const value = Number(n)
  if (Number.isNaN(value)) return '0'
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 4
  }).format(value)
}

const calculationBaseLabel = (base: CompensationCalculationBase): string => (
  calculationBaseOptions.find((option) => option.value === base)?.label || 'базы'
)

const totalCompensations = computed(() =>
  compensations.value.reduce((sum: number, c: EditableCompensation) => sum + (Number(c.amount) || 0), 0)
)

const totalCompensationsLabel = computed(() => {
  const sumItems = compensations.value.filter((c) => c.value_type === 'sum')
  const percentItems = compensations.value.filter((c) => c.value_type === 'percent')
  const parts: string[] = []
  const sumTotal = sumItems.reduce((sum, c) => sum + (Number(c.amount || c.value) || 0), 0)

  if (sumTotal > 0) parts.push(`${formatRub(sumTotal)} р.`)
  if (percentItems.length) {
    parts.push(percentItems.map((c) => `${formatPercent(c.value)}%`).join(' + '))
  }

  return parts.join(' + ') || '0 р.'
})

const formatCompensationTotal = (comp: EditableCompensation): string => {
  if (comp.value_type === 'percent') {
    const percentText = `${formatPercent(comp.value)}% от ${calculationBaseLabel(comp.calculation_base).toLowerCase()}`
    const amount = Number(comp.amount) || 0
    const hasKnownBase = (Number(comp.calculation_base_amount) || 0) > 0
    return hasKnownBase && amount > 0
      ? `${percentText} (≈ ${formatRub(amount)} р.)`
      : percentText
  }

  return `${formatRub(comp.amount || comp.value)} р.`
}

const emptyCompensation = (): EditableCompensation => ({
  payer: 'distributor',
  recipient: 'leasing_company',
  calculation_base: 'down_payment',
  calculation_base_amount: props.baseAmounts.down_payment || 0,
  value_type: 'percent',
  value: 0,
  min_amount: null,
  max_amount: null,
  min_percent: null,
  max_percent: null,
  amount: 0,
  payment_schedule_type: 'days_count',
  payment_schedule_period: null,
  payment_schedule_value: '30',
  comment: ''
})

const todayIso = (): string => {
  const today = new Date()
  const local = new Date(today.getTime() - today.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

const schedulePeriod = (comp: EditableCompensation): CompensationSchedulePeriod => {
  if (comp.payment_schedule_period) return comp.payment_schedule_period
  return 'month'
}

const schedulePeriodMaxDay = (period: CompensationSchedulePeriod): number => ({
  week: 7,
  month: 31,
  two_months: 62,
  quarter: 92,
  half_year: 184,
  year: 366
})[period]

const scheduleBounds = (comp: EditableCompensation): { min?: number; max?: number } => {
  const type = comp.payment_schedule_type
  if (type === 'days_count') return { min: 1 }
  if (isPeriodSchedule(type)) return { min: 1, max: schedulePeriodMaxDay(schedulePeriod(comp)) }
  if (type === 'weekly') return { min: 1, max: 7 }
  if (type === 'quarterly') return { min: 1, max: 92 }
  return {}
}

const scheduleInputMin = (comp: EditableCompensation): string | undefined => {
  if (comp.payment_schedule_type === 'fixed_date') return todayIso()
  const min = scheduleBounds(comp).min
  return min == null ? undefined : String(min)
}

const scheduleInputMax = (comp: EditableCompensation): string | undefined => {
  const max = scheduleBounds(comp).max
  return max == null ? undefined : String(max)
}

const defaultScheduleValue = (comp: EditableCompensation): string => {
  const type = comp.payment_schedule_type
  if (type === 'fixed_date') return todayIso()
  const min = scheduleBounds(comp).min
  return String(min || 1)
}

const onScheduleTypeChange = (index: number): void => {
  const comp = compensations.value[index]
  comp.payment_schedule_period = isPeriodSchedule(comp.payment_schedule_type) ? 'month' : null
  comp.payment_schedule_value = defaultScheduleValue(comp)
}

const onSchedulePeriodChange = (index: number): void => {
  const comp = compensations.value[index]
  comp.payment_schedule_value = defaultScheduleValue(comp)
}

const normalizeScheduleValue = (index: number): void => {
  const comp = compensations.value[index]
  if (comp.payment_schedule_type === 'fixed_date') {
    const minDate = todayIso()
    const value = String(comp.payment_schedule_value || '')
    if (!value || value < minDate) comp.payment_schedule_value = minDate
    return
  }

  const bounds = scheduleBounds(comp)
  const parsed = parseInt(String(comp.payment_schedule_value || ''), 10)
  let next = Number.isNaN(parsed) ? (bounds.min || 1) : parsed
  if (bounds.min != null && next < bounds.min) next = bounds.min
  if (bounds.max != null && next > bounds.max) next = bounds.max
  comp.payment_schedule_value = String(next)
}

const addCompensation = (): void => {
  if (compensations.value.length >= 4) return
  compensations.value = [...compensations.value, emptyCompensation()]
}

const removeCompensation = (index: number): void => {
  const updated = [...compensations.value]
  updated.splice(index, 1)
  compensations.value = updated
}

const updateBaseAmount = (index: number): void => {
  const comp = compensations.value[index]
  comp.calculation_base_amount = props.baseAmounts[comp.calculation_base] || 0
  recalcAmount(index)
}

const onValueTypeChange = (index: number): void => {
  const comp = compensations.value[index]
  comp.min_amount = null
  comp.max_amount = null
  comp.min_percent = null
  comp.max_percent = null
  recalcAmount(index)
}

const recalcAmount = (index: number): void => {
  const comp = compensations.value[index]
  const base = Number(comp.calculation_base_amount) || 0
  let raw = 0

  if (comp.value_type === 'percent') {
    raw = base * (Number(comp.value) || 0) / 100
    if (comp.min_amount != null && raw < comp.min_amount) raw = comp.min_amount
    if (comp.max_amount != null && raw > comp.max_amount) raw = comp.max_amount
  } else {
    raw = Number(comp.value) || 0
    if (base > 0) {
      const minFromPct = comp.min_percent != null ? base * comp.min_percent / 100 : null
      const maxFromPct = comp.max_percent != null ? base * comp.max_percent / 100 : null
      if (minFromPct != null && raw < minFromPct) raw = minFromPct
      if (maxFromPct != null && raw > maxFromPct) raw = maxFromPct
    }
  }

  comp.amount = Math.round(raw)
}

const computeDueDate = (comp: EditableCompensation): string => {
  const today = new Date()
  const type = comp.payment_schedule_type
  const val = comp.payment_schedule_value

  if (!val) return '—'
  if (type === 'fixed_date') return formatDate(String(val) < todayIso() ? todayIso() : val)

  const n = parseInt(val, 10)
  if (Number.isNaN(n)) return '—'
  const bounds = scheduleBounds(comp)
  const normalized = Math.min(
    bounds.max ?? n,
    Math.max(bounds.min ?? n, n)
  )

  let result: Date | null = null
  if (type === 'days_count') {
    result = new Date(today)
    result.setDate(result.getDate() + normalized)
  } else if (isPeriodSchedule(type)) {
    const period = schedulePeriod(comp)
    if (period === 'week') {
      const current = today.getDay() === 0 ? 7 : today.getDay()
      const daysAhead = ((normalized - current) + 7) % 7 || 7
      result = new Date(today)
      result.setDate(result.getDate() + daysAhead)
    } else {
      const start = nextPeriodStart(today, period)
      const nextStart = addPeriod(start, period)
      const periodLength = Math.round((nextStart.getTime() - start.getTime()) / 86400000)
      result = new Date(start)
      result.setDate(result.getDate() + Math.min(normalized, periodLength) - 1)
    }
  } else if (type === 'weekly') {
    const current = today.getDay() === 0 ? 7 : today.getDay()
    const daysAhead = ((normalized - current) + 7) % 7 || 7
    result = new Date(today)
    result.setDate(result.getDate() + daysAhead)
  } else if (type === 'quarterly') {
    const start = nextPeriodStart(today, 'quarter')
    const nextStart = addPeriod(start, 'quarter')
    const periodLength = Math.round((nextStart.getTime() - start.getTime()) / 86400000)
    result = new Date(start)
    result.setDate(result.getDate() + Math.min(normalized, periodLength) - 1)
  }

  return result ? formatDate(result) : '—'
}

const nextPeriodStart = (reference: Date, period: CompensationSchedulePeriod): Date => {
  if (period === 'month') return addMonths(new Date(reference.getFullYear(), reference.getMonth(), 1), 1)
  if (period === 'two_months') {
    const startMonth = Math.floor(reference.getMonth() / 2) * 2
    return addMonths(new Date(reference.getFullYear(), startMonth, 1), 2)
  }
  if (period === 'quarter') {
    const startMonth = Math.floor(reference.getMonth() / 3) * 3
    return addMonths(new Date(reference.getFullYear(), startMonth, 1), 3)
  }
  if (period === 'half_year') {
    const startMonth = reference.getMonth() < 6 ? 0 : 6
    return addMonths(new Date(reference.getFullYear(), startMonth, 1), 6)
  }
  if (period === 'year') return new Date(reference.getFullYear() + 1, 0, 1)
  return new Date(reference)
}

const addPeriod = (reference: Date, period: CompensationSchedulePeriod): Date => {
  const months: Partial<Record<CompensationSchedulePeriod, number>> = {
    month: 1,
    two_months: 2,
    quarter: 3,
    half_year: 6,
    year: 12
  }
  const monthCount = months[period]
  if (monthCount == null) {
    const result = new Date(reference)
    result.setDate(result.getDate() + 7)
    return result
  }
  return addMonths(reference, monthCount)
}

const addMonths = (reference: Date, months: number): Date =>
  new Date(reference.getFullYear(), reference.getMonth() + months, 1)

const formatDate = (d: string | Date): string => {
  const date = d instanceof Date ? d : new Date(d)
  if (Number.isNaN(date.getTime())) return String(d)
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

watch(
  () => props.baseAmounts,
  () => {
    compensations.value.forEach((comp: EditableCompensation, i: number) => {
      const newBase = props.baseAmounts[comp.calculation_base]
      if (newBase !== undefined && newBase !== comp.calculation_base_amount) {
        comp.calculation_base_amount = newBase
        recalcAmount(i)
      }
    })
  },
  { deep: true }
)
</script>
