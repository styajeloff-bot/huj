<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between gap-4">
      <h2 class="text-xl font-semibold text-gray-900">Группы дилеров</h2>
      <button v-if="canManageDealerGroups" @click="openCreateModal" class="btn-primary">
        Создать группу
      </button>
    </div>

    <div class="bg-white rounded-lg border border-gray-200 p-4">
      <div class="grid grid-cols-1 gap-4" :class="props.distributorMode ? 'lg:grid-cols-3' : 'lg:grid-cols-4'">
        <div>
          <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">Поиск</label>
          <input
            v-model="filters.search"
            type="text"
            class="input-field"
            placeholder="Название группы"
            @keyup.enter="applyFilters"
          />
        </div>

        <SearchableDropdown
          v-if="!props.distributorMode"
          v-model="filters.distributor_id"
          label="Дистрибьютор"
          placeholder="Все дистрибьюторы"
          clear-label="Все дистрибьюторы"
          allow-clear
          :items="distributorOptions"
          label-key="display_name"
          value-key="id"
          search-placeholder="Найти дистрибьютора..."
          @update:modelValue="onDistributorFilterChange"
        />

        <SearchableDropdown
          v-model="filters.dealer_id"
          label="Дилер"
          placeholder="Все дилеры"
          clear-label="Все дилеры"
          allow-clear
          :items="dealerOptions"
          label-key="display_name"
          value-key="id"
          search-placeholder="Найти дилера..."
          @update:modelValue="applyFilters"
        />

        <div>
          <label class="block text-xs font-semibold text-gray-500 uppercase mb-1">Статус</label>
          <select v-model="filters.is_active" class="input-field" @change="applyFilters">
            <option value="">Все</option>
            <option value="true">Активные</option>
            <option value="false">Неактивные</option>
          </select>
        </div>
      </div>

      <div class="mt-4 flex flex-wrap justify-end gap-2">
        <button class="btn-secondary text-sm" @click="resetFilters">
          Сбросить
        </button>
        <button class="btn-primary text-sm" @click="applyFilters">
          Применить
        </button>
      </div>
    </div>

    <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div v-if="loading" class="p-6 text-gray-600">Загрузка...</div>
      <div v-else-if="error" class="p-6 text-red-600">{{ error }}</div>
      <div v-else-if="groups.length === 0" class="p-6 text-gray-600">Группы не найдены</div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Группа</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Дистрибьютор</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Дилеры</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Создана</th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Статус</th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Действия</th>
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-gray-200">
            <tr v-for="group in groups" :key="group.id">
              <td class="px-6 py-4 align-top">
                <div class="text-sm font-medium text-gray-900">{{ group.name }}</div>
                <div v-if="group.description" class="text-xs text-gray-500 mt-1">{{ group.description }}</div>
              </td>
              <td class="px-6 py-4 align-top text-sm text-gray-700">
                {{ formatCompanyWithInn(group.distributor) }}
              </td>
              <td class="px-6 py-4 align-top text-sm text-gray-700">
                <div v-if="group.dealers?.length">
                  {{ dealersSummary(group) }}
                </div>
                <div v-else>Нет дилеров</div>
              </td>
              <td class="px-6 py-4 align-top text-sm text-gray-700">
                {{ formatDate(group.created_at) }}
              </td>
              <td class="px-6 py-4 align-top">
                <span
                  class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                  :class="group.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'"
                >
                  {{ group.is_active ? 'Активна' : 'Неактивна' }}
                </span>
              </td>
              <td class="px-6 py-4 align-top text-right text-sm font-medium">
                <div class="flex justify-end gap-3">
                  <button class="text-blue-600 hover:text-blue-900" @click="openViewModal(group)">
                    Посмотреть
                  </button>
                  <button v-if="canManageDealerGroups" class="text-blue-600 hover:text-blue-900" @click="openEditModal(group)">
                    Редактировать
                  </button>
                  <button
                    v-if="canManageDealerGroups && group.is_active"
                    class="text-red-600 hover:text-red-900 disabled:opacity-50"
                    :disabled="deactivatingId === group.id"
                    @click="deactivateGroup(group)"
                  >
                    <span v-if="deactivatingId === group.id">Удаление...</span>
                    <span v-else>Удалить</span>
                  </button>
                  <span v-else-if="canManageDealerGroups" class="text-gray-400">Деактивирована</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <DealerGroupFormModal
      v-if="canManageDealerGroups"
      :show="showFormModal"
      :group="editingGroup"
      :dealers="dealerCompanies"
      :distributors="distributorCompanies"
      :fixed-distributor="props.distributorMode ? ownDistributorCompany : null"
      @close="closeFormModal"
      @success="handleGroupSuccess"
    />

    <div
      v-if="showViewModal && viewedGroup"
      class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4"
      @click.self="closeViewModal"
    >
      <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
        <div class="flex items-center justify-between mb-6">
          <h3 class="text-lg font-semibold">{{ viewedGroup.name }}</h3>
          <button class="text-gray-500 hover:text-gray-700" @click="closeViewModal">✕</button>
        </div>

        <dl class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <dt class="text-xs font-semibold text-gray-500 uppercase">Дистрибьютор</dt>
            <dd class="mt-1 text-sm text-gray-900">{{ formatCompanyWithInn(viewedGroup.distributor) }}</dd>
          </div>
          <div>
            <dt class="text-xs font-semibold text-gray-500 uppercase">Статус</dt>
            <dd class="mt-1 text-sm text-gray-900">{{ viewedGroup.is_active ? 'Активна' : 'Неактивна' }}</dd>
          </div>
          <div>
            <dt class="text-xs font-semibold text-gray-500 uppercase">Создана</dt>
            <dd class="mt-1 text-sm text-gray-900">{{ formatDate(viewedGroup.created_at) }}</dd>
          </div>
          <div>
            <dt class="text-xs font-semibold text-gray-500 uppercase">Обновлена</dt>
            <dd class="mt-1 text-sm text-gray-900">{{ formatDate(viewedGroup.updated_at) }}</dd>
          </div>
          <div class="sm:col-span-2">
            <dt class="text-xs font-semibold text-gray-500 uppercase">Описание</dt>
            <dd class="mt-1 text-sm text-gray-900">{{ viewedGroup.description || 'Нет описания' }}</dd>
          </div>
        </dl>

        <div class="mt-6">
          <h4 class="text-sm font-semibold text-gray-900 mb-3">Дилеры</h4>
          <div v-if="viewedGroup.dealers?.length" class="border border-gray-200 rounded-lg divide-y divide-gray-200">
            <div v-for="dealer in viewedGroup.dealers" :key="dealer.id" class="px-4 py-3 text-sm text-gray-900">
              {{ formatCompanyWithInn(dealer) }}
            </div>
          </div>
          <div v-else class="text-sm text-gray-600">Нет дилеров</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { createCompaniesAdminApi, type DealerGroupFilters } from '../api/companiesAdminApi'
