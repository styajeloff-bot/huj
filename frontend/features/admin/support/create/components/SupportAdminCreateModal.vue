<template>
  <div
    v-if="show"
    class="fixed inset-0 z-50 bg-black bg-opacity-50 flex items-center justify-center p-4"
    @click.self="$emit('close')"
  >
    <div class="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-6">
      <div class="flex items-center justify-between mb-6">
        <h3 class="text-lg font-semibold">{{ titleText }}</h3>
        <button class="text-gray-500 hover:text-gray-700" @click="$emit('close')">✕</button>
      </div>

      <form @submit.prevent="submit">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium mb-1 text-gray-700">
                Название <span class="text-red-500">*</span>
              </label>
              <div :class="{ 'ring-2 ring-red-500 rounded-lg': fieldErrors.name }" class="rounded-lg">
                <input
                  v-model="form.name"
                  type="text"
                  class="input-field"
                  :class="{ 'border-red-500 focus:ring-red-500': fieldErrors.name }"
                  placeholder="Поддержка на ПВ"
                  required
                  @input="fieldErrors.name = false"
                />
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium mb-1 text-gray-700">Описание шилдика (необязательно)</label>
              <textarea
                v-model="form.comment"
                class="input-field min-h-[80px] resize-y"
                placeholder="Описание шилдика"
                rows="3"
              />
            </div>

            <div>
              <SearchableDropdown
                v-model="form.distributor_id"
                label="Дистрибьютор *"
                placeholder="Выберите дистрибьютора"
                :items="distributors"
                label-key="name"
                value-key="id"
                search-placeholder="Найти дистрибьютора..."
                :allow-clear="false"
                :error="fieldErrors.distributor_id"
                @update:modelValue="onDistributorChange"
              />
              <p v-if="distributorBrandsLoading" class="text-xs text-gray-500 mt-1">
                Загружаем марки дистрибьютора...
              </p>
              <div v-else-if="distributorBrandsError" class="mt-1 flex items-center gap-2 text-xs text-red-500">
                <span>{{ distributorBrandsError }}</span>
                <button
                  type="button"
                  class="font-medium underline underline-offset-2"
                  @click="reloadDistributorBrands"
                >
                  Повторить
                </button>
              </div>
            </div>

            <SearchableDropdown
              v-model="form.dealer_group_ids"
              label="Группы дилеров"
              placeholder="Любые группы"
              :items="dealerGroups"
              label-key="name"
              value-key="id"
              search-placeholder="Найти группу..."
              multiple
            />

            <div>
              <SearchableDropdown
                v-model="form.leasing_company_ids"
                label="Лизинговые компании"
                placeholder="Любые"
                :items="leasingCompanies"
                label-key="name"
                value-key="id"
                multiple
                search-placeholder="Найти лизинговую..."
              />
              <p class="text-xs text-gray-500 mt-1">
                Если не выбрать, заявки можно направлять в любую лизинговую.
              </p>
            </div>

            <div>
              <SearchableDropdown
                v-model="form.mark_ids"
                label="Марка *"
                placeholder="Выберите марки"
                :items="markOptions"
                label-key="display_name"
                value-key="id"
                search-placeholder="Найти марку..."
                :allow-clear="false"
                :error="fieldErrors.mark_id || Boolean(distributorMarkSelectionError)"
                :disabled="!form.distributor_id || distributorBrandsLoading || Boolean(distributorBrandsError)"
                multiple
                show-select-all
                @update:modelValue="onMarkChange"
              />
              <p v-if="distributorMarkSelectionError" class="text-xs text-red-500 mt-1">
                {{ distributorMarkSelectionError }}
              </p>
              <p
                v-else-if="form.distributor_id && !distributorBrandsLoading && !distributorBrandsError && !markOptions.length"
                class="text-xs text-gray-500 mt-1"
              >
                У дилеров выбранного дистрибьютора нет автомобилей с заполненной маркой.
              </p>
            </div>

            <SearchableDropdown
              v-model="form.model_ids"
              label="Модель (мультивыбор)"
              placeholder="Все модели"
              :items="modelOptions"
              label-key="display_name"
              value-key="id"
              search-placeholder="Найти модель..."
              :disabled="!form.mark_ids.length"
              multiple
            />

            <SearchableDropdown
              v-model="form.complectation_ids"
              label="Комплектация (опционально)"
              placeholder="Все комплектации"
              :items="trimOptions"
              label-key="trimLabel"
              value-key="id"
              search-placeholder="Найти комплектацию..."
              :disabled="!form.mark_ids.length"
              multiple
            />

            <SearchableDropdown
              v-model="form.vins"
              label="VIN (опционально)"
              placeholder="Все VIN"
              :items="vinOptions"
              label-key="label"
              value-key="vin"
              search-placeholder="Найти VIN..."
              multiple
              :remote="true"
              :remote-debounce-ms="300"
              :disabled="!form.model_ids?.length"
              @search="handleVinSearch"
            />

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Дата начала производства (опц.)</label>
                <input
                  v-model="form.production_date_from"
                  type="date"
                  class="input-field"
                  @input="fieldErrors.production_dates = false"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Дата окончания производства (опц.)</label>
                <input
                  v-model="form.production_date_to"
                  type="date"
                  class="input-field"
                  :min="form.production_date_from || undefined"
                  :class="{ 'border-red-500 focus:ring-red-500': fieldErrors.production_dates }"
                  @input="fieldErrors.production_dates = false"
                />
                <p v-if="fieldErrors.production_dates" class="text-xs text-red-500 mt-1">
                  Дата окончания производства не может быть раньше даты начала
                </p>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Дата начала поставки (опц.)</label>
                <input
                  v-model="form.delivery_date_from"
                  type="date"
                  class="input-field"
                  @input="fieldErrors.delivery_dates = false"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Дата окончания поставки (опц.)</label>
                <input
                  v-model="form.delivery_date_to"
                  type="date"
                  class="input-field"
                  :min="form.delivery_date_from || undefined"
                  :class="{ 'border-red-500 focus:ring-red-500': fieldErrors.delivery_dates }"
                  @input="fieldErrors.delivery_dates = false"
                />
                <p v-if="fieldErrors.delivery_dates" class="text-xs text-red-500 mt-1">
                  Дата окончания поставки не может быть раньше даты начала
                </p>
              </div>
            </div>

          </div>

          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Тип программы <span class="text-red-500">*</span>
              </label>
              <select v-model="form.support_type" class="select-field" required>
                <option v-for="type in supportTypes" :key="type.value" :value="type.value">
                  {{ type.label }}
                </option>
              </select>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Тип значения <span class="text-red-500">*</span>
                </label>
                <select v-model="form.support_params.value_type" class="select-field" required>
                  <option value="percent">Процент</option>
                  <option value="amount">Сумма</option>
                </select>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Значение <span class="text-red-500">*</span>
                </label>
                <input
                  v-model.number="form.support_params.value"
                  type="number"
                  class="input-field"
                  min="0"
                  step="any"
                  required
                  :class="{ 'border-red-500 focus:ring-red-500': fieldErrors.support_value }"
                  @input="fieldErrors.support_value = false"
                />
                <p v-if="fieldErrors.support_value" class="text-xs text-red-500 mt-1">Значение обязательно и должно быть больше нуля</p>
              </div>
            </div>

            <div v-if="form.support_params.value_type === 'percent'" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Сумма от
                </label>
                <input v-model.number="form.support_params.min_amount" type="number" class="input-field" min="0" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Сумма до
                </label>
                <input v-model.number="form.support_params.max_amount" type="number" class="input-field" min="0" />
              </div>
            </div>

            <div v-if="form.support_params.value_type === 'amount'" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  От %
                </label>
                <input v-model.number="form.support_params.min_percent" type="number" class="input-field" min="0" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  До %
                </label>
                <input v-model.number="form.support_params.max_percent" type="number" class="input-field" min="0" />
              </div>
            </div>

            <div v-if="form.support_type === 'leasing_interest_compensation'" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Срок компенсации (мес.)
                </label>
                <input v-model.number="form.support_params.compensation_period_months" type="number" class="input-field" min="1" />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Месяц начала
                </label>
                <input v-model.number="form.support_params.start_month" type="number" class="input-field" min="1" />
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Начало действия
                </label>
                <input
                  v-model="form.starts_at"
                  type="date"
                  class="input-field"
                  @input="fieldErrors.ends_at = false"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Конец действия
                </label>
                <input
                  v-model="form.ends_at"
                  type="date"
                  class="input-field"
                  :min="form.starts_at || undefined"
                  :class="{ 'border-red-500 focus:ring-red-500': fieldErrors.ends_at }"
                  @input="fieldErrors.ends_at = false"
                />
                <p v-if="fieldErrors.ends_at" class="text-xs text-red-500 mt-1">Дата окончания не может быть раньше даты начала</p>
              </div>
            </div>

            <label class="flex items-center gap-2 text-sm text-gray-700">
              <input v-model="form.is_active" type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
              Активна
            </label>

            <div class="rounded-lg border border-gray-200 bg-gray-50 p-3">
              <label class="flex items-center gap-2 text-sm font-medium text-gray-800">
                <input
                  v-model="form.is_compatible"
                  type="checkbox"
                  class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                Можно совмещать с другими программами
              </label>
              <p class="mt-1 text-xs text-gray-500">
                Все выбранные программы в расчёте должны быть совместимы попарно.
              </p>
              <SearchableDropdown
                v-if="form.is_compatible"
                v-model="form.compatible_support_ids"
                class="mt-3"
                label="Совместимые программы"
                placeholder="Выберите программы"
                :items="compatibleProgramOptions"
                label-key="name"
                value-key="id"
                search-placeholder="Найти программу..."
                :disabled="!hasCompatibleProgramScope"
                multiple
              />
            </div>

            <div class="space-y-2 pt-2">
              <label class="flex items-center gap-2 text-sm text-gray-700">
                <input v-model="form.show_to_leasing_company" type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                Отображать лизинговой компании
              </label>
              <label class="flex items-center gap-2 text-sm text-gray-700">
                <input v-model="form.show_to_client" type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                Отображать клиенту (калькулятор, корзина)
              </label>
            </div>

            <div class="border-t pt-4 mt-4 space-y-3">
              <h4 class="text-sm font-medium text-gray-700">Сопровождающая документация (опционально)</h4>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Комментарий к сопровождающей документации (необязательный)
                </label>
                <textarea
                  v-model="form.bill_of_lading.comment"
                  class="input-field min-h-[60px] resize-y text-sm"
                  placeholder="Документация от дистрибьютора №..."
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Дата документа</label>
                <input v-model="form.bill_of_lading.bill_date" type="date" class="input-field" />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Файлы сопровождающей документации (PDF, DOC, DOCX, PPTX, макс. 10 МБ)
                </label>
                <input
                  ref="billOfLadingFileRef"
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.pptx"
                  class="hidden"
                  @change="onBillOfLadingFilesChange"
                />
                <button
                  type="button"
                  class="inline-flex items-center px-3 py-2 border border-blue-300 text-sm font-medium rounded-md text-blue-700 bg-blue-50 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                  @click="billOfLadingFileRef && billOfLadingFileRef.click()"
                >
                  <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                  </svg>
                  Добавить файл
                </button>
              </div>

              <div v-if="form.bill_of_lading.files?.length" class="space-y-1 text-sm mt-2">
                <div
                  v-for="file in form.bill_of_lading.files"
                  :key="file.id"
                  class="flex items-center justify-between bg-gray-50 border border-gray-200 rounded px-2 py-1"
                >
                  <div class="flex flex-col">
                    <span class="text-gray-900">
                      {{ file.file_name || 'Без имени' }}
                    </span>
                    <span v-if="file.file_size" class="text-xs text-gray-500">
                      {{ Math.round(file.file_size / 1024) }} КБ
                    </span>
                  </div>
                  <button
                    type="button"
                    class="text-xs text-red-600 hover:underline"
                    @click="handleBillOfLadingFileDelete(file)"
                  >
                    Удалить
                  </button>
                </div>
              </div>

              <div v-if="billOfLadingNewFiles.length" class="space-y-1 text-sm mt-2">
                <div
                  v-for="file in billOfLadingNewFiles"
                  :key="file.name + file.size"
                  class="flex items-center justify-between bg-blue-50 border border-blue-200 rounded px-2 py-1"
                >
                  <div class="flex flex-col">
                    <span class="text-gray-900">{{ file.name }}</span>
                    <span class="text-xs text-gray-500">
                      {{ Math.round(file.size / 1024) }} КБ
                    </span>
                  </div>
                  <button
                    type="button"
                    class="text-xs text-red-600 hover:underline"
                    @click="billOfLadingNewFiles = billOfLadingNewFiles.filter((f) => f !== file)"
                  >
                    Удалить
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="mt-6">
          <CompensationFormBlock
            v-model="compensationsList"
            :base-amounts="computedBaseAmounts"
          />
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
          <button type="submit" class="btn-primary" :disabled="submitting || distributorBrandsLoading">
            <span v-if="submitting">Сохранение...</span>
            <span v-else>{{ program ? 'Сохранить' : 'Создать' }}</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  createSupportAdminApi,
  type CreateSupportPayload,
  type DistributorInventoryBrand,
} from '../../api/supportAdminApi'
import {
  emptyDistributorVehicleSelection,
  normalizeDistributorMarkIds,
} from '~/features/admin/support/distributorBrandMarks'
import {
  filterCompatibleSupportCandidates,
  hasSupportCompatibilityScope,
  pruneCompatibleSupportIds,
} from '~/features/admin/support/compatibleSupportCandidates'
import CompensationFormBlock from '~/features/compensations/components/CompensationFormBlock.vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useLodash } from '~/composables/useLodash'
import type { VehicleMark, VehicleModel, VehicleTrim, DealerGroup, SupportLeasingCompany, VinVehicle } from '~/types/admin'
import type { SupportProgram } from '~/types/admin'
import type { UUID } from '~/types/ids'
import type { PropType } from 'vue'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  program: {
    type: Object as PropType<SupportProgram | null>,
    default: null
  },
  cloneMode: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'success'])

