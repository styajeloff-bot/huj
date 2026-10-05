<template>
  <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
    <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
      <div class="p-6 border-b border-gray-200">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-semibold text-gray-900">
            Назначение лизинговых компаний
          </h3>
          <button @click="$emit('close')" class="text-gray-400 hover:text-gray-600">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>
        <p class="text-sm text-gray-500 mt-1">
          Заявка {{ formatApplicationNumber(application) }} | {{ application.name }}
        </p>
      </div>

      <div v-if="errorMessage" class="mx-6 mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700" role="alert">
        {{ errorMessage }}
      </div>

      <div class="p-6 overflow-y-auto max-h-[60vh]">
        <!-- Loading -->
        <div v-if="loading" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p class="mt-2 text-gray-600">Загружаем лизинговые компании...</p>
        </div>

        <!-- Companies list: selected_leasing_companies stores leasing_companies.id (LC PK), not companies.id. -->
        <div v-else class="space-y-3">
          <label
            v-if="leasingCompanies.length > 0"
            class="flex items-center p-4 border rounded-lg cursor-pointer transition-colors border-gray-200 bg-gray-50 hover:bg-gray-100"
          >
            <input
              v-model="allSelected"
              type="checkbox"
              class="w-5 h-5 text-blue-600 rounded focus:ring-blue-500"
            >
            <div class="ml-3 flex-1">
              <div class="font-medium text-gray-900">Выбрать все</div>
              <div class="text-sm text-gray-500">Отметить или снять все лизинговые компании</div>
            </div>
          </label>

          <label
            v-for="company in leasingCompanies"
            :key="company.id"
            class="flex items-center p-4 border rounded-lg cursor-pointer transition-colors"
            :class="selectedIds.includes(company.id) ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'"
          >
            <input
              type="checkbox"
              :value="company.id"
              v-model="selectedIds"
              class="w-5 h-5 text-blue-600 rounded focus:ring-blue-500"
            >
            <div class="ml-3 flex-1">
              <div class="font-medium text-gray-900">{{ company.name }}</div>
              <div class="text-sm text-gray-500">
                ИНН: {{ company.inn }}
                <span v-if="company.average_down_payment_percent">
                  | Аванс от {{ company.average_down_payment_percent }}%
                </span>
                <span v-if="company.average_lease_term_months">
                  | Срок {{ company.average_lease_term_months }} мес.
                </span>
              </div>
            </div>
          </label>

          <div v-if="leasingCompanies.length === 0" class="text-center py-8 text-gray-500">
            Нет доступных лизинговых компаний
          </div>
        </div>
      </div>

      <div class="p-6 border-t border-gray-200 bg-gray-50 flex justify-between items-center">
        <div class="text-sm text-gray-600">
          Выбрано: {{ selectedIds.length }} из {{ leasingCompanies.length }}
        </div>
        <div class="flex space-x-3">
          <button @click="$emit('close')" class="btn-secondary">
            Отмена
          </button>
          <button 
            @click="saveSelection" 
            :disabled="saving || selectedIds.length === 0"
            class="btn-primary disabled:opacity-50"
          >
            <span v-if="saving">Сохранение...</span>
            <span v-else>Назначить</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { LeasingCompany } from '~/types/features'
import type { UUID } from '~/types/ids'
import { formatSourcedApplicationNumber as formatApplicationNumber } from '~/features/applications/sourceType'

interface ApplicationProps {
  id: UUID
  name: string
  display_number?: string
  selected_leasing_companies?: UUID[]
}

const props = defineProps<{
  application: ApplicationProps
}>()

const emit = defineEmits(['close', 'saved'])

const config = useRuntimeConfig()

const leasingCompanies = ref<LeasingCompany[]>([])
const selectedIds = ref<UUID[]>([])
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')

const allSelected = computed({
  get: () => leasingCompanies.value.length > 0
    && leasingCompanies.value.every(company => selectedIds.value.includes(company.id)),
  set: (checked: boolean) => {
    selectedIds.value = checked ? leasingCompanies.value.map(company => company.id) : []
  },
})

const fetchLeasingCompanies = async () => {
  loading.value = true
  try {
    const response = await $fetch<{ companies?: LeasingCompany[] }>('/api/v1/admin/leasing-companies', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    leasingCompanies.value = response.companies || []
    
    // Pre-select already assigned companies
    if (props.application.selected_leasing_companies?.length) {
      selectedIds.value = [...props.application.selected_leasing_companies]
    }
  } catch (err) {
    console.error('Error fetching leasing companies:', err)
  } finally {
    loading.value = false
  }
}

const saveSelection = async () => {
  if (selectedIds.value.length === 0) return

  saving.value = true
  errorMessage.value = ''
  try {
    await $fetch(`/api/v1/admin/applications/${props.application.id}/assign-leasing-companies`, {
      method: 'PUT',
      body: { leasing_company_ids: selectedIds.value },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    emit('saved')
  } catch (err: unknown) {
    const payload = err as {
      data?: {
        detail?: string | { message?: string }
        error?: string
        message?: string
        error_code?: string
      }
    }
    const detail = payload.data?.detail
    errorMessage.value = typeof detail === 'string'
      ? detail
      : detail?.message
        || payload.data?.message
        || payload.data?.error
        || 'Ошибка при назначении ЛК'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchLeasingCompanies()
})
</script>
