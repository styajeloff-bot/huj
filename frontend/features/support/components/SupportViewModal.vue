<template>
  <div
    v-if="show"
    class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4"
    @click.self="$emit('close')"
  >
    <div class="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6">
      <div class="flex items-center justify-between mb-6">
        <h3 class="text-lg font-semibold text-gray-900">{{ program.name }}</h3>
        <button class="text-gray-500 hover:text-gray-700" @click="$emit('close')">✕</button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Left column -->
        <div class="space-y-4">
          <div v-if="program.comment" class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Комментарий</div>
            <p class="text-sm text-gray-700">{{ program.comment }}</p>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div class="text-xs font-medium text-gray-500 mb-1">Марка</div>
              <div class="text-sm text-gray-900 font-medium">{{ program.mark_name || '—' }}</div>
            </div>
            <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div class="text-xs font-medium text-gray-500 mb-1">Модель</div>
              <div class="text-sm text-gray-900 font-medium">{{ modelNames || 'Все модели' }}</div>
            </div>
          </div>

          <div v-if="productionDateRangeDisplay" class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Даты производства</div>
            <div class="text-sm text-gray-900">
              {{ productionDateRangeDisplay }}
            </div>
          </div>

          <div v-else-if="productionYearRangeDisplay" class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Год производства</div>
            <div class="text-sm text-gray-900">
              {{ productionYearRangeDisplay }}
            </div>
          </div>

          <div v-if="deliveryDateRangeDisplay" class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Даты поставки</div>
            <div class="text-sm text-gray-900">
              {{ deliveryDateRangeDisplay }}
            </div>
          </div>

          <div v-if="vinsDisplay" class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">VIN</div>
            <div class="text-sm text-gray-900 break-all">{{ vinsDisplay }}</div>
          </div>

          <div v-if="dealerGroupsDisplay" class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Группы дилеров</div>
            <div class="text-sm text-gray-900">{{ dealerGroupsDisplay }}</div>
          </div>

          <div v-if="distributorDisplay" class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Дистрибьютор</div>
            <div class="text-sm text-gray-900">{{ distributorDisplay }}</div>
          </div>

          <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Лизинговые компании</div>
            <div class="text-sm text-gray-900">{{ leasingCompaniesDisplay }}</div>
          </div>

          <div v-if="billOfLadingDisplay" class="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
            <div class="text-xs font-medium text-yellow-700 mb-1">Сопровождающая документация</div>
            <div v-if="billOfLadingDisplay.bill_date" class="text-sm text-gray-700 mb-1">
              Дата: {{ formatDate(billOfLadingDisplay.bill_date) }}
            </div>
            <a
              v-if="billOfLadingDisplay.file_path"
              :href="billOfLadingDisplay.file_path"
              target="_blank"
              class="text-sm text-blue-600 hover:underline"
            >
              {{ billOfLadingDisplay.file_name || 'Открыть файл' }}
            </a>
          </div>
        </div>

        <!-- Right column -->
        <div class="space-y-4">
          <div class="p-3 bg-blue-50 rounded-lg border border-blue-200">
            <div class="text-xs font-medium text-blue-600 mb-1">Тип поддержки</div>
            <div class="text-sm text-gray-900 font-medium">{{ getSupportTypeLabel(program.support_type) }}</div>
          </div>

          <div class="p-3 bg-green-50 rounded-lg border border-green-200">
            <div class="text-xs font-medium text-green-600 mb-2">Параметры поддержки</div>
            <div class="space-y-1 text-sm">
              <div v-if="!hasSupportParamDetails(program.support_params, program.support_type)" class="text-gray-500">
                Параметры не заданы
              </div>
              <div v-if="program.support_params?.value_type && program.support_params?.value != null" class="flex justify-between">
                <span class="text-gray-600">Значение:</span>
                <span class="text-gray-900">
                  {{ program.support_params.value_type === 'percent' ? `${program.support_params.value}%` : `${formatRub(program.support_params.value)} р` }}
                </span>
              </div>
              <div v-if="program.support_params?.min_amount" class="flex justify-between">
                <span class="text-gray-600">Сумма от:</span>
                <span class="text-gray-900">{{ formatRub(program.support_params.min_amount) }} р</span>
              </div>
              <div v-if="program.support_params?.max_amount" class="flex justify-between">
                <span class="text-gray-600">Сумма до:</span>
                <span class="text-gray-900">{{ formatRub(program.support_params.max_amount) }} р</span>
              </div>
              <div v-if="program.support_params?.min_percent" class="flex justify-between">
                <span class="text-gray-600">От %:</span>
                <span class="text-gray-900">{{ program.support_params.min_percent }}%</span>
              </div>
              <div v-if="program.support_params?.max_percent" class="flex justify-between">
                <span class="text-gray-600">До %:</span>
                <span class="text-gray-900">{{ program.support_params.max_percent }}%</span>
              </div>
              <template v-if="program.support_type === 'leasing_interest_compensation'">
                <div v-if="program.support_params?.compensation_period_months" class="flex justify-between">
                  <span class="text-gray-600">Срок компенсации:</span>
                  <span class="text-gray-900">{{ program.support_params.compensation_period_months }} мес.</span>
                </div>
                <div v-if="program.support_params?.start_month" class="flex justify-between">
                  <span class="text-gray-600">Месяц начала:</span>
                  <span class="text-gray-900">{{ program.support_params.start_month }}</span>
                </div>
              </template>
            </div>
          </div>

          <div
            v-if="compensationTemplates.length"
            class="p-3 bg-purple-50 rounded-lg border border-purple-200"
          >
            <div class="text-xs font-medium text-purple-700 mb-2">Компенсации</div>
            <div class="space-y-2 text-sm">
              <div
                v-for="(template, index) in compensationTemplates"
                :key="template.id || index"
                class="border-t border-purple-100 pt-2 first:border-t-0 first:pt-0"
              >
                <div class="font-medium text-gray-900">
                  {{ payerLabel(template.payer) }} → {{ recipientLabel(template.recipient) }}
                </div>
                <div class="text-gray-700">
                  {{ compensationValueLabel(template) }}
                </div>
                <div class="text-xs text-gray-500">
                  График: {{ scheduleLabel(template.payment_schedule_type, template.payment_schedule_value, template.payment_schedule_period) }}
                </div>
                <div v-if="template.comment" class="text-xs text-gray-500">
                  {{ template.comment }}
                </div>
              </div>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div class="text-xs font-medium text-gray-500 mb-1">Начало</div>
              <div class="text-sm text-gray-900">{{ formatDate(program.starts_at) }}</div>
            </div>
            <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div class="text-xs font-medium text-gray-500 mb-1">Завершение действия</div>
              <div class="text-sm text-gray-900">{{ formatDate(program.ends_at) }}</div>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div class="text-xs font-medium text-gray-500 mb-1">Статус</div>
              <span
                class="inline-flex px-2 py-0.5 text-xs font-semibold rounded-full"
                :class="program.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'"
              >
                {{ program.is_active ? 'Активна' : 'Неактивна' }}
              </span>
            </div>
            <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <div class="text-xs font-medium text-gray-500 mb-1">Видимость</div>
              <div class="flex flex-wrap gap-1 mt-0.5">
                <span v-if="program.show_to_leasing_company !== false" class="inline-flex px-1.5 py-0.5 text-xs rounded bg-blue-100 text-blue-700">ЛК</span>
                <span v-if="program.show_to_client !== false" class="inline-flex px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-700">Клиент</span>
                <span v-if="program.show_to_leasing_company === false && program.show_to_client === false" class="text-gray-400 text-xs">—</span>
              </div>
            </div>
          </div>

          <div class="p-3 bg-gray-50 rounded-lg border border-gray-200">
            <div class="text-xs font-medium text-gray-500 mb-1">Совместимость</div>
            <div class="text-sm text-gray-900">
              {{ program.is_compatible ? `Совместима с ${program.compatible_support_ids.length} программами` : 'Эксклюзивная программа' }}
            </div>
          </div>

        </div>
      </div>

      <div class="mt-6 flex justify-end">
        <button class="btn-secondary" @click="$emit('close')">Закрыть</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SupportProgram } from '~/types/admin'