const config = useRuntimeConfig()
const supportApi = createSupportAdminApi(config)
const { debounce } = useLodash()

const submitting = ref(false)
const error = ref('')
const success = ref('')
const compensationsList = ref<Array<{
  payer: 'distributor' | 'dealer' | 'carcraft' | 'minpromtorg' | 'client'
  recipient: 'leasing_company' | 'dealer' | 'carcraft' | 'client'
  calculation_base: 'base_price' | 'special_price' | 'dealer_cost' | 'application_price' | 'down_payment' | 'support_amount'
  calculation_base_amount: number
  value_type: 'percent' | 'sum'
  value: number
  min_amount?: number | null
  max_amount?: number | null
  min_percent?: number | null
  max_percent?: number | null
  amount: number
  payment_schedule_type?: 'fixed_date' | 'days_count' | 'weekly' | 'quarterly' | 'reporting_period'
  payment_schedule_period?: 'week' | 'month' | 'two_months' | 'quarter' | 'half_year' | 'year' | null
  payment_schedule_value?: string | null
  comment?: string
}>>([])

interface DistributorOption {
  id: UUID
  name: string
}

const marks = ref<VehicleMark[]>([])
const models = ref<VehicleModel[]>([])
const trims = ref<VehicleTrim[]>([])
const dealerGroups = ref<DealerGroup[]>([])
const distributors = ref<DistributorOption[]>([])
const distributorBrandOptions = ref<DistributorInventoryBrand[]>([])
const distributorBrandsLoading = ref(false)
const distributorBrandsError = ref('')
const distributorMarkSelectionError = ref('')
const distributorBrandsRequestId = ref(0)
const leasingCompanies = ref<SupportLeasingCompany[]>([])
const supportPrograms = ref<SupportProgram[]>([])
const vinVehicles = ref<VinVehicle[]>([])
const billOfLadingFileRef = ref<HTMLInputElement | null>(null)
const billOfLadingNewFiles = ref<File[]>([])
const billOfLadingDeletedFileIds = ref<UUID[]>([])
const fieldErrors = ref({
  name: false,
  mark_id: false,
  distributor_id: false,
  support_value: false,
  ends_at: false,
  production_dates: false,
  delivery_dates: false
})

