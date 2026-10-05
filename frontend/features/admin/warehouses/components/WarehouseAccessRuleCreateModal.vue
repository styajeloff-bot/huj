<template>
  <div class="fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
    <div class="bg-white rounded-lg shadow-xl max-w-2xl w-full my-8 max-h-[90vh] flex flex-col">
      <!-- Modal Header -->
      <div class="flex items-center justify-between p-6 border-b border-gray-200">
        <h3 class="text-lg font-medium text-gray-900">
          Предоставить доступ к складу
        </h3>
        <button
          type="button"
          class="text-gray-400 hover:text-gray-600 p-1 rounded-md"
          @click="$emit('close')"
        >
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
      </div>

      <!-- Modal Body -->
      <form class="p-6 space-y-5 overflow-y-auto flex-1" @submit.prevent="handleSubmit">
        <!-- Владелец склада -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Владелец склада <span class="text-red-500">*</span>
          </label>
          <SearchableDropdown
            v-model="selectedOwnerId"
            placeholder="Выберите владельца склада"
            :items="ownerCompanyOptions"
            label-key="display_name"
            value-key="id"
            search-placeholder="Поиск по названию или ИНН..."
            :disabled="loadingData"
            @update:modelValue="onOwnerChange"
          />
        </div>

        <!-- Склад -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Склад <span class="text-red-500">*</span>
          </label>
          <select
            v-model="form.warehouse_id"
            class="select-field"
            :disabled="loadingData || !selectedOwnerId"
            required
          >
            <option value="" disabled>{{ selectedOwnerId ? 'Выберите склад' : 'Сначала выберите владельца склада' }}</option>
            <option v-for="wh in filteredWarehouses" :key="wh.id" :value="wh.id">
              {{ wh.name }} ({{ wh.address }})
            </option>
          </select>
          <p v-if="loadingData" class="mt-1 text-xs text-gray-400">Загрузка данных...</p>
          <p v-else-if="selectedOwnerId && filteredWarehouses.length === 0" class="mt-1 text-xs text-amber-600">
            У выбранного владельца нет доступных складов.
          </p>
        </div>

        <!-- Mode: Дилер / Группа дилеров -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">
            Кому предоставляется доступ <span class="text-red-500">*</span>
          </label>
          <div class="flex gap-4">
            <label class="inline-flex items-center cursor-pointer">
              <input
                v-model="form.mode"
                type="radio"
                value="dealers"
                class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
              />
              <span class="ml-2 text-sm text-gray-900">Дилер (отдельные компании)</span>
            </label>
            <label class="inline-flex items-center cursor-pointer">
              <input
                v-model="form.mode"
                type="radio"
                value="dealer_group"
                class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
              />
              <span class="ml-2 text-sm text-gray-900">Группа дилеров</span>
            </label>
          </div>
        </div>

        <!-- Если выбрана «Группа дилеров» -->
        <div v-if="form.mode === 'dealer_group'" class="space-y-4 rounded-lg bg-gray-50 p-4 border border-gray-200">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Группа дилеров <span class="text-red-500">*</span>
            </label>
            <select
              v-model="form.dealer_group_id"
              class="select-field"
              :disabled="loadingData"
              required
            >
              <option value="" disabled>Выберите группу дилеров</option>
              <option v-for="group in filteredDealerGroups" :key="group.id" :value="group.id">
                {{ group.name }}
              </option>
            </select>
            <p v-if="filteredDealerGroups.length === 0 && !loadingData" class="mt-1 text-xs text-amber-600">
              Нет доступных групп дилеров.
            </p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Тип доступа для группы <span class="text-red-500">*</span>
            </label>
            <select
              v-model="form.group_access_type"
              class="select-field"
              required
            >
              <option value="B">В – разрешена работа с заявками</option>
              <option value="C">С – работа с заявками недоступна</option>
            </select>
          </div>
        </div>

        <!-- Если выбран «Дилер» (динамическая таблица) -->
        <div v-else class="space-y-3 rounded-lg bg-gray-50 p-4 border border-gray-200">
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-gray-700">Список дилеров</span>
            <button
              type="button"
              class="btn-secondary text-xs"
              @click="addDealerRow"
            >
              + Добавить дилера
            </button>
          </div>

          <div class="space-y-2">
            <div
              v-for="(row, index) in form.dealers"
              :key="index"
              class="flex items-center gap-2"
            >
              <!-- Выбор дилера -->
              <div class="flex-1">
                <select
                  v-model="row.dealer_id"
                  class="select-field text-sm"
                  required
                >
                  <option value="" disabled>Выберите компанию-дилера</option>
                  <option v-for="dealer in dealers" :key="dealer.id" :value="dealer.id">
                    {{ dealer.name }}{{ dealer.inn ? ` (ИНН: ${dealer.inn})` : '' }}
                  </option>
                </select>
              </div>

              <!-- Тип доступа B / C -->
              <div class="w-64">
                <select
                  v-model="row.access_type"
                  class="select-field text-sm"
                  required
                >
                  <option value="B">В – разрешена работа с заявками</option>
                  <option value="C">С – работа с заявками недоступна</option>
                </select>
              </div>

              <!-- Кнопка удаления строки -->
              <button
                type="button"
                class="p-2 text-gray-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                :disabled="form.dealers.length <= 1"
                title="Удалить строку"
                @click="removeDealerRow(index)"
              >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- Дополнительные параметры (Опциональные: Марка и Сайт) -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-gray-200">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Марка ТС
            </label>
            <select
              v-model="form.brand_id"
              class="select-field"
              :disabled="loadingData"
            >
              <option :value="null">Все марки (без ограничений)</option>
              <option v-for="mark in marks" :key="mark.id" :value="mark.id">
                {{ mark.name }}
              </option>
            </select>
            <p class="mt-1 text-xs text-gray-400">Ограничить доступ к ТС конкретной марки</p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Сайт (витрина)
            </label>
            <select
              v-model="form.site_id"
              class="select-field"
              :disabled="loadingData"
            >
              <option :value="null">Все сайты (глобальный доступ)</option>
              <option v-for="site in storefronts" :key="site.id" :value="site.id">
                {{ site.name || site.slug || site.id }}
              </option>
            </select>
            <p class="mt-1 text-xs text-gray-400">Ограничить действие правила конкретной витриной</p>
          </div>
        </div>

        <!-- Ошибка -->
        <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded-lg">
          <p class="text-sm text-red-600">{{ error }}</p>
        </div>

        <!-- Footer Actions -->
        <div class="pt-4 border-t border-gray-200 flex justify-end space-x-3">
          <button
            type="button"
            class="btn-secondary"
            :disabled="submitting"
            @click="$emit('close')"
          >
            Отмена
          </button>
          <button
            type="submit"
            class="btn-primary"
            :disabled="submitting || loadingData"
          >
            <span v-if="submitting">Сохранение...</span>
            <span v-else>Предоставить доступ</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {
  Warehouse,
  WarehouseDealerGroup,
  WarehouseStorefront,
  WarehouseMark,
  CreateWarehouseAccessRulesRequest
} from '../types'
import type { Company } from '~/types/features'
import { createWarehousesApi } from '../api/warehousesApi'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useAuthStore } from '~/features/auth/store/auth'