import DealerGroupFormModal from './DealerGroupFormModal.vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import type { Company, DealerGroup, DealerGroupCompany } from '~/types/features'
import type { UUID } from '~/types/ids'

interface CompanyOption extends Company {
  display_name: string
  [key: string]: unknown
}

const props = withDefaults(defineProps<{
  distributorMode?: boolean
}>(), {
  distributorMode: false
})

const config = useRuntimeConfig()
const api = createCompaniesAdminApi(config)
const toast = useToast()
const authStore = useAuthStore()

const loading = ref(true)
const error = ref('')
const groups = ref<DealerGroup[]>([])
const dealerCompanies = ref<Company[]>([])
const distributorCompanies = ref<Company[]>([])
const ownDistributorCompany = ref<Company | null>(null)
const distributorCanManageDealerGroups = ref(false)
const showFormModal = ref(false)
const showViewModal = ref(false)
const editingGroup = ref<DealerGroup | null>(null)
const viewedGroup = ref<DealerGroup | null>(null)
const deactivatingId = ref<UUID | null>(null)

const filters = ref({
  distributor_id: null as UUID | null,
  dealer_id: null as UUID | null,
  search: '',
  is_active: ''
})

const canManageDealerGroups = computed(() =>
  authStore.isCarCraftEmployee || (
    props.distributorMode &&
    authStore.isCompanyAdmin &&
    distributorCanManageDealerGroups.value
  )
)

const formatCompanyLabel = (company: Pick<Company, 'name' | 'inn'>) =>
  `${company.name}${company.inn ? ` · ИНН ${company.inn}` : ''}`

const distributorOptions = computed<CompanyOption[]>(() =>
  distributorCompanies.value.map((company) => ({
    ...company,
    display_name: formatCompanyLabel(company)
  }))
)

const dealerOptions = computed<CompanyOption[]>(() =>
  dealerCompanies.value.map((company) => ({
    ...company,
    display_name: formatCompanyLabel(company)
  }))
)

const readAdminError = (err: unknown): string => {
  const data = (err as { data?: { detail?: unknown; error?: string; message?: string }; message?: string })?.data
  if (Array.isArray(data?.detail)) {
    return data.detail
      .map((item) => {
        const errorItem = item as { msg?: string }
        return errorItem.msg || ''
      })
      .filter(Boolean)
      .join('; ') || 'Проверьте данные запроса'
  }
  return typeof data?.detail === 'string'
    ? data.detail
    : data?.error || data?.message || (err as { message?: string })?.message || 'Операция не выполнена'
}

const buildGroupFilters = (): DealerGroupFilters => ({
  distributor_id: props.distributorMode
    ? ownDistributorCompany.value?.id ?? null
    : filters.value.distributor_id,
  dealer_id: filters.value.dealer_id,
  search: filters.value.search.trim(),
  is_active: filters.value.is_active,
  page: 1,
  limit: 200
})