const supportTypes = [
  { value: 'down_payment_compensation', label: 'Компенсация первого взноса' },
  { value: 'vehicle_discount_dealer_compensation', label: 'Поддержка на ТС (компенсация дилеру)' },
  { value: 'vehicle_discount_dealer_invoice', label: 'Поддержка на ТС (уменьшение счёта дилеру)' },
  { value: 'leasing_interest_compensation', label: 'Компенсация процентов по лизингу' }
]

interface BillOfLadingFormFile {
  id: UUID
  file_name?: string
  file_size?: number
  file_path?: string
  bill_date?: string
}

interface SupportForm {
  name: string
  comment: string | null
  mark_id: string | null
  mark_ids: string[]
  model_id: string | null
  model_ids: string[]
  complectation_ids: string[]
  production_date_from: string
  production_date_to: string
  delivery_date_from: string
  delivery_date_to: string
  vins: string[]
  dealer_group_ids: UUID[]
  distributor_id: UUID | null
  leasing_company_ids: UUID[]
  support_type: string
  support_params: {
    value_type: 'percent' | 'amount' | null
    value: number | null
    min_amount: number | null
    max_amount: number | null
    min_percent: number | null
    max_percent: number | null
    compensation_period_months: number | null
    start_month: number | null
  }
  starts_at: string
  ends_at: string
  is_active: boolean
  is_compatible: boolean
  compatible_support_ids: UUID[]
  show_to_leasing_company: boolean
  show_to_client: boolean
  bill_of_lading: { bill_date: string; id: UUID | null; comment: string; files: BillOfLadingFormFile[] }
}