const props = defineProps<{
  defaultWarehouseId?: string
}>()

const emit = defineEmits(['close', 'success'])

const config = useRuntimeConfig()
const authStore = useAuthStore()
const api = createWarehousesApi(config)

const loadingData = ref(false)
const submitting = ref(false)
const error = ref('')

const warehouses = ref<Warehouse[]>([])
const ownerCompanies = ref<Company[]>([])
const selectedOwnerId = ref<string>('')
const dealerGroups = ref<WarehouseDealerGroup[]>([])
const dealers = ref<Company[]>([])
const storefronts = ref<WarehouseStorefront[]>([])
const marks = ref<WarehouseMark[]>([])

interface FormState {
  warehouse_id: string
  mode: 'dealers' | 'dealer_group'
  dealer_group_id: string
  group_access_type: 'B' | 'C'
  dealers: { dealer_id: string; access_type: 'B' | 'C' }[]
  site_id: string | null
  brand_id: string | null
}

const form = ref<FormState>({
  warehouse_id: props.defaultWarehouseId || '',
  mode: 'dealers',
  dealer_group_id: '',
  group_access_type: 'B',
  dealers: [{ dealer_id: '', access_type: 'B' }],
  site_id: null,
  brand_id: null
})

const ownerCompanyOptions = computed(() =>
  ownerCompanies.value.map(company => ({
    id: company.id,
    name: company.name,
    company_type: company.company_type,
    display_name: `${company.name}${company.inn ? ` (ИНН: ${company.inn})` : ''} — ${company.company_type === 'distributor' ? 'Дистрибьютор' : 'Дилер'}`
  }))
)

const selectedOwnerCompany = computed(() =>
  ownerCompanies.value.find(c => c.id === selectedOwnerId.value)
)

const filteredWarehouses = computed(() => {
  if (!selectedOwnerId.value) return []
  return warehouses.value.filter(wh => wh.owner_company_id === selectedOwnerId.value)
})

const filteredDealerGroups = computed(() => {
  if (!selectedOwnerId.value) return dealerGroups.value
  if (selectedOwnerCompany.value?.company_type === 'distributor') {
    return dealerGroups.value.filter(g => g.distributor_company_id === selectedOwnerId.value)
  }
  return dealerGroups.value
})

const onOwnerChange = () => {
  if (form.value.warehouse_id) {
    const valid = filteredWarehouses.value.some(w => w.id === form.value.warehouse_id)
    if (!valid) {
      form.value.warehouse_id = filteredWarehouses.value.length === 1 ? filteredWarehouses.value[0].id : ''
    }
  } else if (filteredWarehouses.value.length === 1) {
    form.value.warehouse_id = filteredWarehouses.value[0].id
  }

  if (form.value.dealer_group_id) {
    const groupValid = filteredDealerGroups.value.some(g => g.id === form.value.dealer_group_id)
    if (!groupValid) {
      form.value.dealer_group_id = ''
    }
  }
}

