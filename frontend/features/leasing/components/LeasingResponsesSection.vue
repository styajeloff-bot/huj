<template>
  <div class="bg-white rounded-lg shadow-sm p-6">
    <h2 class="text-xl font-semibold text-gray-900 mb-4">
      Ответы лизинговых компаний
    </h2>

    <div v-if="loading" class="text-sm text-gray-500">
      Загрузка ответов...
    </div>

    <div v-else-if="error" class="text-sm text-red-600">
      {{ error }}
    </div>

    <div v-else-if="responses.length === 0" class="text-sm text-gray-500">
      Лизинговые ещё не прислали ответ.
    </div>

    <div v-else class="space-y-6">
      <div
        v-for="(resp, idx) in responses"
        :key="(resp.leasing_company?.id ?? idx) + '-' + (resp.submitted_at ?? '')"
        class="border border-gray-200 rounded-lg p-4"
      >
        <div class="flex items-start justify-between mb-3">
          <div>
            <h3 class="font-semibold text-gray-900">
              {{ resp.leasing_company?.name || 'Лизинговая компания' }}
            </h3>
            <p v-if="resp.submitted_at" class="text-xs text-gray-500 mt-1">
              {{ formatDate(resp.submitted_at) }}
            </p>
          </div>
          <span
            class="inline-flex px-3 py-1 text-xs font-semibold rounded-full"
            :class="decisionClass(resp.decision)"
          >
            {{ decisionLabel(resp.decision) }}
          </span>
        </div>

        <p v-if="resp.decision_comment" class="text-sm text-gray-700 mb-3">
          <strong>Комментарий:</strong> {{ resp.decision_comment }}
        </p>

        <div v-if="resp.response_pdf?.file_name" class="mb-3 text-sm">
          <span class="text-gray-700">PDF: </span>
          <span class="font-medium">{{ resp.response_pdf.file_name }}</span>
        </div>

        <div v-if="resp.proposals.length === 0" class="text-sm text-gray-500">
          Параметры не указаны.
        </div>
        <div v-else class="space-y-4">
          <div
            v-for="(p, pIdx) in resp.proposals"
            :key="p.id"
            class="bg-gray-50 rounded p-3"
          >
            <h4 class="text-sm font-medium text-gray-800 mb-2">
              КП №{{ pIdx + 1 }}
            </h4>
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-gray-500">
                  <th class="text-left font-normal pb-1">
                    Параметр
                  </th>
                  <th class="text-right font-normal pb-1">
                    Запрошено
                  </th>
                  <th class="text-right font-normal pb-1">
                    Предложено
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in displayRows(p.diff)"
                  :key="row.field"
                  :class="row.changed ? 'bg-yellow-50' : ''"
                >
                  <td class="py-1 text-gray-700">
                    {{ row.label }}
                  </td>
                  <td class="py-1 text-right text-gray-600">
                    {{ row.requested }}
                  </td>
                  <td
                    class="py-1 text-right font-medium"
                    :class="row.changed ? 'text-orange-700' : 'text-gray-900'"
                  >
                    {{ row.offered }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  ClientLeasingResponse,
  ProposalDiffField,
} from '~/features/leasing/api/leasingApi'
import { createLeasingApi } from '~/features/leasing/api/leasingApi'

const props = defineProps<{ applicationId: string }>()

const config = useRuntimeConfig()
const api = createLeasingApi(config)

const responses = ref<ClientLeasingResponse[]>([])
const loading = ref(true)
const error = ref('')

const FIELD_LABELS: Record<string, { label: string; format: 'money' | 'percent' | 'months' | 'raw' }> = {
  total_amount: { label: 'Сумма лизинга', format: 'money' },
  down_payment: { label: 'Аванс', format: 'money' },
  down_payment_percent: { label: 'Аванс, %', format: 'percent' },
  lease_term_months: { label: 'Срок', format: 'months' },
  monthly_payment: { label: 'Платёж в месяц', format: 'money' },
  total_cost: { label: 'Полная стоимость', format: 'money' },
  markup: { label: 'Удорожание', format: 'money' },
  rate: { label: 'Ставка', format: 'percent' },
  total_interest: { label: 'Проценты, всего', format: 'money' },
  buyout_amount: { label: 'Выкупная стоимость', format: 'money' },
  vat_refund: { label: 'Возврат НДС', format: 'money' },
  profit_tax_savings: { label: 'Экономия налога на прибыль', format: 'money' },
  total_savings: { label: 'Итоговая экономия', format: 'money' },
}

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDateTime } = useFormatDate()

const formatNumber = (value: unknown, format: 'money' | 'percent' | 'months' | 'raw') => {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(n)) return String(value)
  if (format === 'money') {
    return formatSharedPrice(n)
  }
  if (format === 'percent') return `${n}%`
  if (format === 'months') return `${n} мес.`
  return String(n)
}

const displayRows = (diff: ProposalDiffField[]) =>
  diff
    .filter((d) => d.requested !== null || d.offered !== null)
    .map((d) => {
      const meta = FIELD_LABELS[d.field] || { label: d.field, format: 'raw' as const }
      return {
        field: d.field,
        label: meta.label,
        requested: formatNumber(d.requested, meta.format),
        offered: formatNumber(d.offered, meta.format),
        changed: d.changed,
      }
    })

const decisionLabel = (d: string | null) => {
  if (d === 'approved') return 'Одобрено'
  if (d === 'rejected') return 'Отказано'
  return d || ''
}

const decisionClass = (d: string | null) => {
  if (d === 'approved') return 'bg-green-100 text-green-800'
  if (d === 'rejected') return 'bg-red-100 text-red-800'
  return 'bg-gray-100 text-gray-800'
}

const formatDate = (iso: string) => {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return formatDateTime(d)
}

onMounted(async () => {
  try {
    const result = await api.getClientLeasingResponses(props.applicationId)
    responses.value = result.responses
  } catch (err: unknown) {
    error.value = (err as { data?: { detail?: string } }).data?.detail || 'Не удалось загрузить ответы'
  } finally {
    loading.value = false
  }
})
</script>
