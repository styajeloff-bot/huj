<template>
  <div data-storefront-block="client.checkout" class="space-y-4 sm:space-y-6" style="color: var(--storefront-text,#000);">
    <!-- Company Selection -->
    <div class="p-3 sm:p-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg">
      <h5 class="text-sm font-medium text-[color:var(--storefront-title,#111827)] mb-2 sm:mb-3">Выберите компанию</h5>
      
      <div v-if="loadingCompanies" class="text-center py-4">
        <div class="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
        <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загрузка компаний...</p>
      </div>
      
      <div v-else-if="isDealer" class="space-y-2">
        <CompanyAutocomplete
          v-model="dealerCompanySearch"
          placeholder="Введите ИНН или название компании клиента"
          @select="handleDealerCompanySelect"
        />
        <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
          Компания клиента не будет добавлена в ваш профиль.
        </p>
        <p v-if="showCompanyError" class="text-xs text-[color:var(--storefront-error-text,#dc2626)]">
          Выберите компанию клиента из списка
        </p>
      </div>

      <div v-else-if="companies.length === 0" class="text-center py-4 text-[color:var(--storefront-text-muted,#6b7280)]">
        У вас нет привязанных компаний
      </div>

      <div v-else class="space-y-2">
        <select
          v-model="selectedCompanyId"
          class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] text-sm"
          @change="handleCompanyChange"
        >
          <option :value="null">Выберите компанию</option>
          <option v-for="company in companies" :key="company.id" :value="company.id">
            {{ company.name }}{{ company.inn ? ` (ИНН: ${company.inn})` : '' }}
          </option>
        </select>
        
        <p v-if="showCompanyError" class="text-xs text-[color:var(--storefront-error-text,#dc2626)]">
          Пожалуйста, выберите компанию для подачи заявки
        </p>
      </div>
    </div>

    <!-- Normalized commerce items in application -->
    <div v-if="showItemDetails && commerceItems.length > 0" class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3 sm:p-4">
      <h5 class="mb-2 text-sm font-medium text-[color:var(--storefront-title,#111827)] sm:mb-3">Техника в заявке</h5>
      <div class="flex flex-col gap-3">
        <article
          v-for="line in commerceItems"
          :key="`${line.item.ref.type}:${line.item.ref.id}`"
          class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-3"
        >
          <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <p class="font-medium text-[color:var(--storefront-text,#111827)]">{{ line.item.title }}</p>
              <p v-if="line.item.subtitle" class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ line.item.subtitle }}</p>
            </div>
            <p class="shrink-0 text-sm font-bold tabular-nums text-[color:var(--storefront-text,#1d4ed8)]">
              {{ formatCommerceMoney(getCommerceLineTotal(line), line.item.currency_code) }}
            </p>
          </div>
          <p v-if="line.quantity > 1" class="mt-1 text-xs text-[color:var(--storefront-text-muted,#4b5563)]">Количество: {{ line.quantity }} шт.</p>

          <div class="mt-3 grid grid-cols-1 gap-3 border-t border-[color:var(--storefront-border,#f3f4f6)] pt-3 md:grid-cols-2">
            <div>
              <label class="mb-1 block text-xs font-medium text-[color:var(--storefront-label,#374151)]">Цель приобретения</label>
              <SearchableDropdown
                :model-value="selectedLeasingPurposes(line)"
                @update:model-value="updateLeasingPurposes(line, $event)"
                multiple
                :items="purposeOptions"
                label-key="purpose_display_name"
                value-key="purpose_name"
                placeholder="Выберите цель приобретения"
                search-placeholder="Найти цель..."
                :searchable="false"
                :allow-clear="true"
                clear-label="Не выбрано"
              />
              <textarea
                v-if="selectedLeasingPurposes(line).includes('other')"
                v-model.trim="line.leasing_purpose_comment"
                rows="2"
                maxlength="100"
                class="storefront-control mt-2 w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
                placeholder="Укажите цель приобретения"
              />
            </div>

            <div>
              <label class="mb-1 block text-xs font-medium text-[color:var(--storefront-label,#374151)]">Регион</label>
              <SearchableDropdown
                v-model="line.regions"
                :items="regionOptions"
                label-key="region_label"
                value-key="region_display_name"
                :search-keys="['region_display_name', 'region_number', 'region_label']"
                placeholder="Выберите один или несколько регионов"
                search-placeholder="Найти регион..."
                :searchable="true"
                multiple
                show-select-all
                select-all-label="Выбрать все найденные регионы"
              />
              <div class="mt-2 flex flex-wrap gap-3 text-xs">
                <button type="button" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]" @click="selectAllCommerceRegions(line)">Выбрать все регионы</button>
                <button type="button" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:text-[color:var(--storefront-ghost-hover-foreground,#374151)]" @click="line.regions = []">Очистить выбор</button>
              </div>
            </div>
          </div>

          <label class="mt-3 block border-t border-[color:var(--storefront-border,#f3f4f6)] pt-3">
            <span class="mb-1 block text-xs font-medium text-[color:var(--storefront-text,#374151)]">Комментарий <span class="font-normal text-[color:var(--storefront-text-muted,#6b7280)]">(необязательно)</span></span>
            <textarea v-model.trim="line.comment" rows="2" maxlength="2000" class="storefront-control w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]" />
          </label>
        </article>
      </div>
    </div>

    <!-- Legacy vehicle lines use the same conditions surface during migration. -->
    <div v-else-if="showItemDetails && vehicles && vehicles.length > 0" class="p-3 sm:p-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg">
      <h5 class="text-sm font-medium text-[color:var(--storefront-title,#111827)] mb-2 sm:mb-3">Транспортные средства в заявке</h5>
      <div class="space-y-2 sm:space-y-3">
        <div 
          v-for="(vehicle, index) in vehicles" 
          :key="vehicleKey(vehicle, index)"
          class="p-2.5 sm:p-3 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]"
        >
          <div class="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-1 sm:gap-2">
            <div class="flex-1 min-w-0">
              <p class="font-medium text-[color:var(--storefront-text,#111827)] text-sm sm:text-base truncate">
                {{ vehicle.mark_name }} {{ vehicle.model_name }}
              </p>
              <p v-if="vehicle.group_name || vehicle.configuration_name" class="text-xs sm:text-sm text-[color:var(--storefront-text-muted,#4b5563)] truncate">
                {{ vehicle.group_name || vehicle.configuration_name }}
              </p>
              <p v-if="vehicle.quantity && vehicle.quantity > 1" class="text-xs sm:text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
                Количество: {{ vehicle.quantity }} шт.
              </p>
            </div>
            <div class="sm:text-right shrink-0">
              <p class="font-bold text-[color:var(--storefront-text-muted,#2563eb)] text-sm sm:text-base">
                {{ formatPrice(getVehicleLineTotal(vehicle)) }}
              </p>
            </div>
          </div>
          <div v-if="vehicle.comment" class="mt-2 pt-2 border-t border-[color:var(--storefront-border,#f3f4f6)]">
            <p class="text-xs sm:text-sm text-[color:var(--storefront-text,#374151)]">
              <span class="font-medium">Комментарий:</span> {{ vehicle.comment }}
            </p>
          </div>

          <div class="mt-3 pt-3 border-t border-[color:var(--storefront-border,#f3f4f6)] grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-[color:var(--storefront-label,#374151)] mb-1">
                Цель приобретения
              </label>
              <SearchableDropdown
                :model-value="selectedLeasingPurposes(vehicle)"
                @update:model-value="updateLeasingPurposes(vehicle, $event)"
                multiple
                :items="purposeOptions"
                label-key="purpose_display_name"
                value-key="purpose_name"
                placeholder="Выберите цель приобретения"
                search-placeholder="Найти цель..."
                :searchable="false"
                :allow-clear="true"
                clear-label="Не выбрано"
              />
              <textarea
                v-if="selectedLeasingPurposes(vehicle).includes('other')"
                v-model="vehicle.leasing_purpose_comment"
                rows="2"
                class="storefront-control mt-2 w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md text-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)]"
                placeholder="Укажите цель приобретения"
              />
            </div>

            <div>
              <label class="block text-xs font-medium text-[color:var(--storefront-label,#374151)] mb-1">
                Регион
              </label>
              <SearchableDropdown
                v-model="vehicle.regions"
                :items="regionOptions"
                label-key="region_label"
                value-key="region_display_name"
                :search-keys="['region_display_name', 'region_number', 'region_label']"
                placeholder="Выберите один или несколько регионов"
                search-placeholder="Найти регион..."
                :searchable="true"
                multiple
                show-select-all
                select-all-label="Выбрать все найденные регионы"
              />
              <div class="mt-2 flex flex-wrap gap-2 text-xs">
                <button
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
                  @click="selectAllRegions(vehicle)"
                >
                  Выбрать все регионы
                </button>
                <button
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:text-[color:var(--storefront-ghost-hover-foreground,#374151)]"
                  @click="clearVehicleRegions(vehicle)"
                >
                  Очистить выбор
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Leasing Conditions -->
    <div v-if="showLeasingConditions && leasingConditions" class="p-3 sm:p-4 bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] rounded-lg">
      <h5 class="text-sm font-medium text-[color:var(--storefront-title,#1e3a8a)] mb-2 sm:mb-3">Запрашиваемые условия</h5>
      <div class="space-y-2 text-xs sm:text-sm text-[color:var(--storefront-text,#1e40af)]">
        <div v-if="leasingConditions.monthlyPayment" class="pb-2 border-b border-[color:var(--storefront-border,#dbeafe)]">
          <span class="font-medium">Ежемесячный платеж:</span>
          <span class="text-base sm:text-lg font-bold text-[color:var(--storefront-text,#1e3a8a)] ml-1 sm:ml-2">{{ formatPrice(leasingConditions.monthlyPayment) }}</span>
        </div>
        
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
          <p v-if="leasingConditions.rate !== undefined">
            <span class="font-medium">Ставка удорожания:</span>
            <span class="ml-1">{{ leasingConditions.rate }}%</span>
          </p>
          <p v-if="leasingConditions.leaseTermMonths">
            <span class="font-medium">Срок:</span>
            <span class="ml-1">{{ leasingConditions.leaseTermMonths }} мес.</span>
          </p>
        </div>
        
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
          <p v-if="leasingConditions.downPaymentPercent && leasingConditions.downPayment">
            <span class="font-medium">Аванс:</span>
            <span class="ml-1">{{ leasingConditions.downPaymentPercent }}% ({{ formatPrice(leasingConditions.downPayment) }})</span>
          </p>
          <p v-if="leasingConditions.totalAmount">
            <span class="font-medium">Стоимость имущества:</span>
            <span class="ml-1">{{ formatPrice(leasingConditions.totalAmount) }}</span>
          </p>
        </div>
        
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 sm:gap-2">
          <p v-if="leasingConditions.totalCost">
            <span class="font-medium">Общая сумма выплат:</span>
            <span class="ml-1">{{ formatPrice(leasingConditions.totalCost) }}</span>
          </p>
          <p v-if="leasingConditions.totalInterest">
            <span class="font-medium">Проценты:</span>
            <span class="ml-1">{{ formatPrice(leasingConditions.totalInterest) }}</span>
          </p>
        </div>
        
        <p v-if="leasingConditions.buyoutAmount > 0">
          <span class="font-medium">Выкупная стоимость:</span>
          <span class="ml-1 text-[color:var(--storefront-text,#1e3a8a)]">{{ formatPrice(leasingConditions.buyoutAmount) }}</span>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { selectedLeasingPurposes, updateLeasingPurposes } from '~/features/checkout/utils/leasingPurposes'
import type { UUID } from '~/types/ids'
import CompanyAutocomplete from '~/components/ui/CompanyAutocomplete.vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { useCompanySelectHistory } from '~/features/auth/composables/useCompanySelectHistory'
import type { CompanyOption } from '~/features/auth/composables/useCompanySelectHistory'
import { formatCommerceMoney, multiplyMoney, normalizeMoney, sumMoney } from '~/features/commerce/money'
import type { CommerceCheckoutLine } from '~/features/commerce/types'
import type { ApplicationCompanyPayload } from '~/features/checkout/store/checkout'

interface Step1Vehicle {
  vehicle_id?: UUID
  mark_name?: string
  model_name?: string
  group_name?: string
  configuration_name?: string
  quantity?: number
  custom_price?: number | null
  discount_price?: number | null
  base_price?: number
  comment?: string
  leasing_purpose?: string | null
  leasing_purposes?: string[] | null
  leasing_purpose_comment?: string | null
  region?: string | null
  regions?: string[]
  [key: string]: unknown
}

const props = withDefaults(defineProps<{
  vehicles?: Step1Vehicle[]
  commerceItems?: CommerceCheckoutLine[]
  showItemDetails?: boolean
  showLeasingConditions?: boolean
  leasingConditions?: Record<string, any> | null
  showCompanyError?: boolean
}>(), {
  vehicles: () => [],
  commerceItems: () => [],
  showItemDetails: true,
  showLeasingConditions: false,
  leasingConditions: null,
  showCompanyError: false
})

const emit = defineEmits<{
  (e: 'company-selected', companyId: UUID | null): void
}>()

const authStore = useAuthStore()
const checkoutStore = useCheckoutStore()
const config = useRuntimeConfig()
const { formatPrice } = useFormatPrice()
const { 
  companies, 
  loadingCompanies, 
  loadCompanies, 
  loadSelectedCompany,
  selectCompany 
} = useCompanySelectHistory()

const selectedCompanyId = ref<UUID | null>(null)
const dealerCompanySearch = ref('')
const confirmedDealerCompanySearch = ref('')

const isDealer = computed(() => authStore.user?.role === 'dealer')

const getVehicleUnitPrice = (vehicle: Step1Vehicle) =>
  vehicle.custom_price ?? vehicle.discount_price ?? vehicle.base_price ?? 0

const getVehicleLineTotal = (vehicle: Step1Vehicle) =>
  getVehicleUnitPrice(vehicle) * (vehicle.quantity || 1)

const getCommerceOptionPrice = (price: unknown) => {
  if (typeof price === 'string') return normalizeMoney(price) ?? '0.00'
  return typeof price === 'number' && Number.isFinite(price) ? price.toFixed(2) : '0.00'
}

const getCommerceLineTotal = (line: CommerceCheckoutLine) => multiplyMoney(
  sumMoney([
    line.custom_price ?? line.item.price,
    ...line.equipments.map(option => getCommerceOptionPrice(option.price)),
    ...line.services.map(option => getCommerceOptionPrice(option.price)),
  ]),
  line.quantity,
)

const vehicleKey = (vehicle: Step1Vehicle, index: number) => {
  if (vehicle.vehicle_id) return vehicle.vehicle_id
  return `vehicle-${index}`
}

type LeasingPurposeOption = {
  purpose_name: string
  purpose_display_name: string
}

type LeasingRegionOption = {
  region_name: string
  region_display_name: string
  region_number: string
  region_label: string
}

const fallbackPurposeOptions: LeasingPurposeOption[] = [
  { purpose_name: 'business', purpose_display_name: 'Для предпринимательской деятельности' },
  { purpose_name: 'personal', purpose_display_name: 'Личное пользование' },
  { purpose_name: 'management', purpose_display_name: 'Для руководства' },
  { purpose_name: 'staff', purpose_display_name: 'Для служебных поездок' },
  { purpose_name: 'taxi', purpose_display_name: 'Для такси' },
  { purpose_name: 'carsharing', purpose_display_name: 'Каршеринг' },
  { purpose_name: 'special_equipment', purpose_display_name: 'Для операционной деятельности (спец. техника)' },
  { purpose_name: 'test_drive', purpose_display_name: 'Для тест-драйва' },
  { purpose_name: 'other', purpose_display_name: 'Прочее' }
]

const purposeOptions = ref<LeasingPurposeOption[]>(fallbackPurposeOptions)
const regionOptions = ref<LeasingRegionOption[]>([])

const loadLeasingDictionaries = async () => {
  try {
    const [purposes, regions] = await Promise.all([
      $fetch<{ purposes?: LeasingPurposeOption[] }>('/api/v1/applications/leasing-purposes', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      }),
      $fetch<{ regions?: Array<Omit<LeasingRegionOption, 'region_label'>> }>('/api/v1/applications/leasing-regions', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    ])
    if (purposes.purposes?.length) purposeOptions.value = purposes.purposes
    if (regions.regions?.length) {
      regionOptions.value = regions.regions.map((region) => ({
        ...region,
        region_label: `${region.region_number} — ${region.region_display_name}`,
      }))
    }
  } catch (err) {
    console.warn('Не удалось загрузить справочники цели приобретения/регионов', err)
  }
}

const normalizeVehicleRegions = (vehicle: Step1Vehicle) => {
  if (Array.isArray(vehicle.regions)) return vehicle.regions
  if (vehicle.region) return [vehicle.region]
  vehicle.regions = []
  return vehicle.regions
}

const selectAllRegions = (vehicle: Step1Vehicle) => {
  vehicle.regions = regionOptions.value.map((region) => region.region_display_name)
}

const clearVehicleRegions = (vehicle: Step1Vehicle) => {
  vehicle.regions = []
  vehicle.region = null
}

const selectAllCommerceRegions = (line: CommerceCheckoutLine): void => {
  line.regions = regionOptions.value.map((region) => region.region_display_name)
}

const validateVehicleLeasingFields = () => ({
  canProceed: true,
  messages: [],
})

watch(
  () => props.vehicles,
  (vehicles) => {
    vehicles.forEach(normalizeVehicleRegions)
  },
  { deep: true, immediate: true }
)

const formatCompanyDisplay = (company: { name: string; inn?: string | null }) =>
  `${company.name}${company.inn ? ` (ИНН: ${company.inn})` : ''}`

const dealerCompany = computed(() => {
  const storedId = checkoutStore.selectedCompanyId
  const userCompanyId = authStore.user?.company_id as UUID | undefined | null
  return companies.value.find((company) => company.id === userCompanyId)
    || companies.value.find((company) => company.id === storedId)
    || companies.value[0]
    || null
})

const isOriginalCompany = (company: ApplicationCompanyPayload) =>
  companies.value.find((original) => {
    const sameId = company.id != null && original.id === company.id
    const sameInn = !!original.inn && !!company.inn && original.inn === company.inn
    return sameId || sameInn
  }) || null

const applyDealerCompany = async (company: CompanyOption | null) => {
  const companyId = company?.id ?? null
  selectedCompanyId.value = companyId
  checkoutStore.setSelectedCompanyId(companyId)
  checkoutStore.setSelectedApplicationCompany(null)
  const displayValue = company ? formatCompanyDisplay(company) : ''
  confirmedDealerCompanySearch.value = displayValue
  dealerCompanySearch.value = displayValue
  if (companyId) {
    await selectCompany(companyId)
  }
  emit('company-selected', selectedCompanyId.value)
}

watch(dealerCompanySearch, (value) => {
  if (!isDealer.value || value === confirmedDealerCompanySearch.value) return

  selectedCompanyId.value = null
  checkoutStore.setSelectedCompanyId(null)
  checkoutStore.setSelectedApplicationCompany(null)
  emit('company-selected', null)
})

const handleCompanyChange = async () => {
  if (selectedCompanyId.value) {
    await selectCompany(selectedCompanyId.value)
  }
  checkoutStore.setSelectedApplicationCompany(null)
  emit('company-selected', selectedCompanyId.value)
}

const handleDealerCompanySelect = async (company: ApplicationCompanyPayload | null) => {
  if (!company) {
    selectedCompanyId.value = null
    checkoutStore.setSelectedCompanyId(null)
    checkoutStore.setSelectedApplicationCompany(null)
    emit('company-selected', null)
    return
  }

  const originalCompany = isOriginalCompany(company)
  const userCompanyId = authStore.user?.company_id as UUID | undefined | null
  if (originalCompany && originalCompany.id === userCompanyId) {
    await applyDealerCompany(originalCompany)
    return
  }
  if (originalCompany) {
    await applyDealerCompany(originalCompany)
    return
  }

  selectedCompanyId.value = null
  checkoutStore.setSelectedCompanyId(null)
  checkoutStore.setSelectedApplicationCompany(company)
  confirmedDealerCompanySearch.value = formatCompanyDisplay(company)
  dealerCompanySearch.value = confirmedDealerCompanySearch.value
  emit('company-selected', null)
}

onMounted(async () => {
  await loadLeasingDictionaries()
  await loadCompanies()
  await loadSelectedCompany()
  if (isDealer.value) {
    await applyDealerCompany(dealerCompany.value)
    return
  }

  selectedCompanyId.value = checkoutStore.selectedCompanyId
  checkoutStore.setSelectedApplicationCompany(null)
  emit('company-selected', selectedCompanyId.value)
})

defineExpose({
  selectedCompanyId,
  companies,
  validateVehicleLeasingFields,
})
</script>
