<template>
  <Teleport to="body">
    <div
      v-if="show"
      class="fixed inset-0 z-[100] bg-black bg-opacity-50 flex items-center justify-center p-4"
      @click.self="$emit('close')"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
        <div class="flex items-center justify-between mb-6">
          <h3 class="text-lg font-semibold">
            {{ isEditMode ? 'Редактировать группу дилеров' : 'Создать группу дилеров' }}
          </h3>
          <button class="text-gray-500 hover:text-gray-700" @click="$emit('close')">✕</button>
        </div>

        <form @submit.prevent="submit">
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Название <span class="text-red-500">*</span>
              </label>
              <input
                v-model="form.name"
                type="text"
                class="input-field"
                placeholder="Официальные дилеры"
                required
                @input="clearFeedback"
              />
            </div>

            <div v-if="props.fixedDistributor">
              <label class="block text-sm font-medium text-gray-700 mb-1">Дистрибьютор</label>
              <div class="input-field bg-gray-50 text-gray-700">
                {{ formatCompanyLabel(props.fixedDistributor) }}
              </div>
            </div>
            <SearchableDropdown
              v-else
              v-model="form.distributor_company_id"
              label="Дистрибьютор *"
              placeholder="Выберите дистрибьютора"
              :items="distributorOptions"
              label-key="display_name"
              value-key="id"
              search-placeholder="Найти дистрибьютора..."
              :error="fieldErrors.distributor_company_id"
              @update:modelValue="handleDistributorFieldUpdate"
            />

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Описание
              </label>
              <textarea
                v-model="form.description"
                class="input-field"
                rows="2"
                placeholder="Дополнительные условия"
                @input="clearFeedback"
              ></textarea>
            </div>

            <SearchableDropdown
              v-model="form.dealer_company_ids"
              label="Дилеры в группе"
              :placeholder="dealerDropdownPlaceholder"
              :items="dealerOptions"
              label-key="display_name"
              value-key="id"
              multiple
              show-select-all
              search-placeholder="Найти дилера..."
              :disabled="loadingDistributorDealers || !resolvedDistributorCompanyId"
              :loading="loadingDistributorDealers"
              :empty-label="dealerDropdownEmptyLabel"
              :error="fieldErrors.dealer_company_ids"
              @update:modelValue="handleDealerFieldUpdate"
            />
            <div v-if="loadingDistributorDealers" class="mt-2 flex items-center text-xs text-gray-500">
              <svg class="animate-spin -ml-0.5 mr-2 h-3.5 w-3.5 text-blue-600" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Загрузка дилеров дистрибьютора...
            </div>
            <p v-else-if="resolvedDistributorCompanyId && dealerOptions.length === 0" class="mt-2 text-xs text-amber-700">
              У выбранного дистрибьютора нет привязанных дилеров в дилерской сети
            </p>
            <p v-else-if="!resolvedDistributorCompanyId" class="mt-2 text-xs text-gray-500">
              Выберите дистрибьютора, чтобы указать дилеров.
            </p>
          </div>

          <div v-if="error" class="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-sm text-red-600">{{ error }}</p>
          </div>
          <div v-if="success" class="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
            <p class="text-sm text-green-600">{{ success }}</p>
          </div>

          <div class="mt-6 flex justify-end space-x-3">
            <button type="button" class="btn-secondary" :disabled="submitting" @click="$emit('close')">
              Отмена
            </button>
            <button type="submit" class="btn-primary" :disabled="submitting || loadingDistributorDealers">
              <span v-if="submitting">Сохранение...</span>
              <span v-else>{{ isEditMode ? 'Сохранить' : 'Создать' }}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { createCompaniesAdminApi } from '../api/companiesAdminApi'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import type { Company, DealerGroup } from '~/types/features'
import type { UUID } from '~/types/ids'

interface CompanyOption extends Company {
  display_name: string
  [key: string]: unknown
}

const props = defineProps<{
  show?: boolean
  group?: DealerGroup | null
  dealers?: Company[]
  distributors?: Company[]
  fixedDistributor?: Company | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'success'): void
}>()

const config = useRuntimeConfig()
const api = createCompaniesAdminApi(config)
const authStore = useAuthStore()

