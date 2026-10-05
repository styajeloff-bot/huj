<template>
  <Modal
    :show="show"
    :title="isEditing ? 'Редактировать сотрудника' : 'Создать сотрудника'"
    size="xl"
    :show-footer="false"
    @close="$emit('close')"
  >
    <div
      v-if="error"
      class="p-3 mb-4 text-sm text-[color:var(--storefront-error-text,#b91c1c)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg"
    >
      {{ error }}
    </div>

    <form @submit.prevent="handleSubmit">
      <div class="space-y-4 max-h-[75vh] overflow-y-auto px-1 pr-2">
        <!-- ФИО -->
        <div>
          <label for="emp-name" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            ФИО <span class="text-red-500">*</span>
          </label>
          <input
            id="emp-name"
            v-model="form.name"
            type="text"
            required
            placeholder="Иванов Иван Иванович"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          />
        </div>

        <!-- Телефон -->
        <div>
          <label for="emp-phone" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Телефон <span class="text-red-500">*</span>
          </label>
          <input
            id="emp-phone"
            v-model="form.phone"
            type="tel"
            required
            placeholder="+7 (999) 000-00-00"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          />
          <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            Если пользователь с таким телефоном уже есть, будет создана связь с компанией
          </p>
        </div>

        <!-- Дополнительный телефон -->
        <div>
          <label for="emp-additional-phone" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Дополнительный телефон
          </label>
          <input
            id="emp-additional-phone"
            v-model="form.additional_phone"
            type="tel"
            placeholder="+7 (999) 000-00-00"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          />
        </div>

        <!-- Компания -->
        <div>
          <label for="emp-company" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Компания <span class="text-red-500">*</span>
          </label>
          <select
            id="emp-company"
            v-model="form.company_id"
            required
            :disabled="isEditing || isCompanySelectionDisabled"
            class="select-field"
          >
            <option value="" disabled>Выберите компанию</option>
            <option
              v-for="c in companies"
              :key="c.id"
              :value="c.id"
            >
              {{ c.name }}
            </option>
          </select>
        </div>

        <!-- Роль -->
        <div>
          <label for="emp-role" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Роль <span class="text-red-500">*</span>
          </label>
          <select
            id="emp-role"
            v-model="form.role"
            required
            class="select-field"
            @change="handleRoleChange"
          >
            <option value="client">Клиент</option>
            <option value="dealer">Дилер</option>
            <option value="distributor">Дистрибьютор</option>
            <option value="leasing_company">Лизинговая компания</option>
          </select>
        </div>

        <!-- Должность -->
        <div>
          <label for="emp-position" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Должность
          </label>
          <select
            id="emp-position"
            v-model="form.position_id"
            :disabled="!isPositionApplicable"
            class="select-field"
          >
            <option value="">{{ isPositionApplicable ? 'Без должности' : 'Не применимо для выбранной роли' }}</option>
            <option
              v-for="p in selectablePositions"
              :key="p.id"
              :value="p.id"
            >
              {{ p.name }}
            </option>
          </select>
          <p v-if="!isPositionApplicable" class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            Должность доступна только для ролей «Дилер» и «Дистрибьютор»
          </p>
        </div>

        <!-- Права доступа к заявкам -->
        <div class="pt-2 border-t border-[color:var(--storefront-border,#e5e7eb)]">
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
            Действия с заявками
          </label>
          <div class="space-y-2">
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                v-model="form.can_view_applications"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
              />
              <span class="text-sm text-gray-700">Просмотр заявок</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                v-model="form.can_create_applications"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
              />
              <span class="text-sm text-gray-700">Создание заявок</span>
            </label>
          </div>
        </div>

        <!-- Разрешено создавать сотрудников (Toggle switch) -->
        <div class="flex items-center justify-between pt-2 border-t border-[color:var(--storefront-border,#e5e7eb)]">
          <div>
            <span class="text-sm font-medium text-[color:var(--storefront-label,#374151)]">
              Разрешено создавать сотрудников
            </span>
            <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ form.can_create_employees ? 'Сотрудник может создавать и настраивать других сотрудников' : 'Создание сотрудников запрещено' }}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            :aria-checked="form.can_create_employees"
            :disabled="!canManageEmployeeCreation"
            :class="[
              form.can_create_employees ? 'bg-blue-600' : 'bg-gray-200',
              !canManageEmployeeCreation ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
              'relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2'
            ]"
            @click="canManageEmployeeCreation && (form.can_create_employees = !form.can_create_employees)"
          >
            <span class="sr-only">Переключить разрешение на создание сотрудников</span>
            <span
              :class="[
                form.can_create_employees ? 'translate-x-5' : 'translate-x-0',
                'pointer-events-none relative inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out'
              ]"
            />
          </button>
        </div>

        <!-- Статус (Toggle switch) -->
        <div class="flex items-center justify-between pt-2 border-t border-[color:var(--storefront-border,#e5e7eb)]">
          <div>
            <span class="text-sm font-medium text-[color:var(--storefront-label,#374151)]">Статус сотрудника</span>
            <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ form.is_active ? 'Сотрудник активен в компании' : 'Сотрудник отключен' }}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            :aria-checked="form.is_active"
            :class="[
              form.is_active ? 'bg-blue-600' : 'bg-gray-200',
              'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2'
            ]"
            @click="form.is_active = !form.is_active"
          >
            <span class="sr-only">Переключить статус активности сотрудника</span>
            <span
              :class="[
                form.is_active ? 'translate-x-5' : 'translate-x-0',
                'pointer-events-none relative inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out'
              ]"
            />
          </button>
        </div>

        <!-- БЛОК «НАСТРОЙКА ПРАВ ДОСТУПА» -->
        <div v-if="isAccessSettingsApplicable" class="pt-4 border-t-2 border-[color:var(--storefront-border,#e5e7eb)] space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="text-base font-semibold text-gray-900">
              Настройка прав доступа
            </h3>
            <span v-if="!canEditAccessSettings" class="text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded border border-amber-200">
              Редактирование прав недоступно
            </span>
          </div>

          <div v-if="settingsLoading" class="p-4 text-center text-sm text-gray-500">
            Загрузка настроек прав...
          </div>

          <div v-else class="space-y-4">
            <!-- Дилеры (только для дистрибьютора) -->
            <AccessRuleObjectSelector
              v-if="form.role === 'distributor'"
              label="Доступ к дилерам"
              :mode="rulesState.dealer.mode"
              :mode-options="dealerModeOptions"
              :items="rulesState.dealer.items"
              :disabled="!canEditAccessSettings"
              :validation-error="rulesErrors.dealer"
              placeholder="Поиск дилеров..."
              :fetch-lookup="fetchDealersLookup"
              @update:mode="rulesState.dealer.mode = $event"
              @update:items="rulesState.dealer.items = $event"
            />

            <!-- Склады (дилера или дистрибьютора) -->
            <AccessRuleObjectSelector
              :label="form.role === 'distributor' ? 'Доступ к складам дистрибьютора' : 'Доступ к складам'"
              :mode="rulesState.warehouse.mode"
              :mode-options="standardModeOptions"
              :items="rulesState.warehouse.items"
              :disabled="!canEditAccessSettings"
              :validation-error="rulesErrors.warehouse"
              placeholder="Поиск складов..."
              :fetch-lookup="fetchWarehousesLookup"
              @update:mode="rulesState.warehouse.mode = $event"
              @update:items="rulesState.warehouse.items = $event"
            />

            <!-- Склады дилеров (только для дистрибьютора) -->
            <AccessRuleObjectSelector
              v-if="form.role === 'distributor'"
              label="Доступ к складам дилеров"
              :mode="rulesState.dealer_warehouse.mode"
              :mode-options="standardModeOptions"
              :items="rulesState.dealer_warehouse.items"
              :disabled="!canEditAccessSettings"
              :validation-error="rulesErrors.dealer_warehouse"
              placeholder="Поиск складов дилеров..."
              :fetch-lookup="fetchWarehousesLookup"
              @update:mode="rulesState.dealer_warehouse.mode = $event"
              @update:items="rulesState.dealer_warehouse.items = $event"
            />

            <!-- Марки -->
            <AccessRuleObjectSelector
              :label="form.role === 'distributor' ? 'Доступ к маркам дистрибьютора' : 'Доступ к маркам'"
              :mode="rulesState.brand.mode"
              :mode-options="standardModeOptions"
              :items="rulesState.brand.items"
              :disabled="!canEditAccessSettings"
              :validation-error="rulesErrors.brand"
              placeholder="Поиск марок..."
              :fetch-lookup="fetchBrandsLookup"
              @update:mode="rulesState.brand.mode = $event"
              @update:items="rulesState.brand.items = $event"
            />

            <!-- Заявки сотрудников -->
            <AccessRuleObjectSelector
              label="Доступ к заявкам сотрудников"
              :mode="rulesState.application_creator.mode"
              :mode-options="applicationCreatorModeOptions"
              :items="rulesState.application_creator.items"
              :disabled="!canEditAccessSettings"
              :validation-error="rulesErrors.application_creator"
              placeholder="Поиск сотрудников компании..."
              :fetch-lookup="fetchColleaguesLookup"
              @update:mode="rulesState.application_creator.mode = $event"
              @update:items="rulesState.application_creator.items = $event"
            />

            <!-- Подраздел «Доступные разделы» -->
            <div class="pt-3 border-t border-gray-200 space-y-3">
              <div class="flex items-center justify-between">
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">
                  Доступные разделы
                </label>
                <!-- Управляющий чекбокс «Все разделы» -->
                <label class="flex items-center gap-2 cursor-pointer text-sm font-medium text-blue-600 select-none">
                  <input
                    type="checkbox"
                    :checked="allSectionsChecked"
                    :disabled="!canEditAccessSettings"
                    class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4 disabled:opacity-50"
                    @change="toggleAllSections(($event.target as HTMLInputElement).checked)"
                  />
                  <span>Все разделы</span>
                </label>
              </div>

              <!-- 9 Section checkboxes grid -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                <label
                  v-for="sec in sectionDefinitions"
                  :key="sec.code"
                  :class="[
                    'flex items-center gap-2 text-sm p-2 rounded border transition-colors',
                    sectionsState[sec.code] ? 'bg-blue-50/50 border-blue-200 text-gray-900 font-medium' : 'bg-gray-50/50 border-gray-200 text-gray-700',
                    !isSectionAvailableToGranter(sec.code) || !canEditAccessSettings ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-gray-50'
                  ]"
                >
                  <input
                    v-model="sectionsState[sec.code]"
                    type="checkbox"
                    :disabled="!isSectionAvailableToGranter(sec.code) || !canEditAccessSettings"
                    class="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4 disabled:opacity-50"
                    @change="handleSectionChange"
                  />
                  <span class="flex-1 select-none">{{ sec.label }}</span>
                  <span v-if="!isSectionAvailableToGranter(sec.code)" class="text-[10px] text-gray-400">
                    (недоступен)
                  </span>
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="mt-6 flex justify-end gap-3 border-t border-[color:var(--storefront-border,#e5e7eb)] pt-4">
        <button
          type="button"
          class="btn-secondary"
          :disabled="loading"
          @click="$emit('close')"
        >
          Отмена
        </button>
        <button
          type="submit"
          :disabled="loading || !isValid"
          class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? (isEditing ? 'Сохранение...' : 'Создание...') : (isEditing ? 'Сохранить' : 'Создать') }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import Modal from '~/components/ui/Modal.vue'
