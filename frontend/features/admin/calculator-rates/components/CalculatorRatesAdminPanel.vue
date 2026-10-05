<template>
  <div>
    <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 class="text-xl font-semibold text-gray-900">Ставки калькулятора</h2>
        <p v-if="currentRate" class="mt-1 text-sm text-gray-600">
          Текущая ставка действует с {{ formatDate(currentRate.date_from) }}:
          НДС {{ formatPercent(currentRate.vat_rate) }}, налог на прибыль {{ formatPercent(currentRate.profit_tax_rate) }}
        </p>
      </div>
      <div class="flex gap-2">
        <button
          type="button"
          class="btn-secondary"
          :disabled="loading"
          @click="fetchRates"
        >
          <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': loading }" />
        </button>
        <button type="button" class="btn-primary" @click="openCreateModal">
          <PlusIcon class="h-4 w-4" />
          Создать ставку
        </button>
      </div>
    </div>

    <p v-if="error" class="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
      {{ error }}
    </p>

    <DataTable
      :data="tableRows"
      :columns="columns"
      :loading="loading"
      :actions="actions"
      :paginated="false"
      :filterable="false"
      :searchable="true"
      :show-header="false"
      empty-message="Ставки калькулятора не найдены"
      @action="handleAction"
      @refresh="fetchRates"
    >
      <template #column-date_from="{ item }">
        <span class="font-medium text-gray-900">{{ formatDate(String(item.date_from)) }}</span>
      </template>

      <template #column-date_to="{ item }">
        <span v-if="item.date_to" class="text-gray-900">{{ formatDate(String(item.date_to)) }}</span>
        <span v-else class="inline-flex rounded-full bg-green-100 px-2 py-1 text-xs font-semibold text-green-800">
          Текущая
        </span>
      </template>

      <template #column-status="{ item }">
        <span
          :class="[
            'inline-flex rounded-full px-2 py-1 text-xs font-semibold',
            item.date_to ? 'bg-gray-100 text-gray-700' : 'bg-blue-100 text-blue-800'
          ]"
        >
          {{ item.date_to ? 'История' : 'Активна' }}
        </span>
      </template>

      <template #column-key_rate="{ item }">
        {{ formatPercent(Number(item.key_rate)) }}
      </template>

      <template #column-surcharge="{ item }">
        {{ formatPercent(Number(item.surcharge)) }}
      </template>

      <template #column-vat_rate="{ item }">
        {{ formatPercent(Number(item.vat_rate)) }}
      </template>

      <template #column-profit_tax_rate="{ item }">
        {{ formatPercent(Number(item.profit_tax_rate)) }}
      </template>
    </DataTable>

    <CalculatorRateFormModal
      v-if="showCreateModal"
      @close="showCreateModal = false"
      @success="handleSuccess"
    />

    <CalculatorRateFormModal
      v-if="showEditModal && selectedRate"
      :rate="selectedRate"
      @close="closeEditModal"
      @success="handleSuccess"
    />
  </div>
</template>

<script setup lang="ts">
import { ArrowPathIcon, PencilIcon, PlusIcon } from '@heroicons/vue/24/outline'
import CalculatorRateFormModal from '~/features/admin/calculator-rates/components/CalculatorRateFormModal.vue'
import {
  createCalculatorRatesAdminApi,
  type CalculatorRate
} from '~/features/admin/calculator-rates/api/calculatorRatesAdminApi'
import type { DataTableAction, DataTableColumn } from '~/types'

const config = useRuntimeConfig()
const api = createCalculatorRatesAdminApi(config)

const rates = ref<CalculatorRate[]>([])
const loading = ref(true)
const error = ref('')
const showCreateModal = ref(false)
const showEditModal = ref(false)
const selectedRate = ref<CalculatorRate | null>(null)

const columns: DataTableColumn[] = [
  { key: 'id', label: 'ID' },
  { key: 'date_from', label: 'С' },
  { key: 'date_to', label: 'По' },
  { key: 'status', label: 'Статус' },
  { key: 'key_rate', label: 'Ключевая' },
  { key: 'surcharge', label: 'Надбавка' },
  { key: 'vat_rate', label: 'НДС' },
  { key: 'profit_tax_rate', label: 'Налог на прибыль' }
]

const actions: DataTableAction[] = [
  { key: 'edit', label: 'Редактировать', icon: PencilIcon, className: 'text-blue-600 hover:text-blue-900' }
]

const tableRows = computed<Record<string, unknown>[]>(() =>
  rates.value.map((rate) => ({
    ...rate,
    status: rate.date_to ? 'history' : 'current'
  }))
)

const currentRate = computed(() => rates.value.find((rate) => rate.date_to === null) ?? null)

const formatPercent = (value: number): string => {
  const normalized = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')
  return `${normalized}%`
}

const formatDate = (value: string): string => {
  const [year, month, day] = value.split('-')
  if (!year || !month || !day) return value
  return `${day}.${month}.${year}`
}

const extractError = (err: unknown): string => {
  const data = (err as { data?: { detail?: unknown; error?: string } }).data
  if (typeof data?.error === 'string') return data.error
  if (typeof data?.detail === 'string') return data.detail
  return 'Не удалось загрузить ставки калькулятора'
}

const fetchRates = async () => {
  loading.value = true
  error.value = ''

  try {
    const response = await api.listRates()
    rates.value = response.items
  } catch (err: unknown) {
    error.value = extractError(err)
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  showCreateModal.value = true
}

const closeEditModal = () => {
  selectedRate.value = null
  showEditModal.value = false
}

const handleAction = ({ action, item }: { action: string; item: Record<string, unknown> }) => {
  if (action !== 'edit') return

  const id = String(item.id)
  selectedRate.value = rates.value.find((rate) => rate.id === id) ?? null
  showEditModal.value = Boolean(selectedRate.value)
}

const handleSuccess = () => {
  showCreateModal.value = false
  closeEditModal()
  fetchRates()
}

onMounted(fetchRates)
</script>