const submitting = ref(false)
const loadingDistributorDealers = ref(false)
const distributorDealers = ref<Company[]>([])
const lastLoadedDistributorId = ref<UUID | null>(null)
let currentRequestId = 0

const error = ref('')
const success = ref('')
const fieldErrors = ref({
  distributor_company_id: false,
  dealer_company_ids: false
})

const form = ref({
  name: '',
  description: '',
  distributor_company_id: null as UUID | null,
  dealer_company_ids: [] as UUID[]
})

const isEditMode = computed(() => Boolean(props.group?.id))

const fixedDistributorId = () => props.fixedDistributor?.id || null

const resolvedDistributorCompanyId = computed<UUID | null>(() => {
  const distributorId = fixedDistributorId()
  if (distributorId) return distributorId
  return form.value.distributor_company_id || null
})

const formatCompanyLabel = (company: Pick<Company, 'name' | 'inn'>) =>
  `${company.name}${company.inn ? ` · ИНН ${company.inn}` : ''}`

const distributorOptions = computed<CompanyOption[]>(() =>
  (props.distributors || []).map((company) => ({
    ...company,
    display_name: formatCompanyLabel(company)
  }))
)

const dealerOptions = computed<CompanyOption[]>(() =>
  distributorDealers.value.map((company) => ({
    ...company,
    display_name: formatCompanyLabel(company)
  }))
)

const dealerDropdownPlaceholder = computed(() => {
  if (loadingDistributorDealers.value) return 'Загрузка списка дилеров...'
  if (!resolvedDistributorCompanyId.value) return 'Сначала выберите дистрибьютора'
  return 'Выберите дилеров'
})

const dealerDropdownEmptyLabel = computed(() => {
  if (!resolvedDistributorCompanyId.value) return 'Дистрибьютор не выбран'
  return 'У выбранного дистрибьютора нет привязанных дилеров в дилерской сети'
})

const clearFeedback = () => {
  error.value = ''
  success.value = ''
}

const handleDistributorFieldUpdate = () => {
  fieldErrors.value.distributor_company_id = false
  clearFeedback()
}

const handleDealerFieldUpdate = () => {
  fieldErrors.value.dealer_company_ids = false
  clearFeedback()
}

const resetForm = () => {
  form.value = {
    name: '',
    description: '',
    distributor_company_id: fixedDistributorId(),
    dealer_company_ids: []
  }
  fieldErrors.value = {
    distributor_company_id: false,
    dealer_company_ids: false
  }
}

const fillFormFromGroup = (group: DealerGroup) => {
  const distributorId = fixedDistributorId()
  let distributorCompanyId = group.distributor_company_id
  if (distributorId) {
    distributorCompanyId = distributorId
  }

  form.value = {
    name: group.name || '',
    description: group.description || '',
    distributor_company_id: distributorCompanyId,
    dealer_company_ids: [...group.dealer_company_ids]
  }
}

const fetchDistributorDealers = async (distributorId: UUID | null) => {
  const requestId = ++currentRequestId

  if (!distributorId) {
    distributorDealers.value = []
    lastLoadedDistributorId.value = null
    form.value.dealer_company_ids = []
    return
  }

  loadingDistributorDealers.value = true
  try {
    let dealers: Company[] = []

    if (authStore.isCarCraftEmployee) {
      const response = await api.getDistributorDealers(distributorId)
      dealers = response.dealers || []
    } else {
      try {
        const response = await api.getCurrentDistributorDealers()
        dealers = (response.dealers || []).map((dealer) => ({
          id: dealer.id,
          name: dealer.name || 'Без названия',
          inn: dealer.inn || undefined,
          company_type: 'dealer' as const,
          is_active: true
        }))
      } catch (distributorErr) {
        if (props.dealers?.length) {
          dealers = props.dealers
        } else {
          throw distributorErr
        }
      }
    }

    if (requestId !== currentRequestId) {
      return
    }

    distributorDealers.value = dealers
    lastLoadedDistributorId.value = distributorId

    // Automatically filter out any selected dealers that do not belong to the newly selected distributor
    const availableDealerIds = new Set(dealers.map((d) => d.id))
    form.value.dealer_company_ids = form.value.dealer_company_ids.filter((dealerId) =>
      availableDealerIds.has(dealerId)
    )
  } catch (err) {
    if (requestId !== currentRequestId) {
      return
    }
    console.error('Error fetching distributor dealers:', err)
    distributorDealers.value = []
    form.value.dealer_company_ids = []
  } finally {
    if (requestId === currentRequestId) {
      loadingDistributorDealers.value = false
    }
  }
}