import AccessRuleObjectSelector, {
  type ObjectOptionItem,
  type ModeOption,
} from './AccessRuleObjectSelector.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import type { UUID } from '~/types/ids'
import {
  createEmployee,
  updateEmployee,
  getEmployeeAccessSettings,
  updateEmployeeAccessSettings,
  lookupWarehouses,
  lookupBrands,
  lookupDealers,
  lookupColleagues,
  type EmployeeItem,
  type PositionItem,
  type AccessRuleItem,
  type SectionAccessItem,
} from '../api/employeesApi'

const props = withDefaults(
  defineProps<{
    show?: boolean
    employee?: EmployeeItem | null
    companies?: Array<{ id: UUID; name: string }>
    positions?: PositionItem[]
  }>(),
  {
    show: true,
    employee: null,
    companies: () => [],
    positions: () => [],
  },
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', employee: EmployeeItem): void
}>()

const config = useRuntimeConfig()
const authStore = useAuthStore()

const isEditing = computed(() => !!props.employee?.user_id)

const form = ref({
  name: '',
  phone: '',
  additional_phone: '',
  company_id: '' as UUID | '',
  role: 'client',
  position_id: '' as UUID | '',
  can_view_applications: true,
  can_create_applications: false,
  can_create_employees: false,
  is_active: true,
})