const props = defineProps<{
  show: boolean
  program: SupportProgram
}>()

defineEmits(['close'])

const SUPPORT_TYPE_LABELS = {
  down_payment_compensation: 'Компенсация первого взноса (компенсация лизинговой)',
  vehicle_discount_dealer_compensation: 'Поддержка на ТС (компенсация дилеру)',
  vehicle_discount_dealer_invoice: 'Поддержка на ТС (уменьшение счета дилеру)',
  leasing_interest_compensation: 'Компенсация процентов по лизингу (компенсация лизинговой)'
}

const getSupportTypeLabel = (type: string) => (SUPPORT_TYPE_LABELS as Record<string, string>)[type] || type || '—'

const formatDate = (val: string | undefined | null) => {
  if (!val) return 'Без ограничений'
  const raw = String(val)
  const iso = raw.slice(0, 10)
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (m) return `${m[3]}.${m[2]}.${m[1]}`
  const d = new Date(raw)
  if (!Number.isNaN(d.getTime())) {
    return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
  }
  return iso
}

const rangeDate = (val: string | undefined | null) => val ? formatDate(val) : '—'

const formatRub = (n: number | null | undefined) => {
  if (n == null || Number.isNaN(Number(n))) return '0'
  return new Intl.NumberFormat('ru-RU').format(Number(n))
}

