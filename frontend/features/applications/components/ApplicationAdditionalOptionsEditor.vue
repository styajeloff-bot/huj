<template>
  <div data-storefront-block="client.application"
    v-if="hasAdditionalOptions || canEditAdditionalOptions"
    class="mt-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4"
  >
    <div class="mb-3 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
      <h5 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">Дополнительное оборудование и услуги</h5>
      <div v-if="additionalOptionsTotal > 0" class="text-sm font-medium text-[color:var(--storefront-text,#111827)] sm:text-right">
        Сумма опций: {{ formatPrice(additionalOptionsTotal) }}
      </div>
    </div>

    <div class="grid min-w-0 gap-4 lg:grid-cols-2">
      <div class="min-w-0">
        <div class="mb-2 flex flex-wrap items-start justify-between gap-2 text-sm font-medium">
          <span class="text-[color:var(--storefront-text,#374151)]">Оборудование</span>
          <div class="flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
            <span v-if="additionalEquipmentTotal > 0" class="text-[color:var(--storefront-text,#111827)]">
              Сумма: {{ formatPrice(additionalEquipmentTotal) }}
            </span>
            <button
              v-if="canEditAdditionalOptions"
              type="button"
              class="storefront-action-ghost text-sm font-semibold text-[color:var(--storefront-ghost-foreground,#1d4ed8)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)] disabled:cursor-not-allowed disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)]"
              :disabled="submitting || !canAddEquipment"
              @click="addEquipment"
            >
              + Предложить оборудование
            </button>
          </div>
        </div>
        <p v-if="equipmentOptions.length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Не выбрано</p>
        <div v-else class="space-y-2">
          <div
            v-for="(option, optionIndex) in equipmentOptions"
            :key="'equipment-' + optionIndex + '-' + option.equipment_code"
            class="grid min-w-0 gap-2 rounded-md bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm"
          >
            <select
              v-if="isNewAdditionalOption(option)"
              :value="option.equipment_code"
              class="storefront-control select-field"
              aria-label="Название оборудования"
              :disabled="submitting"
              @change="setEquipmentCode(optionIndex, $event)"
            >
              <option value="" disabled>Выберите оборудование</option>
              <option
                v-for="catalogOption in availableEquipmentCatalog(option.equipment_code)"
                :key="catalogOption.equipment_code"
                :value="catalogOption.equipment_code"
              >
                {{ catalogOption.equipment_display_name }}
              </option>
            </select>
            <span v-else>
              <span class="block text-[color:var(--storefront-text,#1f2937)]">{{ equipmentName(option.equipment_code) }}</span>
              <span class="block text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">{{ option.equipment_code }}</span>
            </span>
            <input
              :value="option.comment ?? ''"
              type="text"
              class="storefront-control input-field"
              placeholder="Комментарий"
              :disabled="!canEditAdditionalOptions || submitting"
              @input="setEquipmentComment(optionIndex, $event)"
            />
            <input
              :value="formatAdditionalOptionPriceInput(option.price)"
              type="text"
              inputmode="decimal"
              class="storefront-control input-field tabular-nums"
              placeholder="Цена, ₽"
              :disabled="!canEditAdditionalOptions || submitting"
              @input="setEquipmentPrice(optionIndex, $event)"
            />
          </div>
        </div>
      </div>

      <div class="min-w-0">
        <div class="mb-2 flex flex-wrap items-start justify-between gap-2 text-sm font-medium">
          <span class="text-[color:var(--storefront-text,#374151)]">Услуги</span>
          <div class="flex min-w-0 flex-wrap items-center justify-end gap-x-3 gap-y-1">
            <span v-if="additionalServicesTotal > 0" class="text-[color:var(--storefront-text,#111827)]">
              Сумма: {{ formatPrice(additionalServicesTotal) }}
            </span>
            <button
              v-if="canEditAdditionalOptions"
              type="button"
              class="storefront-action-ghost text-sm font-semibold text-[color:var(--storefront-ghost-foreground,#1d4ed8)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e3a8a)] disabled:cursor-not-allowed disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)]"
              :disabled="submitting || !canAddService"
              @click="addService"
            >
              + Предложить услугу
            </button>
          </div>
        </div>
        <p v-if="serviceOptions.length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Не выбрано</p>
        <div v-else class="space-y-2">
          <div
            v-for="(option, optionIndex) in serviceOptions"
            :key="'service-' + optionIndex + '-' + option.service_code"
            class="grid min-w-0 gap-2 rounded-md bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm"
          >
            <select
              v-if="isNewAdditionalOption(option)"
              :value="option.service_code"
              class="storefront-control select-field"
              aria-label="Название услуги"
              :disabled="submitting"
              @change="setServiceCode(optionIndex, $event)"
            >
              <option value="" disabled>Выберите услугу</option>
              <option
                v-for="catalogOption in availableServiceCatalog(option.service_code)"
                :key="catalogOption.service_code"
                :value="catalogOption.service_code"
              >
                {{ catalogOption.service_display_name }}
              </option>
            </select>
            <span v-else>
              <span class="block text-[color:var(--storefront-text,#1f2937)]">{{ serviceName(option.service_code) }}</span>
              <span class="block text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">{{ option.service_code }}</span>
            </span>
            <input
              :value="option.comment ?? ''"
              type="text"
              class="storefront-control input-field"
              placeholder="Комментарий"
              :disabled="!canEditAdditionalOptions || submitting"
              @input="setServiceComment(optionIndex, $event)"
            />
            <input
              :value="formatAdditionalOptionPriceInput(option.price)"
              type="text"
              inputmode="decimal"
              class="storefront-control input-field tabular-nums"
              placeholder="Цена, ₽"
              :disabled="!canEditAdditionalOptions || submitting"
              @input="setServicePrice(optionIndex, $event)"
            />
          </div>
        </div>
      </div>
    </div>

    <div v-if="error" class="mt-4 rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
      {{ error }}
    </div>

    <div v-if="canEditAdditionalOptions" class="mt-4 flex justify-end">
      <button
        type="button"
        class="btn-primary text-sm"
        :disabled="submitting"
        @click="save"
      >
        {{ submitting ? 'Сохраняем...' : 'Сохранить изменения' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useNotificationCompanyContext } from '~/features/notifications'
import {
  createApplicationsApi,
  parseApplicationsApiError,
  type ApplicationVehicle,
  type EntityId,
} from '~/features/applications/api/applicationsApi'
import {
  formatAdditionalOptionPriceInput,
  normalizeAdditionalOptionPriceInput,
} from '~/features/applications/additionalOptionPrice'
import { useAuthStore } from '~/features/auth/store/auth'
import {
  createAdditionalOptionsApi,
  type AdditionalEquipmentCatalogItem,
  type AdditionalServiceCatalogItem,
} from '~/utils/additionalOptionsApi'

const props = defineProps<{
  applicationId: EntityId
  vehicle: ApplicationVehicle
  normalized: boolean
  afterSave: () => Promise<void>
}>()

const config = useRuntimeConfig()
const applicationsApi = createApplicationsApi(config, useNotificationCompanyContext())
const additionalOptionsApi = createAdditionalOptionsApi(config)
const authStore = useAuthStore()
const { formatPrice } = useFormatPrice()

const submitting = ref(false)
const error = ref('')
const equipmentCatalog = ref<AdditionalEquipmentCatalogItem[]>([])
const serviceCatalog = ref<AdditionalServiceCatalogItem[]>([])

const newAdditionalOptionMarker = Symbol('new-additional-option')
type NewAdditionalOption = { [newAdditionalOptionMarker]?: true }
type EquipmentOption = NonNullable<ApplicationVehicle['equipments']>[number] & NewAdditionalOption
type ServiceOption = NonNullable<ApplicationVehicle['services']>[number] & NewAdditionalOption

const canEditAdditionalOptions = computed(() => (
  props.vehicle.can_manage_whole_vehicle !== false
  && (authStore.isDealer || authStore.isDistributor || authStore.isLeasingCompany)
))
const equipmentOptions = computed<EquipmentOption[]>(() => (
  Array.isArray(props.vehicle.equipments) ? props.vehicle.equipments : []
))
const serviceOptions = computed<ServiceOption[]>(() => (
  Array.isArray(props.vehicle.services) ? props.vehicle.services : []
))
const hasAdditionalOptions = computed(() => (
  equipmentOptions.value.length > 0 || serviceOptions.value.length > 0
))

const hasAssignedOptionPrice = (price: number | string | null | undefined): boolean => {
  const value = Number(price)
  return Number.isFinite(value) && value > 0
}
const vehicleQuantity = computed(() => {
  const quantity = Number(props.vehicle.quantity || 1)
  return Number.isFinite(quantity) && quantity > 0 ? quantity : 1
})
const additionalEquipmentTotal = computed(() => equipmentOptions.value.reduce(
  (sum, option) => sum + (hasAssignedOptionPrice(option.price) ? Number(option.price) : 0),
  0,
) * vehicleQuantity.value)
const additionalServicesTotal = computed(() => serviceOptions.value.reduce(
  (sum, option) => sum + (hasAssignedOptionPrice(option.price) ? Number(option.price) : 0),
  0,
) * vehicleQuantity.value)
const additionalOptionsTotal = computed(() => (
  additionalEquipmentTotal.value + additionalServicesTotal.value
))

const equipmentName = (code: string) => (
  equipmentCatalog.value.find(option => option.equipment_code === code)?.equipment_display_name || code
)
const serviceName = (code: string) => (
  serviceCatalog.value.find(option => option.service_code === code)?.service_display_name || code
)
const isNewAdditionalOption = (option: NewAdditionalOption): boolean => (
  option[newAdditionalOptionMarker] === true
)
const availableEquipmentCatalog = (currentCode = '') => {
  const selectedCodes = new Set(
    equipmentOptions.value
      .map(option => option.equipment_code)
      .filter(code => code && code !== currentCode),
  )
  return equipmentCatalog.value.filter(option => !selectedCodes.has(option.equipment_code))
}
const availableServiceCatalog = (currentCode = '') => {
  const selectedCodes = new Set(
    serviceOptions.value
      .map(option => option.service_code)
      .filter(code => code && code !== currentCode),
  )
  return serviceCatalog.value.filter(option => !selectedCodes.has(option.service_code))
}
const canAddEquipment = computed(() => (
  !equipmentOptions.value.some(option => !option.equipment_code)
  && availableEquipmentCatalog().length > 0
))
const canAddService = computed(() => (
  !serviceOptions.value.some(option => !option.service_code)
  && availableServiceCatalog().length > 0
))

const addEquipment = () => {
  if (!canEditAdditionalOptions.value || !canAddEquipment.value) return
  if (!Array.isArray(props.vehicle.equipments)) props.vehicle.equipments = []
  props.vehicle.equipments.push({
    equipment_code: '',
    price: null,
    comment: null,
    [newAdditionalOptionMarker]: true,
  } as EquipmentOption)
}
const addService = () => {
  if (!canEditAdditionalOptions.value || !canAddService.value) return
  if (!Array.isArray(props.vehicle.services)) props.vehicle.services = []
  props.vehicle.services.push({
    service_code: '',
    price: null,
    comment: null,
    [newAdditionalOptionMarker]: true,
  } as ServiceOption)
}
const setEquipmentCode = (index: number, event: Event) => {
  const option = equipmentOptions.value[index]
  const nextCode = (event.target as HTMLSelectElement).value
  if (!option || !nextCode) return
  if (equipmentOptions.value.some((item, itemIndex) => (
    itemIndex !== index && item.equipment_code === nextCode
  ))) return
  option.equipment_code = nextCode
}
const setServiceCode = (index: number, event: Event) => {
  const option = serviceOptions.value[index]
  const nextCode = (event.target as HTMLSelectElement).value
  if (!option || !nextCode) return
  if (serviceOptions.value.some((item, itemIndex) => (
    itemIndex !== index && item.service_code === nextCode
  ))) return
  option.service_code = nextCode
}
const readInputPrice = (
  event: Event,
  currentValue: EquipmentOption['price'] | ServiceOption['price'],
) => {
  const input = event.target as HTMLInputElement
  const rawValue = input.value
  const normalized = normalizeAdditionalOptionPriceInput(rawValue)
  if (normalized === null && rawValue.trim()) {
    input.value = formatAdditionalOptionPriceInput(currentValue)
    return undefined
  }
  input.value = formatAdditionalOptionPriceInput(normalized)
  return normalized
}
const setEquipmentPrice = (index: number, event: Event) => {
  const option = equipmentOptions.value[index]
  if (!option) return
  const price = readInputPrice(event, option.price)
  if (price !== undefined) option.price = price
}
const setServicePrice = (index: number, event: Event) => {
  const option = serviceOptions.value[index]
  if (!option) return
  const price = readInputPrice(event, option.price)
  if (price !== undefined) option.price = price
}
const setEquipmentComment = (index: number, event: Event) => {
  const option = equipmentOptions.value[index]
  if (option) option.comment = (event.target as HTMLInputElement).value || null
}
const setServiceComment = (index: number, event: Event) => {
  const option = serviceOptions.value[index]
  if (option) option.comment = (event.target as HTMLInputElement).value || null
}

const save = async () => {
  if (!canEditAdditionalOptions.value || !props.normalized) return
  const applicationVehicleId = props.vehicle.id
  if (!applicationVehicleId) {
    error.value = 'Не найден идентификатор автомобиля заявки'
    return
  }

  const equipmentCodes = equipmentOptions.value.map(option => option.equipment_code)
  const serviceCodes = serviceOptions.value.map(option => option.service_code)
  if (
    equipmentCodes.some(code => !code)
    || serviceCodes.some(code => !code)
    || new Set(equipmentCodes).size !== equipmentCodes.length
    || new Set(serviceCodes).size !== serviceCodes.length
  ) {
    error.value = 'Выберите уникальные позиции оборудования и услуг'
    return
  }

  submitting.value = true
  error.value = ''
  try {
    await applicationsApi.updateAdditionalOptions(props.applicationId, {
      application_vehicle_id: applicationVehicleId,
      equipments: equipmentOptions.value.map(option => ({
        equipment_code: option.equipment_code,
        price: option.price ?? '0',
        comment: option.comment ?? null,
      })),
      services: serviceOptions.value.map(option => ({
        service_code: option.service_code,
        price: option.price ?? '0',
        comment: option.comment ?? null,
      })),
    })
    await props.afterSave()
  } catch (err) {
    error.value = parseApplicationsApiError(
      err,
      'Ошибка при сохранении изменений допов',
    ).message
  } finally {
    submitting.value = false
  }
}

const loadCatalog = async () => {
  try {
    const [equipments, services] = await Promise.all([
      additionalOptionsApi.getEquipments(),
      additionalOptionsApi.getServices(),
    ])
    equipmentCatalog.value = Array.isArray(equipments.items) ? equipments.items : []
    serviceCatalog.value = Array.isArray(services.items) ? services.items : []
  } catch {
    equipmentCatalog.value = []
    serviceCatalog.value = []
  }
}

onMounted(loadCatalog)
</script>