const loading = ref(false)
const settingsLoading = ref(false)
const error = ref('')

const isCompanySelectionDisabled = computed(() => {
  return props.companies.length <= 1
})

const isPositionApplicable = computed(() => {
  return form.value.role === 'dealer' || form.value.role === 'distributor'
})

const isAccessSettingsApplicable = computed(() => {
  return form.value.role === 'dealer' || form.value.role === 'distributor'
})

const selectablePositions = computed(() => {
  return props.positions.filter(
    (p) => p.is_active || p.id === form.value.position_id,
  )
})

// --- Permissions for granter ---
const isSelf = computed(() => {
  return isEditing.value && props.employee?.user_id === authStore.user?.id
})

const canManageEmployeeCreation = computed(() => {
  if (isSelf.value) return false
  return Boolean(authStore.isCarCraftEmployee || authStore.canCreateEmployees)
})

const canEditAccessSettings = computed(() => {
  if (isSelf.value) return false
  return Boolean(authStore.isCarCraftEmployee || authStore.canCreateEmployees)
})

// --- Object rules state ---
interface RuleSlot {
  mode: string
  items: ObjectOptionItem[]
}

const rulesState = reactive<{
  warehouse: RuleSlot
  brand: RuleSlot
  dealer: RuleSlot
  dealer_warehouse: RuleSlot
  application_creator: RuleSlot
}>({
  warehouse: { mode: 'all', items: [] },
  brand: { mode: 'all', items: [] },
  dealer: { mode: 'all', items: [] },
  dealer_warehouse: { mode: 'all', items: [] },
  application_creator: { mode: 'all', items: [] },
})