const payerLabel = (value: string) => ({
  distributor: 'Дистрибьютор',
  dealer: 'Дилер',
  carcraft: 'CarCraft',
  minpromtorg: 'Минпромторг',
  client: 'Клиент'
} as Record<string, string>)[value] || value

const recipientLabel = (value: string) => ({
  leasing_company: 'Лизинговая компания',
  dealer: 'Дилер',
  carcraft: 'CarCraft',
  client: 'Клиент'
} as Record<string, string>)[value] || value

const compensationBaseLabel = (value: string) => ({
  base_price: 'РРЦ',
  special_price: 'специальной цены',
  dealer_cost: 'себестоимости',
  application_price: 'цены в заявке',
  down_payment: 'первого взноса',
  support_amount: 'суммы поддержки'
} as Record<string, string>)[value] || value

const compensationValueLabel = (template: NonNullable<SupportProgram['compensation_templates']>[number]) => {
  const value = template.value_type === 'percent'
    ? `${template.value}% от ${compensationBaseLabel(template.calculation_base)}`
    : `${formatRub(template.value)} р`
  const limits = []
  if (template.min_amount) limits.push(`мин. ${formatRub(template.min_amount)} р`)
  if (template.max_amount) limits.push(`макс. ${formatRub(template.max_amount)} р`)
  if (template.min_percent) limits.push(`мин. ${template.min_percent}%`)
  if (template.max_percent) limits.push(`макс. ${template.max_percent}%`)
  return limits.length ? `${value} (${limits.join(', ')})` : value
}

const scheduleLabel = (type?: string | null, value?: string | null, period?: string | null) => {
  const periodLabels = {
    week: 'неделя',
    month: 'месяц',
    two_months: 'два месяца',
    quarter: 'квартал',
    half_year: 'полугодие',
    year: 'год'
  } as Record<string, string>
  const dayValue = ordinalDayLabel(value)

  if (type === 'fixed_date') {
    return value ? `фиксированная дата, ${formatDate(value)}` : 'фиксированная дата'
  }
  if (type === 'days_count') {
    return value ? `через ${dayCountLabel(value)}` : 'через N дней'
  }
  if (type === 'weekly') {
    return dayValue ? `еженедельно, ${dayValue} недели` : 'еженедельно'
  }
  if (type === 'quarterly') {
    return dayValue ? `ежеквартально, ${dayValue}` : 'ежеквартально'
  }
  if (type === 'reporting_period') {
    const parts = ['раз в период']
    if (period) parts.push(periodLabels[period] || period)
    if (dayValue) parts.push(dayValue)
    return parts.join(', ')
  }
  return type || '—'
}