const addDealerRow = () => {
  form.value.dealers.push({ dealer_id: '', access_type: 'B' })
}

const removeDealerRow = (index: number) => {
  if (form.value.dealers.length > 1) {
    form.value.dealers.splice(index, 1)
  }
}

const fetchInitialData = async () => {
  loadingData.value = true
  try {
    const [whRes, groupsRes, dealersRes, storefrontsRes, marksRes] = await Promise.all([
      api.getMyWarehouses(),
      api.getDealerGroups(),
      api.getCompanies({ company_type: 'dealer', limit: 1000 }),
      api.getStorefronts(),
      api.getWarehouseMarks()
    ])

    warehouses.value = whRes.warehouses || []
    dealerGroups.value = groupsRes.dealer_groups || groupsRes.items || []
    dealers.value = (dealersRes.companies || []).filter(c => c.company_type === 'dealer')
    storefronts.value = storefrontsRes.items || storefrontsRes.storefronts || []
    marks.value = marksRes.marks || marksRes.items || []

    let companiesList: Company[] = []
    try {
      const allCompaniesRes = await api.getCompanies({ limit: 1000 })
      companiesList = allCompaniesRes.companies || []
    } catch {
      const userCompRes = await api.getUserCompanies()
      companiesList = userCompRes.companies || []
    }

    const filteredOwners = companiesList.filter(
      c => c.company_type === 'dealer' || c.company_type === 'distributor'
    )
    const knownOwnerIds = new Set(filteredOwners.map(c => c.id))
    for (const wh of warehouses.value) {
      if (wh.owner_company_id && !knownOwnerIds.has(wh.owner_company_id)) {
        filteredOwners.push({
          id: wh.owner_company_id,
          name: wh.owner_company_name || wh.company_name || 'Неизвестная компания',
          company_type: wh.owner_company_type || 'dealer'
        } as Company)
        knownOwnerIds.add(wh.owner_company_id)
      }
    }
    ownerCompanies.value = filteredOwners

    // If user is distributor, auto-set to their company
    if (authStore.isDistributor) {
      const myCompanyId = authStore.activeCompanyId || authStore.user?.company_id
      if (myCompanyId) {
        selectedOwnerId.value = myCompanyId
      }
    } else if (props.defaultWarehouseId) {
      const defaultWh = warehouses.value.find(w => w.id === props.defaultWarehouseId)
      if (defaultWh?.owner_company_id) {
        selectedOwnerId.value = defaultWh.owner_company_id
      }
    } else if (ownerCompanies.value.length === 1) {
      selectedOwnerId.value = ownerCompanies.value[0].id
    }

    if (props.defaultWarehouseId) {
      form.value.warehouse_id = props.defaultWarehouseId
    } else if (!form.value.warehouse_id && filteredWarehouses.value.length === 1) {
      form.value.warehouse_id = filteredWarehouses.value[0].id
    }
  } catch (err) {
    console.error('Error fetching initial data for access rule creation:', err)
    error.value = 'Ошибка при загрузке справочных данных для формы.'
  } finally {
    loadingData.value = false
  }
}

const handleSubmit = async () => {
  error.value = ''

  if (!selectedOwnerId.value) {
    error.value = 'Пожалуйста, выберите владельца склада.'
    return
  }

  if (!form.value.warehouse_id) {
    error.value = 'Пожалуйста, выберите склад.'
    return
  }

  if (form.value.mode === 'dealer_group') {
    if (!form.value.dealer_group_id) {
      error.value = 'Пожалуйста, выберите группу дилеров.'
      return
    }
  } else {
    const filledDealers = form.value.dealers.filter(d => Boolean(d.dealer_id))
    if (filledDealers.length === 0) {
      error.value = 'Пожалуйста, выберите хотя бы одного дилера.'
      return
    }
    const ids = filledDealers.map(d => d.dealer_id)
    if (new Set(ids).size !== ids.length) {
      error.value = 'В списке дилеров присутствуют дубликаты. Пожалуйста, удалите повторяющиеся строки.'
      return
    }
  }

  submitting.value = true

  try {
    const payload: CreateWarehouseAccessRulesRequest = {
      warehouse_id: form.value.warehouse_id,
      mode: form.value.mode,
      dealer_group_id: form.value.mode === 'dealer_group' ? form.value.dealer_group_id : undefined,
      group_access_type: form.value.mode === 'dealer_group' ? form.value.group_access_type : undefined,
      dealers: form.value.mode === 'dealers' ? form.value.dealers.filter(d => Boolean(d.dealer_id)) : undefined,
      site_id: form.value.site_id || undefined,
      brand_id: form.value.brand_id || undefined
    }

    await api.createAccessRules(payload)
    emit('success')
  } catch (err: unknown) {
    console.error('Error creating access rules:', err)
    const e = err as { data?: { detail?: string; error?: string; message?: string } }
    error.value = e.data?.detail || e.data?.error || e.data?.message || 'Не удалось сохранить правила доступа.'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchInitialData()
})
</script>