const standardModeOptions: ModeOption[] = [
  { value: 'all', label: 'Все' },
  { value: 'selected', label: 'Только выбранные' },
  { value: 'except_selected', label: 'Все, кроме выбранных' },
  { value: 'none', label: 'Нет доступа' },
]

const dealerModeOptions: ModeOption[] = [
  { value: 'all', label: 'Все дилеры' },
  { value: 'selected', label: 'Только выбранные дилеры' },
  { value: 'none', label: 'Нет доступа' },
]

const applicationCreatorModeOptions: ModeOption[] = [
  { value: 'own', label: 'Только свои заявки' },
  { value: 'all', label: 'Все заявки компании' },
  { value: 'own_and_selected', label: 'Свои и выбранных сотрудников' },
  { value: 'except_selected', label: 'Все, кроме выбранных сотрудников' },
]

// --- Sections state ---
const sectionDefinitions = [
  { code: 'applications', label: 'Заявки' },
  { code: 'warehouses', label: 'Склады' },
  { code: 'vehicle_exchange', label: 'Биржа' },
  { code: 'employees', label: 'Сотрудники' },
  { code: 'catalog_management', label: 'Управление каталогом' },
  { code: 'analytics', label: 'Аналитика' },
  { code: 'monetization_income', label: 'Монетизация (доход)' },
  { code: 'monetization_expense', label: 'Монетизация (расход)' },
  { code: 'incentive_programs', label: 'Программы стимулирования' },
] as const