const ordinalDayLabel = (value?: string | null) => {
  const normalized = String(value || '').trim()
  if (!normalized) return null
  const count = Number(normalized)
  if (Number.isInteger(count) && count > 0) return `${count}-й день`
  return normalized
}

const dayCountLabel = (value?: string | null) => {
  const normalized = String(value || '').trim()
  const count = Number(normalized)
  if (!Number.isInteger(count) || count <= 0) return normalized
  const mod10 = count % 10
  const mod100 = count % 100
  const suffix = mod10 === 1 && mod100 !== 11
    ? 'день'
    : ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100) ? 'дня' : 'дней')
  return `${count} ${suffix}`
}

const hasSupportParamDetails = (
  params: SupportProgram['support_params'] | undefined,
  supportType: string
) => {
  if (!params) return false
  return Boolean(
    params.min_amount ||
    params.max_amount ||
    params.min_percent ||
    params.max_percent ||
    params.value ||
    params.value_type ||
    (
      supportType === 'leasing_interest_compensation' &&
      (params.compensation_period_months || params.start_month)
    )
  )
}

const modelNames = computed(() => {
  if (Array.isArray(props.program.model_ids) && props.program.model_ids.length > 0 && props.program.model_name) {
    return props.program.model_name
  }
  if (props.program.model_name) return props.program.model_name
  return null
})

const productionDateRangeDisplay = computed(() => {
  if (!props.program.production_date_from && !props.program.production_date_to) return null
  return `${rangeDate(props.program.production_date_from)} → ${rangeDate(props.program.production_date_to)}`
})

const productionYearRangeDisplay = computed(() => {
  if (!props.program.production_year_from && !props.program.production_year_to) return null
  return `${props.program.production_year_from || '—'} → ${props.program.production_year_to || '—'}`
})

const deliveryDateRangeDisplay = computed(() => {
  if (!props.program.delivery_date_from && !props.program.delivery_date_to) return null
  return `${rangeDate(props.program.delivery_date_from)} → ${rangeDate(props.program.delivery_date_to)}`
})

const vinsDisplay = computed(() => {
  if (Array.isArray(props.program.vins) && props.program.vins.length > 0) {
    return props.program.vins.join(', ')
  }
  if (props.program.vin) return props.program.vin
  return null
})

const dealerGroupsDisplay = computed(() => {
  if (Array.isArray(props.program.dealer_groups) && props.program.dealer_groups.length > 0) {
    return props.program.dealer_groups.map((g) => g.name || g).join(', ')
  }
  if (props.program.dealer_group_name) return props.program.dealer_group_name
  return null
})

const distributorDisplay = computed(() => {
  if (Array.isArray(props.program.distributors) && props.program.distributors.length > 0) {
    return props.program.distributors.map((d) => d.name || d.id).join(', ')
  }
  if (props.program.distributor_name) return props.program.distributor_name
  if (Array.isArray(props.program.distributor_ids) && props.program.distributor_ids.length > 0) {
    return props.program.distributor_ids.join(', ')
  }
  return props.program.distributor_id || null
})

const leasingCompaniesDisplay = computed(() => {
  if (Array.isArray(props.program.leasing_companies) && props.program.leasing_companies.length > 0) {
    return props.program.leasing_companies.map((c) => c.name).join(', ')
  }
  if (Array.isArray(props.program.leasing_company_ids) && props.program.leasing_company_ids.length > 0) {
    return props.program.leasing_company_ids.join(', ')
  }
  return 'Любые'
})

const billOfLadingDisplay = computed(() => {
  const bol = props.program.bill_of_lading
  if (!bol) return null
  if (!bol.bill_date && !bol.file_path && !bol.file_name) return null
  return bol
})

const compensationTemplates = computed(() => props.program.compensation_templates || [])
</script>
