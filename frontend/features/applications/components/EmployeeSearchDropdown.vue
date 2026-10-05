<template>
  <div data-storefront-block="client.application" ref="root" class="relative">
    <label class="mb-1 block text-sm font-medium text-[color:var(--storefront-label,#374151)]">{{ label }}</label>
    <button
      type="button"
      class="storefront-action-secondary flex w-full items-center justify-between gap-3 rounded-lg border border-[color:var(--storefront-secondary-border,#d1d5db)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-2 text-left text-sm hover:border-[color:var(--storefront-secondary-hover-border,#60a5fa)] disabled:cursor-not-allowed disabled:bg-[color:rgb(var(--storefront-secondary-disabled-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
      :disabled="disabled || saving"
      :aria-expanded="open"
      @click="toggleDropdown"
    >
      <span class="min-w-0">
        <span class="block truncate font-medium text-[color:var(--storefront-secondary-foreground,#111827)]">{{ selectedLabel }}</span>
        <span v-if="selectedDetails" class="block truncate text-xs text-[color:var(--storefront-secondary-foreground,#6b7280)]">
          {{ selectedDetails }}
        </span>
      </span>
      <span v-if="saving" class="h-4 w-4 flex-none animate-spin rounded-full border-b-2 border-[color:var(--storefront-secondary-border,#2563eb)]" />
      <svg
        v-else
        class="h-4 w-4 flex-none text-[color:var(--storefront-secondary-icon,#6b7280)] transition-transform"
        :class="{ 'rotate-180': open }"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m19 9-7 7-7-7" />
      </svg>
    </button>

    <div
      v-if="open"
      class="absolute z-30 mt-1 w-full overflow-hidden rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-xl"
      role="listbox"
    >
      <div class="border-b border-[color:var(--storefront-border,#f3f4f6)] p-2">
        <input
          ref="searchInput"
          v-model="searchQuery"
          type="text"
          class="storefront-control input-field"
          placeholder="Поиск по имени или телефону"
          autocomplete="off"
          @keydown.escape.prevent="closeDropdown"
        />
      </div>

      <div class="max-h-64 overflow-y-auto py-1">
        <div v-if="loading" class="px-3 py-5 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
          Ищем сотрудников...
        </div>
        <div v-else-if="searchError" class="px-3 py-4 text-sm text-[color:var(--storefront-error-text,#b91c1c)]" role="alert">
          <p>{{ searchError }}</p>
          <button type="button" class="storefront-action-ghost mt-2 font-medium underline" @click="loadEmployees(searchQuery)">
            Повторить
          </button>
        </div>
        <template v-else>
          <button
            type="button"
            class="w-full px-3 py-2 text-left text-sm hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]"
            :class="{ 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]': !modelValue }"
            role="option"
            :aria-selected="!modelValue"
            @click="selectEmployee(null)"
          >
            <span class="block font-medium text-[color:var(--storefront-primary-foreground,#1f2937)]">Не назначен</span>
          </button>
          <button
            v-for="employee in employees"
            :key="employee.id"
            type="button"
            class="w-full px-3 py-2 text-left text-sm hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] disabled:cursor-not-allowed disabled:bg-[color:rgb(var(--storefront-primary-disabled-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-60 disabled:hover:bg-[color:rgb(var(--storefront-primary-disabled-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
            :class="{ 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]': employee.id === modelValue?.id }"
            :disabled="isEmployeeExcluded(employee)"
            role="option"
            :aria-selected="employee.id === modelValue?.id"
            :aria-disabled="isEmployeeExcluded(employee)"
            @click="selectEmployee(employee)"
          >
            <span class="flex flex-wrap items-center justify-between gap-2">
              <span class="font-medium text-[color:var(--storefront-primary-foreground,#111827)]">{{ employeeName(employee) }}</span>
              <span
                v-if="isEmployeeExcluded(employee)"
                class="rounded-full bg-[color:rgb(var(--storefront-primary-rgb,254_243_199)/var(--tw-bg-opacity,1))] px-2 py-0.5 text-xs font-medium text-[color:var(--storefront-primary-foreground,#92400e)]"
              >
                Уже выбран как {{ excludedFieldLabel }}
              </span>
            </span>
            <span v-if="employeeDetails(employee)" class="block text-xs text-[color:var(--storefront-primary-foreground,#6b7280)]">
              {{ employeeDetails(employee) }}
            </span>
          </button>
          <div v-if="employees.length === 0" class="px-3 py-5 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
            Сотрудники не найдены
          </div>
        </template>
      </div>
    </div>

    <p v-if="excludedEmployeeId" class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
      {{ exclusionHint }}
    </p>
    <p v-if="saveError" class="mt-1 text-sm text-[color:var(--storefront-error-text,#b91c1c)]" role="alert">{{ saveError }}</p>
  </div>
</template>