const sectionsState = reactive<Record<string, boolean>>({
  applications: true,
  warehouses: true,
  vehicle_exchange: true,
  employees: true,
  catalog_management: true,
  analytics: true,
  monetization_income: true,
  monetization_expense: true,
  incentive_programs: true,
})

const granterAvailableSections = ref<string[]>([])

const isSectionAvailableToGranter = (code: string) => {
  if (authStore.isCarCraftEmployee) return true
  if (granterAvailableSections.value.length > 0) {
    return granterAvailableSections.value.includes(code)
  }
  const sa = authStore.user?.section_access
  if (sa && sa[code] === false) return false
  return true
}

const allSectionsChecked = computed(() => {
  const allowed = sectionDefinitions.filter((s) => isSectionAvailableToGranter(s.code))
  if (allowed.length === 0) return false
  return allowed.every((s) => sectionsState[s.code] === true)
})

const toggleAllSections = (checked: boolean) => {
  for (const s of sectionDefinitions) {
    if (isSectionAvailableToGranter(s.code)) {
      sectionsState[s.code] = checked
    }
  }
}

const handleSectionChange = () => {
  // Checkbox state updated via v-model
}

// --- Lookup search methods ---
const fetchWarehousesLookup = async (query: string): Promise<ObjectOptionItem[]> => {
  if (!form.value.company_id) return []
  const res = await lookupWarehouses(config, {
    company_id: form.value.company_id as UUID,
    q: query,
  })
  return res.items.map((i) => ({
    id: i.id,
    name: i.name,
    description: i.address || undefined,
  }))
}

const fetchBrandsLookup = async (query: string): Promise<ObjectOptionItem[]> => {
  if (!form.value.company_id) return []
  const res = await lookupBrands(config, {
    company_id: form.value.company_id as UUID,
    q: query,
  })
  return res.items.map((i) => ({
    id: i.id,
    name: i.name,
  }))
}

const fetchDealersLookup = async (query: string): Promise<ObjectOptionItem[]> => {
  if (!form.value.company_id) return []
  const res = await lookupDealers(config, {
    distributor_company_id: form.value.company_id as UUID,
    q: query,
  })
  return res.items.map((i) => ({
    id: i.id,
    name: i.name,
    description: i.inn ? `ИНН: ${i.inn}` : undefined,
  }))
}

const fetchColleaguesLookup = async (query: string): Promise<ObjectOptionItem[]> => {
  if (!form.value.company_id) return []
  const res = await lookupColleagues(config, {
    company_id: form.value.company_id as UUID,
    q: query,
    exclude_user_id: props.employee?.user_id,
  })
  return res.items.map((i) => ({
    id: i.id,
    name: i.name,
    description: i.phone || undefined,
  }))
}

// --- Validation ---
const rulesErrors = computed(() => {
  const errors: Record<string, string> = {}
  if (!isAccessSettingsApplicable.value) return errors

  if (rulesState.warehouse.mode === 'selected' && rulesState.warehouse.items.length === 0) {
    errors.warehouse = 'Выберите хотя бы один склад'
  }
  if (rulesState.brand.mode === 'selected' && rulesState.brand.items.length === 0) {
    errors.brand = 'Выберите хотя бы одну марку'
  }
  if (
    form.value.role === 'distributor' &&
    rulesState.dealer.mode === 'selected' &&
    rulesState.dealer.items.length === 0
  ) {
    errors.dealer = 'Выберите хотя бы одного дилера'
  }
  if (
    form.value.role === 'distributor' &&
    rulesState.dealer_warehouse.mode === 'selected' &&
    rulesState.dealer_warehouse.items.length === 0
  ) {
    errors.dealer_warehouse = 'Выберите хотя бы один склад дилера'
  }
  if (
    rulesState.application_creator.mode === 'own_and_selected' &&
    rulesState.application_creator.items.length === 0
  ) {
    errors.application_creator = 'Выберите хотя бы одного сотрудника'
  }
  return errors
})