const form = ref<SupportForm>({
  name: '',
  comment: '',
  mark_id: null,
  mark_ids: [],
  model_id: null,
  model_ids: [],
  complectation_ids: [],
  production_date_from: '',
  production_date_to: '',
  delivery_date_from: '',
  delivery_date_to: '',
  vins: [],
  dealer_group_ids: [],
  distributor_id: null,
  leasing_company_ids: [],
  support_type: 'down_payment_compensation',
  support_params: {
    value_type: 'amount',
    value: 0,
    min_amount: null,
    max_amount: null,
    min_percent: null,
    max_percent: null,
    compensation_period_months: null,
    start_month: null
  },
  starts_at: '',
  ends_at: '',
  is_active: false,
  is_compatible: false,
  compatible_support_ids: [],
  show_to_leasing_company: true,
  show_to_client: true,
  bill_of_lading: { bill_date: '', id: null, comment: '', files: [] }
})

const markOptions = computed(() => {
  const marksById = new Map(marks.value.map(mark => [mark.id, mark]))
  return distributorBrandOptions.value.map((brand) => {
    const mark = marksById.get(brand.id) || { id: brand.id, name: brand.name }
    return {
      ...mark,
      id: brand.id,
      display_name: mark.name || mark.cyrillic_name
    }
  })
})

const modelOptions = computed(() =>
  models.value.map((model) => ({
    ...model,
    id: String(model.id),
    display_name: model.name || model.cyrillic_name
  }))
)

const trimOptions = computed(() =>
  trims.value.map((t) => ({
    ...t,
    id: String(t.id),
    trimLabel: [t.name, t.trim_name].filter(Boolean).join(' — ') || t.id
  }))
)

const supportCompatibilityScope = computed(() => ({
  mark_ids: [...form.value.mark_ids],
  model_ids: [...form.value.model_ids],
  dealer_group_ids: [...form.value.dealer_group_ids],
  distributor_id: form.value.distributor_id,
  leasing_company_ids: [...form.value.leasing_company_ids]
}))

const hasCompatibleProgramScope = computed(() => (
  hasSupportCompatibilityScope(supportCompatibilityScope.value)
))

const compatibleSupportCandidates = computed(() => filterCompatibleSupportCandidates(
  supportCompatibilityScope.value,
  supportPrograms.value,
  {
    excludeProgramId: props.cloneMode ? null : (props.program?.id ?? null)
  }
))

const compatibleProgramOptions = computed(() => compatibleSupportCandidates.value
  .map(program => ({ id: program.id, name: program.name })))

const titleText = computed(() => {
  if (props.cloneMode) return 'Дублировать программу'
  if (props.program?.id) return 'Редактировать программу'
  return 'Новая программа'
})

const vinOptions = computed(() => {
  const selected = Array.isArray(form.value.vins) ? form.value.vins.filter(Boolean) : []
  const items = (vinVehicles.value || [])
    .filter(v => v?.vin)
    .map(v => ({
      vin: v.vin,
      label: `${v.vin} — ${v.mark_name || ''} ${v.model_name || ''}${v.year ? `, ${v.year}` : ''}`.trim()
    }))

  // Remote-режим: добавим выбранные VIN в список, если их нет в текущей выдаче.
  const selectedVins = new Set(items.map(i => i.vin))
  selected.forEach(vin => {
    if (vin && !selectedVins.has(vin)) {
      items.push({ vin, label: vin })
    }
  })

  return items
})

const toNullableNumber = (value: unknown) => {
  if (value === null || value === undefined || value === '') return null
  const normalized = Number(value)
  return Number.isNaN(normalized) ? null : normalized
}

const toIdString = (value: unknown): string | null => {
  if (value === null || value === undefined || value === '') return null
  return String(value)
}

const toIdStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []
  return value
    .map(toIdString)
    .filter((id): id is string => Boolean(id))
}

const resetDistributorBrandState = () => {
  distributorBrandsRequestId.value += 1
  distributorBrandOptions.value = []
  distributorBrandsLoading.value = false
  distributorBrandsError.value = ''
  distributorMarkSelectionError.value = ''
}

const clearMarkDependentSelection = () => {
  form.value.model_id = null
  form.value.model_ids = []
  form.value.complectation_ids = []
  form.value.vins = []
  models.value = []
  trims.value = []
  vinVehicles.value = []
}

const clearDistributorVehicleSelection = () => {
  Object.assign(form.value, emptyDistributorVehicleSelection())
  models.value = []
  trims.value = []
  vinVehicles.value = []
}

const loadDistributorBrands = async (
  distributorId: UUID | null,
): Promise<boolean> => {
  const requestId = ++distributorBrandsRequestId.value
  distributorBrandOptions.value = []
  distributorBrandsError.value = ''
  if (!distributorId) {
    distributorBrandsLoading.value = false
    return true
  }

  distributorBrandsLoading.value = true
  try {
    const response = await supportApi.getDistributorInventoryBrands(distributorId)
    if (
      requestId !== distributorBrandsRequestId.value
      || form.value.distributor_id !== distributorId
    ) {
      return false
    }
    distributorBrandOptions.value = response.brands
    return true
  } catch {
    if (
      requestId === distributorBrandsRequestId.value
      && form.value.distributor_id === distributorId
    ) {
      distributorBrandsError.value = 'Не удалось загрузить марки дистрибьютора'
    }
    return false
  } finally {
    if (requestId === distributorBrandsRequestId.value) {
      distributorBrandsLoading.value = false
    }
  }
}

const normalizeCurrentDistributorMarks = () => {
  const currentMarkIds = [...form.value.mark_ids]
  const normalizedMarkIds = normalizeDistributorMarkIds(
    currentMarkIds,
    distributorBrandOptions.value.map(brand => brand.id),
  )
  const selectionChanged = (
    normalizedMarkIds.length !== currentMarkIds.length
    || normalizedMarkIds.some((markId, index) => markId !== currentMarkIds[index])
  )
  form.value.mark_ids = normalizedMarkIds
  form.value.mark_id = normalizedMarkIds[0] || null
  if (selectionChanged) {
    clearMarkDependentSelection()
    distributorMarkSelectionError.value = (
      'Некоторые сохранённые марки больше не представлены в автомобилях дилеров выбранного дистрибьютора. Выберите марки заново.'
    )
  }
}