const fetchGroups = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await api.getDealerGroups(buildGroupFilters())
    groups.value = response.dealer_groups || []
  } catch (err: unknown) {
    error.value = readAdminError(err) || 'Не удалось загрузить группы дилеров'
  } finally {
    loading.value = false
  }
}

const fetchDistributorReferences = async () => {
  try {
    const profile = await api.getMyCompanyProfile()
    const ownCompany: Company = {
      id: profile.id,
      name: profile.name,
      inn: profile.inn || undefined,
      company_type: 'distributor',
      is_active: profile.is_active !== false
    }
    ownDistributorCompany.value = ownCompany
    distributorCompanies.value = [ownCompany]
    filters.value.distributor_id = ownCompany.id
    distributorCanManageDealerGroups.value = profile.distributor?.can_manage_dealer_groups === true
  } catch (err) {
    console.error('Error fetching distributor company profile:', err)
  }

  try {
    const response = await api.getCurrentDistributorDealers()
    dealerCompanies.value = (response.dealers || []).map((dealer) => ({
      id: dealer.id,
      name: dealer.name || 'Без названия',
      inn: dealer.inn || undefined,
      company_type: 'dealer',
      is_active: true
    }))
  } catch (err) {
    console.error('Error fetching current distributor dealers:', err)
  }
}

const fetchReferences = async () => {
  if (props.distributorMode) {
    await fetchDistributorReferences()
    return
  }

  try {
    const [dealersResponse, distributorsResponse] = await Promise.all([
      api.getDealerCompanies(),
      api.getDistributorCompanies()
    ])
    dealerCompanies.value = dealersResponse.companies || []
    distributorCompanies.value = distributorsResponse.companies || []
  } catch (err) {
    console.error('Error fetching dealer group references:', err)
  }
}

const applyFilters = () => {
  fetchGroups()
}

const onDistributorFilterChange = async (distributorId: UUID | null) => {
  if (!props.distributorMode) {
    if (distributorId) {
      try {
        const response = await api.getDistributorDealers(distributorId)
        dealerCompanies.value = response.dealers || []
        if (filters.value.dealer_id) {
          const ids = new Set((response.dealers || []).map((d) => d.id))
          if (!ids.has(filters.value.dealer_id)) {
            filters.value.dealer_id = null
          }
        }
      } catch (err) {
        console.error('Error fetching distributor dealers for filter:', err)
      }
    } else {
      try {
        const dealersResponse = await api.getDealerCompanies()
        dealerCompanies.value = dealersResponse.companies || []
      } catch (err) {
        console.error('Error restoring all dealers for filter:', err)
      }
    }
  }
  applyFilters()
}

const resetFilters = async () => {
  filters.value = {
    distributor_id: props.distributorMode ? ownDistributorCompany.value?.id ?? null : null,
    dealer_id: null,
    search: '',
    is_active: ''
  }
  if (!props.distributorMode) {
    try {
      const dealersResponse = await api.getDealerCompanies()
      dealerCompanies.value = dealersResponse.companies || []
    } catch (err) {
      console.error('Error restoring all dealers on reset:', err)
    }
  }
  fetchGroups()
}

const openCreateModal = () => {
  if (!canManageDealerGroups.value) return
  editingGroup.value = null
  showFormModal.value = true
}

const openEditModal = (group: DealerGroup) => {
  if (!canManageDealerGroups.value) return
  editingGroup.value = group
  showFormModal.value = true
}

const closeFormModal = () => {
  showFormModal.value = false
  editingGroup.value = null
}

const openViewModal = (group: DealerGroup) => {
  viewedGroup.value = group
  showViewModal.value = true
}

const closeViewModal = () => {
  showViewModal.value = false
  viewedGroup.value = null
}

const handleGroupSuccess = async () => {
  await fetchGroups()
}

const deactivateGroup = async (group: DealerGroup) => {
  if (!canManageDealerGroups.value) return
  if (!confirm(`Удалить группу "${group.name}"?`)) return

  deactivatingId.value = group.id
  try {
    await api.deleteDealerGroup(group.id)
    toast.success('Группа дилеров деактивирована')
    await fetchGroups()
  } catch (err: unknown) {
    toast.error(readAdminError(err))
  } finally {
    deactivatingId.value = null
  }
}

const formatCompanyWithInn = (company?: DealerGroupCompany | Company | null) => {
  if (!company) return '-'
  return `${company.name}${company.inn ? ` · ИНН ${company.inn}` : ''}`
}

const dealersSummary = (group: DealerGroup) => {
  const dealers = group.dealers || []
  const visible = dealers.slice(0, 3).map(formatCompanyWithInn).join(', ')
  const hiddenCount = dealers.length - 3
  return hiddenCount > 0 ? `${visible} и ещё ${hiddenCount}` : visible
}

const formatDate = (value?: string | null) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  }).format(date)
}

onMounted(async () => {
  if (props.distributorMode) {
    await fetchReferences()
    await fetchGroups()
    return
  }

  await Promise.all([
    fetchReferences(),
    fetchGroups()
  ])
})
</script>