const isValid = computed(() => {
  const hasBasic =
    form.value.name.trim().length > 0 &&
    form.value.phone.trim().length >= 6 &&
    Boolean(form.value.company_id) &&
    Boolean(form.value.role)

  if (!hasBasic) return false
  if (Object.keys(rulesErrors.value).length > 0) return false
  return true
})

const handleRoleChange = () => {
  if (!isPositionApplicable.value) {
    form.value.position_id = ''
  }
}

const normalizePhone = (value: string): string => {
  const digits = value.replace(/\D+/g, '')
  if (digits.startsWith('8') && digits.length === 11) return `+7${digits.slice(1)}`
  if (digits.startsWith('7') && digits.length === 11) return `+${digits}`
  if (digits.length === 10) return `+7${digits}`
  if (value.startsWith('+')) return value
  return digits ? `+${digits}` : ''
}

// Reset and load settings
const resetAccessSettings = () => {
  rulesState.warehouse = { mode: 'all', items: [] }
  rulesState.brand = { mode: 'all', items: [] }
  rulesState.dealer = { mode: 'all', items: [] }
  rulesState.dealer_warehouse = { mode: 'all', items: [] }
  rulesState.application_creator = { mode: 'all', items: [] }

  for (const s of sectionDefinitions) {
    sectionsState[s.code] = isSectionAvailableToGranter(s.code)
  }
}

const loadAccessSettings = async (userId: UUID, companyId: UUID) => {
  settingsLoading.value = true
  try {
    const data = await getEmployeeAccessSettings(config, userId, companyId)
    if (data.available_sections) {
      granterAvailableSections.value = data.available_sections
    }
    if (data.additional_phone) {
      form.value.additional_phone = data.additional_phone
    }
    if (data.can_create_employees !== undefined) {
      form.value.can_create_employees = Boolean(data.can_create_employees)
    }

    // Parse rules
    const rawRules = data.access_rules || (data as any).rules || []
    const parseSlot = (objType: string): RuleSlot => {
      const filtered = rawRules.filter((r: any) => r.access_object === objType)
      if (filtered.length === 0) {
        return { mode: 'all', items: [] }
      }
      const first = filtered[0]
      const items = filtered
        .filter((r: any) => r.object_id)
        .map((r: any) => ({
          id: String(r.object_id),
          name: r.object_name || String(r.object_id),
        }))
      return {
        mode: first.access_type || 'all',
        items,
      }
    }

    rulesState.warehouse = parseSlot('warehouse')
    rulesState.brand = parseSlot('brand')
    rulesState.dealer = parseSlot('dealer')
    rulesState.dealer_warehouse = parseSlot('dealer_warehouse')

    // Parse application_creator
    const creatorRules = rawRules.filter((r: any) => r.access_object === 'application_creator')
    if (creatorRules.length === 0) {
      rulesState.application_creator = { mode: 'all', items: [] }
    } else {
      const first = creatorRules[0]
      if (first.access_type === 'all') {
        rulesState.application_creator = { mode: 'all', items: [] }
      } else if (first.access_type === 'except_selected') {
        rulesState.application_creator = {
          mode: 'except_selected',
          items: creatorRules
            .filter((r: any) => r.object_id)
            .map((r: any) => ({
              id: String(r.object_id),
              name: r.object_name || String(r.object_id),
            })),
        }
      } else if (first.access_type === 'selected') {
        const others = creatorRules.filter(
          (r: any) => r.object_id && String(r.object_id) !== String(userId),
        )
        if (others.length === 0) {
          rulesState.application_creator = { mode: 'own', items: [] }
        } else {
          rulesState.application_creator = {
            mode: 'own_and_selected',
            items: others.map((r: any) => ({
              id: String(r.object_id),
              name: r.object_name || String(r.object_id),
            })),
          }
        }
      }
    }

    // Parse sections
    const secAccess = data.section_access || []
    const secDict: Record<string, boolean> = (data as any).sections || {}
    for (const item of secAccess) {
      secDict[item.section_code] = item.can_view
    }

    for (const s of sectionDefinitions) {
      if (secDict[s.code] !== undefined) {
        sectionsState[s.code] = Boolean(secDict[s.code])
      } else {
        sectionsState[s.code] = isSectionAvailableToGranter(s.code)
      }
    }
  } catch (err: any) {
    // If settings not initialized yet or not found, fallback to defaults
    resetAccessSettings()
  } finally {
    settingsLoading.value = false
  }
}