const reloadDistributorBrands = async () => {
  const loaded = await loadDistributorBrands(form.value.distributor_id)
  if (loaded) {
    normalizeCurrentDistributorMarks()
  }
}

const normalizeReferenceItem = <T extends { id?: unknown }>(item: T): T & { id: string } => {
  const normalizedId = item.id === null || item.id === undefined ? '' : String(item.id)
  return { ...item, id: normalizedId }
}

type ScheduleType =
  | 'fixed_date'
  | 'days_count'
  | 'weekly'
  | 'quarterly'
  | 'reporting_period'
type SchedulePeriod = 'week' | 'month' | 'two_months' | 'quarter' | 'half_year' | 'year'

const normalizeScheduleForForm = (
  type?: string | null,
  period?: string | null
): { type: ScheduleType; period: SchedulePeriod | null } => {
  if (type === 'reporting_period') return { type, period: (period as SchedulePeriod | null) || 'month' }
  if (type === 'fixed_date' || type === 'days_count' || type === 'weekly' || type === 'quarterly') {
    return { type, period: null }
  }
  return { type: 'days_count', period: null }
}

const schedulePayload = (compensation: {
  payment_schedule_type?: ScheduleType
  payment_schedule_period?: SchedulePeriod | null
}): { payment_schedule_type: ScheduleType; payment_schedule_period: SchedulePeriod | null } => {
  const normalized = normalizeScheduleForForm(
    compensation.payment_schedule_type || 'days_count',
    compensation.payment_schedule_period || null
  )
  if (normalized.type !== 'reporting_period') {
    return { payment_schedule_type: normalized.type, payment_schedule_period: null }
  }
  return {
    payment_schedule_type: 'reporting_period',
    payment_schedule_period: normalized.period || 'month'
  }
}

const getYearFromDate = (value: string | null | undefined) => {
  if (!value) return null
  const match = String(value).match(/^(\d{4})-/)
  if (match) return Number(match[1])
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.getFullYear()
}

const computedBaseAmounts = computed(() => ({
  base_price: 0,
  special_price: 0,
  dealer_cost: 0,
  application_price: 0,
  down_payment: 0,
  support_amount: 0
}))

const buildSupportParamsPayload = () => {
  const valueType = form.value.support_params.value_type || 'amount'
  const value = toNullableNumber(form.value.support_params.value) ?? 0
  return {
    value_type: valueType,
    value,
    min_amount: valueType === 'percent' ? toNullableNumber(form.value.support_params.min_amount) : null,
    max_amount: valueType === 'percent' ? toNullableNumber(form.value.support_params.max_amount) : null,
    min_percent: valueType === 'amount' ? toNullableNumber(form.value.support_params.min_percent) : null,
    max_percent: valueType === 'amount' ? toNullableNumber(form.value.support_params.max_percent) : null,
    compensation_period_months: toNullableNumber(form.value.support_params.compensation_period_months),
    start_month: toNullableNumber(form.value.support_params.start_month)
  }
}

const resetForm = () => {
  form.value = {
    name: '',
    comment: '',
    mark_id: null,
    mark_ids: [],
    model_id: null,
    model_ids: [],
    complectation_ids: [],
    production_date_from: '',
    production_date_to: '',
    delivery_date_from: '',
    delivery_date_to: '',
    vins: [],
    dealer_group_ids: [],
    distributor_id: null,
    leasing_company_ids: [],
    support_type: 'down_payment_compensation',
    support_params: {
      value_type: 'amount',
      value: 0,
      min_amount: null,
      max_amount: null,
      min_percent: null,
      max_percent: null,
      compensation_period_months: null,
      start_month: null
    },
    starts_at: '',
    ends_at: '',
    is_active: false,
    is_compatible: false,
    compatible_support_ids: [],
    show_to_leasing_company: true,
    show_to_client: true,
    bill_of_lading: { bill_date: '', id: null, comment: '', files: [] }
  }
  vinVehicles.value = []
  trims.value = []
  resetDistributorBrandState()
  billOfLadingNewFiles.value = []
  billOfLadingDeletedFileIds.value = []
  if (billOfLadingFileRef.value) billOfLadingFileRef.value.value = ''
  compensationsList.value = []
}

const onBillOfLadingFilesChange = (e: Event) => {
  const files = Array.from((e.target as HTMLInputElement)?.files || [])
  if (!files.length) return
  billOfLadingNewFiles.value = [...billOfLadingNewFiles.value, ...files]
  if (billOfLadingFileRef.value) {
    billOfLadingFileRef.value.value = ''
  }
}

const handleBillOfLadingFileDelete = (file: { id: UUID; file_name?: string; file_size?: number }) => {
  form.value.bill_of_lading.files = form.value.bill_of_lading.files.filter((f) => f.id !== file.id)
  if (props.program?.id && file?.id) {
    const ids = new Set(billOfLadingDeletedFileIds.value)
    ids.add(file.id)
    billOfLadingDeletedFileIds.value = Array.from(ids)
  }
}

const fetchTrims = async () => {
  const markIds = Array.isArray(form.value.mark_ids) ? form.value.mark_ids.filter(Boolean) : []
  if (!markIds.length) {
    trims.value = []
    return
  }
  try {
    const modelIds = Array.isArray(form.value.model_ids) && form.value.model_ids.length > 0 ? form.value.model_ids : undefined
    const rows = await Promise.all(markIds.map((mark) => supportApi.getTrims({ mark, models: modelIds })))
    const byId = new Map<string, VehicleTrim>()
    rows.flat().forEach((trim) => byId.set(String(trim.id), trim))
    trims.value = Array.from(byId.values())
  } catch {
    trims.value = []
  }
}