<script setup lang="ts">
import { useNotificationCompanyContext } from '~/features/notifications'
import {
  createApplicationsApi,
  parseApplicationsApiError,
  type ApplicationVehicle,
  type AssignedEmployee,
  type EmployeeOption,
  type EntityId,
} from '~/features/applications/api/applicationsApi'

type EmployeeField = 'primary_employee_id' | 'additional_employee_id'

const props = withDefaults(defineProps<{
  applicationId: EntityId
  applicationVehicleId: EntityId
  field: EmployeeField
  label: string
  modelValue: AssignedEmployee | null
  excludedEmployeeId?: EntityId | null
  excludedEmployeeName?: string | null
  disabled?: boolean
}>(), {
  excludedEmployeeId: null,
  excludedEmployeeName: null,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [employee: AssignedEmployee | null]
  saved: [applicationVehicle: ApplicationVehicle]
}>()

const config = useRuntimeConfig()
const applicationsApi = createApplicationsApi(config, useNotificationCompanyContext())

const root = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const open = ref(false)
const searchQuery = ref('')
const employees = ref<EmployeeOption[]>([])
const loading = ref(false)
const saving = ref(false)
const searchError = ref('')
const saveError = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let searchRequestSequence = 0

const employeeName = (employee: AssignedEmployee) =>
  employee.name?.trim() || employee.phone?.trim() || 'Сотрудник'

const employeeDetails = (employee: AssignedEmployee) =>
  [employee.phone, employee.sub_role].filter(Boolean).join(' · ')

const selectedLabel = computed(() =>
  props.modelValue ? employeeName(props.modelValue) : 'Не назначен',
)

const selectedDetails = computed(() =>
  props.modelValue ? employeeDetails(props.modelValue) : '',
)

const excludedFieldLabel = computed(() =>
  props.field === 'primary_employee_id'
    ? 'дополнительный сотрудник'
    : 'основной сотрудник',
)

const exclusionHint = computed(() => {
  const employeeLabel = props.excludedEmployeeName?.trim() || 'Этот сотрудник'
  return `${employeeLabel} уже выбран как ${excludedFieldLabel.value} и недоступен в этом списке.`
})

const isEmployeeExcluded = (employee: AssignedEmployee) =>
  Boolean(
    props.excludedEmployeeId
    && employee.id === props.excludedEmployeeId,
  )

const loadEmployees = async (query: string) => {
  const requestSequence = ++searchRequestSequence
  loading.value = true
  searchError.value = ''
  try {
    const response = await applicationsApi.searchApplicationVehicleEmployees(
      props.applicationId,
      props.applicationVehicleId,
      query.trim(),
      20,
    )
    if (requestSequence === searchRequestSequence) {
      employees.value = response.employees
    }
  } catch (error) {
    if (requestSequence === searchRequestSequence) {
      employees.value = []
      searchError.value = parseApplicationsApiError(
        error,
        'Не удалось найти сотрудников',
      ).message
    }
  } finally {
    if (requestSequence === searchRequestSequence) {
      loading.value = false
    }
  }
}

const resetSearchState = () => {
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  searchRequestSequence += 1
  searchQuery.value = ''
  employees.value = []
  loading.value = false
  searchError.value = ''
  saveError.value = ''
}

const toggleDropdown = async () => {
  if (props.disabled || saving.value) return
  if (open.value) {
    closeDropdown()
    return
  }

  resetSearchState()
  await nextTick()
  open.value = true
  void loadEmployees('')
  nextTick(() => searchInput.value?.focus())
}

const closeDropdown = () => {
  open.value = false
  resetSearchState()
}

const selectEmployee = async (employee: EmployeeOption | null) => {
  if (employee && isEmployeeExcluded(employee)) {
    saveError.value = exclusionHint.value
    return
  }

  saving.value = true
  saveError.value = ''
  const employeeId = employee?.id ?? null
  const body = props.field === 'primary_employee_id'
    ? { primary_employee_id: employeeId }
    : { additional_employee_id: employeeId }

  try {
    const response = await applicationsApi.updateApplicationVehicleEmployees(
      props.applicationId,
      props.applicationVehicleId,
      body,
    )
    const assignedEmployee = props.field === 'primary_employee_id'
      ? response.application_vehicle.primary_employee ?? employee
      : response.application_vehicle.additional_employee ?? employee
    emit('update:modelValue', assignedEmployee)
    emit('saved', response.application_vehicle)
    closeDropdown()
  } catch (error) {
    saveError.value = parseApplicationsApiError(
      error,
      'Не удалось назначить сотрудника',
    ).message
  } finally {
    saving.value = false
  }
}

const onDocumentClick = (event: MouseEvent) => {
  if (!root.value?.contains(event.target as Node)) {
    closeDropdown()
  }
}

watch(searchQuery, (query) => {
  if (!open.value) return
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    void loadEmployees(query)
  }, 300)
})

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  if (debounceTimer) clearTimeout(debounceTimer)
  searchRequestSequence += 1
})
</script>