watch(
  () => [props.employee, props.companies] as const,
  async ([emp, comps]) => {
    error.value = ''
    if (emp) {
      form.value = {
        name: emp.name || '',
        phone: emp.phone || '',
        additional_phone: emp.additional_phone || '',
        company_id: emp.company_id || '',
        role: emp.role || 'client',
        position_id: emp.position_id || '',
        can_view_applications: emp.can_view_applications ?? true,
        can_create_applications: emp.can_create_applications ?? false,
        can_create_employees: emp.can_create_employees ?? false,
        is_active: emp.is_active ?? true,
      }
      if (emp.role === 'dealer' || emp.role === 'distributor') {
        await loadAccessSettings(emp.user_id, emp.company_id)
      } else {
        resetAccessSettings()
      }
    } else {
      const defaultCompanyId = comps.length === 1 ? comps[0].id : ''
      form.value = {
        name: '',
        phone: '',
        additional_phone: '',
        company_id: defaultCompanyId,
        role: 'client',
        position_id: '',
        can_view_applications: true,
        can_create_applications: false,
        can_create_employees: false,
        is_active: true,
      }
      resetAccessSettings()
    }
  },
  { immediate: true, deep: true },
)

const buildAccessRulesPayload = (targetUserId: string | null): AccessRuleItem[] => {
  const result: AccessRuleItem[] = []

  const addStandard = (objType: string, slot: RuleSlot) => {
    if (slot.mode === 'all') {
      result.push({ access_object: objType, access_type: 'all', object_id: null, object_name: null })
    } else if (slot.mode === 'none') {
      result.push({ access_object: objType, access_type: 'none', object_id: null, object_name: null })
    } else if (slot.mode === 'selected') {
      for (const item of slot.items) {
        result.push({ access_object: objType, access_type: 'selected', object_id: item.id, object_name: item.name })
      }
    } else if (slot.mode === 'except_selected') {
      if (slot.items.length === 0) {
        result.push({ access_object: objType, access_type: 'all', object_id: null, object_name: null })
      } else {
        for (const item of slot.items) {
          result.push({ access_object: objType, access_type: 'except_selected', object_id: item.id, object_name: item.name })
        }
      }
    }
  }

  addStandard('warehouse', rulesState.warehouse)
  addStandard('brand', rulesState.brand)

  if (form.value.role === 'distributor') {
    addStandard('dealer', rulesState.dealer)
    addStandard('dealer_warehouse', rulesState.dealer_warehouse)
  }

  // Application creator
  const cSlot = rulesState.application_creator
  if (cSlot.mode === 'all') {
    result.push({ access_object: 'application_creator', access_type: 'all', object_id: null, object_name: null })
  } else if (cSlot.mode === 'own') {
    if (targetUserId) {
      result.push({
        access_object: 'application_creator',
        access_type: 'selected',
        object_id: targetUserId,
        object_name: form.value.name.trim() || 'Свои заявки',
      })
    }
  } else if (cSlot.mode === 'own_and_selected') {
    if (targetUserId) {
      result.push({
        access_object: 'application_creator',
        access_type: 'selected',
        object_id: targetUserId,
        object_name: form.value.name.trim() || 'Свои заявки',
      })
    }
    for (const item of cSlot.items) {
      result.push({
        access_object: 'application_creator',
        access_type: 'selected',
        object_id: item.id,
        object_name: item.name,
      })
    }
  } else if (cSlot.mode === 'except_selected') {
    if (cSlot.items.length === 0) {
      result.push({ access_object: 'application_creator', access_type: 'all', object_id: null, object_name: null })
    } else {
      for (const item of cSlot.items) {
        result.push({
          access_object: 'application_creator',
          access_type: 'except_selected',
          object_id: item.id,
          object_name: item.name,
        })
      }
    }
  }

  return result
}