watch(() => props.show, async (isOpen) => {
  if (isOpen) {
    error.value = ''
    success.value = ''
    fieldErrors.value = {
      name: false,
      mark_id: false,
      distributor_id: false,
      support_value: false,
      ends_at: false,
      production_dates: false,
      delivery_dates: false
    }
    models.value = []
    vinVehicles.value = []
    resetDistributorBrandState()

    // Марки только с VIN (specialOffer=true на бэкенде)
    try {
      const marksData = await supportApi.getMarks({ specialOffer: 'true' }) as VehicleMark[] | { data: VehicleMark[] }
      marks.value = Array.isArray(marksData) ? marksData : (marksData?.data ? marksData.data : [])
    } catch {
      marks.value = []
    }

    try {
      const [dealerGroupsData, distributorsData, leasingData, supportProgramsData] = await Promise.all([
        supportApi.getDealerGroups(),
        supportApi.getDistributors(),
        supportApi.getLeasingCompanies(),
        supportApi.getSupportPrograms({ limit: '200' })
      ])

      dealerGroups.value = (dealerGroupsData.dealer_groups || []).map(normalizeReferenceItem)
      distributors.value = (distributorsData.distributors || []).map(normalizeReferenceItem)
      leasingCompanies.value = (leasingData.companies || []).map(normalizeReferenceItem)
      supportPrograms.value = supportProgramsData.items
      const supportProgramPages = Number(supportProgramsData.pagination?.pages || 1)
      for (let page = 2; page <= supportProgramPages; page += 1) {
        const nextPage = await supportApi.getSupportPrograms({ limit: '200', page: String(page) })
        supportPrograms.value.push(...nextPage.items)
      }

      // Редактирование или клонирование — заполняем форму данными программы
      if (props.program) {
        const modelIds = Array.isArray(props.program.model_ids) && props.program.model_ids.length > 0
          ? toIdStringArray(props.program.model_ids)
          : toIdStringArray([props.program.model_id])
        const markIds = Array.isArray(props.program.mark_ids) && props.program.mark_ids.length > 0
          ? toIdStringArray(props.program.mark_ids)
          : toIdStringArray([props.program.mark_id])
        form.value = {
          name: props.program.name || '',
          comment: props.program.comment ?? '',
          mark_id: toIdString(props.program.mark_id),
          mark_ids: markIds,
          model_id: toIdString(props.program.model_id),
          model_ids: modelIds,
          complectation_ids: toIdStringArray(props.program.complectation_ids),
          production_date_from: props.program.production_date_from
            ? String(props.program.production_date_from).slice(0, 10)
            : (props.program.production_year_from ? `${props.program.production_year_from}-01-01` : ''),
          production_date_to: props.program.production_date_to
            ? String(props.program.production_date_to).slice(0, 10)
            : (props.program.production_year_to ? `${props.program.production_year_to}-12-31` : ''),
          delivery_date_from: props.program.delivery_date_from
            ? String(props.program.delivery_date_from).slice(0, 10)
            : '',
          delivery_date_to: props.program.delivery_date_to
            ? String(props.program.delivery_date_to).slice(0, 10)
            : '',
          vins: Array.isArray(props.program.vins) ? props.program.vins.filter(Boolean).map(String) : (props.program.vin ? [String(props.program.vin)] : []),
          dealer_group_ids: [...(props.program.dealer_group_ids ?? [])],
          distributor_id: props.program.distributor_ids?.[0] ?? null,
          leasing_company_ids: [...(props.program.leasing_company_ids ?? [])],
          support_type: props.program.support_type || 'down_payment_compensation',
          support_params: {
            value_type: String(props.program.support_params?.value_type || '') === 'sum'
              ? 'amount'
              : (props.program.support_params?.value_type || 'amount'),
            value: props.program.support_params?.value ?? null,
            min_amount: props.program.support_params?.min_amount || null,
            max_amount: props.program.support_params?.max_amount || null,
            min_percent: props.program.support_params?.min_percent || null,
            max_percent: props.program.support_params?.max_percent || null,
            compensation_period_months: props.program.support_params?.compensation_period_months || null,
            start_month: props.program.support_params?.start_month || null
          },
          starts_at: props.program.starts_at ? String(props.program.starts_at).slice(0, 10) : '',
          ends_at: props.program.ends_at ? String(props.program.ends_at).slice(0, 10) : '',
          is_active: props.cloneMode ? false : (props.program.is_active !== undefined ? props.program.is_active : false),
          is_compatible: props.program.is_compatible === true,
          compatible_support_ids: [...(props.program.compatible_support_ids ?? [])],
          show_to_leasing_company: props.program.show_to_leasing_company !== false,
          show_to_client: props.program.show_to_client !== false,
          bill_of_lading: {
            bill_date: props.program.bill_of_lading?.bill_date ? String(props.program.bill_of_lading.bill_date).slice(0, 10) : '',
            id: props.program.bill_of_lading?.id ?? null,
            comment: props.program.bill_of_lading?.comment || '',
            files: Array.isArray(props.program.bill_of_lading?.files)
              ? (props.program.bill_of_lading.files as BillOfLadingFormFile[])
              : []
          }
        }
        compensationsList.value = (props.program.compensation_templates || []).map((template) => {
          const schedule = normalizeScheduleForForm(
            template.payment_schedule_type,
            template.payment_schedule_period
          )
          return {
            payer: template.payer,
            recipient: template.recipient,
            calculation_base: template.calculation_base,
            calculation_base_amount: computedBaseAmounts.value[template.calculation_base] || 0,
            value_type: template.value_type,
            value: Number(template.value) || 0,
            min_amount: template.min_amount ?? null,
            max_amount: template.max_amount ?? null,
            min_percent: template.min_percent ?? null,
            max_percent: template.max_percent ?? null,
            amount: 0,
            payment_schedule_type: schedule.type,
            payment_schedule_period: schedule.period,
            payment_schedule_value: template.payment_schedule_value || null,
            comment: template.comment || ''
          }
        })

        const distributorBrandsLoaded = await loadDistributorBrands(form.value.distributor_id)
        if (distributorBrandsLoaded) {
          normalizeCurrentDistributorMarks()
        }

        if (form.value.mark_ids.length) {
          const rows = await Promise.all(form.value.mark_ids.map((mark) => supportApi.getModels(mark)))
          const byId = new Map<string, VehicleModel>()
          rows.flat().forEach((model) => byId.set(String(model.id), normalizeReferenceItem(model)))
          models.value = Array.from(byId.values())
          await fetchTrims()
          if (form.value.model_ids?.length || form.value.model_id) {
            await fetchVinVehicles('')
          }
        }
      }
    } catch {
      error.value = 'Не удалось загрузить справочники для формы'
    }
  } else {
    resetForm()
  }
}, { immediate: true })