watch(() => props.show, async (isOpen) => {
  if (!isOpen) {
    distributorDealers.value = []
    lastLoadedDistributorId.value = null
    loadingDistributorDealers.value = false
    return
  }

  error.value = ''
  success.value = ''

  if (props.group) {
    fillFormFromGroup(props.group)
  } else {
    resetForm()
  }

  const distributorId = resolvedDistributorCompanyId.value
  if (distributorId && distributorId !== lastLoadedDistributorId.value) {
    await fetchDistributorDealers(distributorId)
  } else if (!distributorId) {
    distributorDealers.value = []
    lastLoadedDistributorId.value = null
  }
})

watch(resolvedDistributorCompanyId, async (newDistributorId, oldDistributorId) => {
  if (!props.show) return
  if (newDistributorId === oldDistributorId) return
  if (newDistributorId === lastLoadedDistributorId.value) return

  await fetchDistributorDealers(newDistributorId)
})

watch(() => props.group, (newGroup) => {
  if (!props.show) return
  if (newGroup) {
    fillFormFromGroup(newGroup)
  } else {
    resetForm()
  }
  const distributorId = resolvedDistributorCompanyId.value
  if (distributorId && distributorId !== lastLoadedDistributorId.value) {
    fetchDistributorDealers(distributorId)
  }
})

watch(() => props.fixedDistributor?.id, (distributorId) => {
  if (distributorId) {
    form.value.distributor_company_id = distributorId
  }
}, { immediate: true })

function readAdminError(err: unknown): string {
  const data = (err as { data?: { detail?: unknown; error?: string; message?: string }; message?: string })?.data
  if (Array.isArray(data?.detail)) {
    return data.detail
      .map((item) => {
        const errorItem = item as { msg?: string }
        return errorItem.msg || ''
      })
      .filter(Boolean)
      .join('; ') || 'Проверьте данные группы'
  }
  return typeof data?.detail === 'string'
    ? data.detail
    : data?.error || data?.message || (err as { message?: string })?.message || 'Ошибка при сохранении группы дилеров'
}

const submit = async () => {
  error.value = ''
  success.value = ''
  fieldErrors.value = {
    distributor_company_id: false,
    dealer_company_ids: false
  }

  try {
    if (!form.value.name.trim()) {
      throw new Error('Название группы обязательно')
    }
    if (!resolvedDistributorCompanyId.value) {
      fieldErrors.value.distributor_company_id = true
      throw new Error('Выберите дистрибьютора')
    }
    if (loadingDistributorDealers.value) {
      throw new Error('Пожалуйста, дождитесь загрузки списка дилеров')
    }
    if (form.value.dealer_company_ids.length === 0) {
      fieldErrors.value.dealer_company_ids = true
      throw new Error('Выберите хотя бы одного дилера')
    }
  } catch (err: unknown) {
    error.value = (err as { message?: string })?.message || 'Проверьте данные группы'
    return
  }

  submitting.value = true

  try {
    const distributorCompanyId = resolvedDistributorCompanyId.value as UUID
    const payload = {
      name: form.value.name.trim(),
      description: form.value.description.trim() || null,
      distributor_company_id: distributorCompanyId,
      dealer_company_ids: form.value.dealer_company_ids
    }

    if (props.group?.id) {
      await api.updateDealerGroup(props.group.id, payload)
      success.value = 'Группа дилеров обновлена'
    } else {
      await api.createDealerGroup(payload)
      success.value = 'Группа дилеров создана'
      resetForm()
    }

    emit('success')
    emit('close')
  } catch (err: unknown) {
    error.value = readAdminError(err)
  } finally {
    submitting.value = false
  }
}
</script>