const buildSectionAccessPayload = (): SectionAccessItem[] => {
  return sectionDefinitions.map((s) => ({
    section_code: s.code,
    can_view: isSectionAvailableToGranter(s.code) ? Boolean(sectionsState[s.code]) : false,
  }))
}

const handleSubmit = async () => {
  if (!isValid.value || loading.value) return

  loading.value = true
  error.value = ''

  const finalPhone = normalizePhone(form.value.phone)
  const finalAdditionalPhone = form.value.additional_phone
    ? normalizePhone(form.value.additional_phone)
    : null

  try {
    let result: EmployeeItem
    if (isEditing.value && props.employee) {
      result = await updateEmployee(
        config,
        props.employee.user_id,
        props.employee.company_id,
        {
          name: form.value.name.trim(),
          phone: finalPhone,
          additional_phone: finalAdditionalPhone,
          company_id: form.value.company_id as UUID,
          role: form.value.role,
          position_id: isPositionApplicable.value && form.value.position_id ? form.value.position_id : null,
          can_view_applications: form.value.can_view_applications,
          can_create_applications: form.value.can_create_applications,
          can_create_employees: form.value.can_create_employees,
          is_active: form.value.is_active,
        },
      )

      if (isAccessSettingsApplicable.value && canEditAccessSettings.value) {
        await updateEmployeeAccessSettings(
          config,
          props.employee.user_id,
          props.employee.company_id,
          {
            additional_phone: finalAdditionalPhone,
            can_create_employees: form.value.can_create_employees,
            access_rules: buildAccessRulesPayload(props.employee.user_id),
            section_access: buildSectionAccessPayload(),
          },
        )
      }
    } else {
      result = await createEmployee(config, {
        name: form.value.name.trim(),
        phone: finalPhone,
        additional_phone: finalAdditionalPhone,
        company_id: form.value.company_id as UUID,
        role: form.value.role,
        position_id: isPositionApplicable.value && form.value.position_id ? form.value.position_id : null,
        can_view_applications: form.value.can_view_applications,
        can_create_applications: form.value.can_create_applications,
        can_create_employees: form.value.can_create_employees,
        is_active: form.value.is_active,
      })

      if (isAccessSettingsApplicable.value && canEditAccessSettings.value && result.user_id) {
        await updateEmployeeAccessSettings(
          config,
          result.user_id,
          result.company_id,
          {
            additional_phone: finalAdditionalPhone,
            can_create_employees: form.value.can_create_employees,
            access_rules: buildAccessRulesPayload(result.user_id),
            section_access: buildSectionAccessPayload(),
          },
        )
      }
    }

    emit('saved', result)
    emit('close')
  } catch (err: any) {
    error.value = err?.data?.detail || err?.message || 'Не удалось сохранить данные сотрудника'
  } finally {
    loading.value = false
  }
}
</script>