const fetchVinVehicles = async (search = '') => {
  const modelIds = Array.isArray(form.value.model_ids) ? form.value.model_ids.filter(Boolean) : []
  const effectiveModelIds = modelIds.length > 0
    ? modelIds
    : (form.value.model_id ? [form.value.model_id] : [])
  const markIds = Array.isArray(form.value.mark_ids) ? form.value.mark_ids.filter(Boolean) : []
  if (!markIds.length || !effectiveModelIds.length) {
    vinVehicles.value = []
    return
  }
  const complectationIds = Array.isArray(form.value.complectation_ids) ? form.value.complectation_ids.filter(Boolean) : []
  const productionYearFrom = getYearFromDate(form.value.production_date_from)
  const productionYearTo = getYearFromDate(form.value.production_date_to)
  const buildParams = (mark: string, model: string) => {
    const params = new URLSearchParams({
      page: '1',
      limit: '200',
      mark,
      model
    })
    params.append('mark_ids', markIds.join(','))
    params.append('model_ids', effectiveModelIds.join(','))
    if (complectationIds.length > 0) {
      params.append('complectation_ids', complectationIds.join(','))
    }
    if (productionYearFrom != null) {
      params.append('production_year_from', String(productionYearFrom))
    }
    if (productionYearTo != null) {
      params.append('production_year_to', String(productionYearTo))
    }
    if (search) params.append('search', search)
    return params
  }

  try {
    const responses = await Promise.all(
      markIds.flatMap((mark) =>
        effectiveModelIds.map((model) =>
          $fetch(`/api/v1/admin/vehicles/for-warehouse?${buildParams(mark, model).toString()}`, {
            baseURL: config.public.apiBase,
            credentials: 'include'
          })
        )
      )
    )
    const byVin = new Map<string, VinVehicle>()
    responses.forEach((response) => {
      ((response as { vehicles?: VinVehicle[] })?.vehicles || []).forEach((vehicle) => {
        if (vehicle.vin) byVin.set(vehicle.vin, vehicle)
      })
    })
    vinVehicles.value = Array.from(byVin.values())
  } catch {
    vinVehicles.value = []
  }
}

const debouncedVinSearch = debounce((q: string) => {
  fetchVinVehicles(q)
}, 300)

const handleVinSearch = (q: string) => {
  debouncedVinSearch(q || '')
}

const onDistributorChange = async (distributorId: UUID | null) => {
  form.value.distributor_id = distributorId
  fieldErrors.value.distributor_id = false
  distributorMarkSelectionError.value = ''
  clearDistributorVehicleSelection()
  await loadDistributorBrands(distributorId)
}

const onMarkChange = async () => {
  fieldErrors.value.mark_id = false
  distributorMarkSelectionError.value = ''
  form.value.mark_id = form.value.mark_ids[0] || null
  clearMarkDependentSelection()
  if (!form.value.mark_ids.length) {
    return
  }
  try {
    const rows = await Promise.all(form.value.mark_ids.map((mark) => supportApi.getModels(mark)))
    const byId = new Map<string, VehicleModel>()
    rows.flat().forEach((model) => byId.set(String(model.id), normalizeReferenceItem(model)))
    models.value = Array.from(byId.values())
    await fetchTrims()
  } catch {
    models.value = []
  }
}

watch(() => form.value.model_ids, async (newIds) => {
  form.value.vins = []
  vinVehicles.value = []
  await fetchTrims()
  if (Array.isArray(newIds) && newIds.length > 0) {
    await fetchVinVehicles('')
  }
}, { deep: true })

watch(
  () => [form.value.complectation_ids, form.value.production_date_from, form.value.production_date_to],
  async () => {
    form.value.vins = []
    vinVehicles.value = []
    if (Array.isArray(form.value.model_ids) && form.value.model_ids.length > 0) {
      await fetchVinVehicles('')
    }
  },
  { deep: true }
)

watch(() => form.value.is_compatible, (isCompatible) => {
  if (!isCompatible) form.value.compatible_support_ids = []
})

watch(supportCompatibilityScope, (scope) => {
  if (!hasSupportCompatibilityScope(scope)) {
    form.value.compatible_support_ids = []
    return
  }
  form.value.compatible_support_ids = pruneCompatibleSupportIds(
    form.value.compatible_support_ids,
    compatibleSupportCandidates.value
  )
}, { deep: true })

const submit = async () => {
  if (submitting.value || distributorBrandsLoading.value) return
  error.value = ''
  success.value = ''
  fieldErrors.value = {
    name: false,
    mark_id: false,
    distributor_id: false,
    support_value: false,
    ends_at: false,
    production_dates: false,
    delivery_dates: false
  }
  submitting.value = true

  try {
    const missing = []
    if (!form.value.name || !String(form.value.name).trim()) {
      fieldErrors.value.name = true
      missing.push('Название')
    }
    if (distributorBrandsError.value) {
      fieldErrors.value.mark_id = true
      missing.push('Марки дистрибьютора (повторите загрузку)')
    } else if (distributorMarkSelectionError.value) {
      fieldErrors.value.mark_id = true
      missing.push('Марка (выберите заново)')
    } else if (!form.value.mark_ids.length) {
      fieldErrors.value.mark_id = true
      missing.push('Марка')
    }
    if (!form.value.distributor_id) {
      fieldErrors.value.distributor_id = true
      missing.push('Дистрибьютор')
    }
    const supportValue = toNullableNumber(form.value.support_params.value)
    if (supportValue === null || supportValue <= 0) {
      fieldErrors.value.support_value = true
      missing.push('Значение поддержки')
    }
    compensationsList.value.forEach((compensation, index) => {
      const compensationValue = toNullableNumber(compensation.value)
      if (compensationValue === null || compensationValue <= 0) {
        missing.push(`Компенсация ${index + 1}: значение должно быть больше нуля`)
      }
    })
    if (missing.length > 0) {
      throw new Error(`Заполните обязательные поля: ${missing.join(', ')}`)
    }

    const startsAt = form.value.starts_at ? String(form.value.starts_at).trim() : ''
    const endsAt = form.value.ends_at ? String(form.value.ends_at).trim() : ''
    if (endsAt && startsAt && endsAt < startsAt) {
      fieldErrors.value.ends_at = true
      throw new Error('Дата окончания не может быть раньше даты начала')
    }

    const productionFrom = form.value.production_date_from ? String(form.value.production_date_from).trim() : ''
    const productionTo = form.value.production_date_to ? String(form.value.production_date_to).trim() : ''
    if (productionTo && productionFrom && productionTo < productionFrom) {
      fieldErrors.value.production_dates = true
      throw new Error('Дата окончания производства не может быть раньше даты начала')
    }

    const deliveryFrom = form.value.delivery_date_from ? String(form.value.delivery_date_from).trim() : ''
    const deliveryTo = form.value.delivery_date_to ? String(form.value.delivery_date_to).trim() : ''
    if (deliveryTo && deliveryFrom && deliveryTo < deliveryFrom) {
      fieldErrors.value.delivery_dates = true
      throw new Error('Дата окончания поставки не может быть раньше даты начала')
    }

    const vinsArray = Array.isArray(form.value.vins) ? form.value.vins.filter(Boolean) : []
    const vinValue = vinsArray.length > 0 ? vinsArray[0] : null
    const markIds = Array.isArray(form.value.mark_ids) ? form.value.mark_ids.filter(Boolean) : []
    const distributorId = form.value.distributor_id
    const distributorIds = distributorId ? [distributorId] : []
    const modelIds = Array.isArray(form.value.model_ids) && form.value.model_ids.length > 0 ? form.value.model_ids : undefined
    const firstModelId = modelIds?.[0] || form.value.model_id || null
    const productionYearFrom = getYearFromDate(productionFrom)
    const productionYearTo = getYearFromDate(productionTo)
    const complectationIds = Array.isArray(form.value.complectation_ids)
      ? form.value.complectation_ids.filter(Boolean).map(String)
      : []
    const payload: CreateSupportPayload = {
      name: form.value.name,
      comment: form.value.comment ? String(form.value.comment).trim() || null : null,
      mark_id: markIds[0] || '',
      mark_ids: markIds,
      model_id: firstModelId,
      model_ids: modelIds,
      complectation_ids: complectationIds,
      production_date_from: form.value.production_date_from || null,
      production_date_to: form.value.production_date_to || null,
      production_year_from: productionYearFrom,
      production_year_to: productionYearTo,
      delivery_date_from: form.value.delivery_date_from || null,
      delivery_date_to: form.value.delivery_date_to || null,
      vin: vinValue,
      vins: vinsArray,
      dealer_group_ids: form.value.dealer_group_ids || [],
      distributor_id: distributorId,
      distributor_ids: distributorIds,
      leasing_company_ids: form.value.leasing_company_ids || [],
      compensation_templates: compensationsList.value.map((c) => {
        const schedule = schedulePayload(c)
        return {
          payer: c.payer,
          recipient: c.recipient,
          calculation_base: c.calculation_base,
          value_type: c.value_type,
          value: c.value,
          min_amount: c.min_amount || null,
          max_amount: c.max_amount || null,
          min_percent: c.min_percent || null,
          max_percent: c.max_percent || null,
          payment_schedule_type: schedule.payment_schedule_type,
          payment_schedule_period: schedule.payment_schedule_period,
          payment_schedule_value: c.payment_schedule_value || null,
          comment: c.comment || ''
        }
      }),
      support_type: form.value.support_type,
      support_params: buildSupportParamsPayload(),
      starts_at: form.value.starts_at || null,
      ends_at: form.value.ends_at || null,
      is_active: form.value.is_active,
      is_compatible: form.value.is_compatible,
      compatible_support_ids: form.value.is_compatible && hasCompatibleProgramScope.value
        ? [...form.value.compatible_support_ids]
        : [],
      show_to_leasing_company: form.value.show_to_leasing_company !== false,
      show_to_client: form.value.show_to_client !== false
    }

    const isEdit = !!props.program?.id

    if (isEdit) {
      await supportApi.updateSupportProgram(props.program.id, payload)

      // Новые файлы сопровождающей документации
      if (billOfLadingNewFiles.value.length) {
        for (const file of billOfLadingNewFiles.value) {
          await supportApi.uploadBillOfLading(
            props.program.id,
            file,
            form.value.bill_of_lading?.bill_date || null,
            form.value.bill_of_lading.comment || null
          )
        }
      }

      // Удаление файлов, помеченных к удалению
      if (billOfLadingDeletedFileIds.value.length) {
        for (const fileId of billOfLadingDeletedFileIds.value) {
          await supportApi.deleteBillOfLadingFile(props.program.id, fileId)
        }
      }

      success.value = 'Программа успешно обновлена'
    } else {
      const result = await supportApi.createSupportProgram(payload)
      const createdSupportProgramId = result?.support_program?.id
      if (createdSupportProgramId && billOfLadingNewFiles.value.length) {
        for (const file of billOfLadingNewFiles.value) {
          await supportApi.uploadBillOfLading(
            createdSupportProgramId,
            file,
            form.value.bill_of_lading?.bill_date || null,
            form.value.bill_of_lading.comment || null
          )
        }
      }

      success.value = 'Программа успешно создана'
      resetForm()
    }

    emit('success')
    setTimeout(() => {
      emit('close')
    }, 1500)
  } catch (err: unknown) {
    const e = err as { data?: { detail?: string; error?: string }; message?: string }
    error.value = e?.data?.detail || e?.data?.error || e?.message || (props.program?.id ? 'Ошибка при обновлении поддержки' : 'Ошибка при создании поддержки')
  } finally {
    submitting.value = false
  }
}
</script>
