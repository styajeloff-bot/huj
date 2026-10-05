<template>
  <Modal
    :show="true"
    :title="isEditing ? 'Редактировать склад' : 'Создать склад'"
    size="lg"
    :closable="!submitting"
    :close-on-overlay="!submitting"
    @close="$emit('close')"
  >
      <form ref="dropdownTarget" class="space-y-4" @submit.prevent="handleSubmit">
        <!-- Название склада -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Название склада <span class="text-red-500">*</span>
          </label>
          <input
            v-model="form.name"
            type="text"
            class="input-field"
            placeholder="Например: Центральный склад ТС"
            required
          />
        </div>

        <!-- Компания-владелец -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Компания-владелец <span class="text-red-500">*</span>
          </label>
          <SearchableDropdown
            v-model="form.owner_company_id"
            placeholder="Выберите компанию"
            :items="companyOptions"
            :selected-items="selectedCompanyOptions"
            label-key="display_name"
            value-key="id"
            :search-keys="['name', 'inn', 'display_name']"
            search-placeholder="Поиск по названию или ИНН..."
            :allow-clear="false"
            :remote="true"
            :loading="loadingCompanies"
            :empty-label="companiesError || 'Компании не найдены'"
            :teleport-to="dropdownTarget || 'body'"
            :disabled="submitting"
            @search="fetchCompanies"
            @update:model-value="onCompanyChange"
          />
          <p v-if="loadingCompanies" class="mt-1 text-xs text-gray-400">Загрузка компаний...</p>
          <p v-if="noCompanyMatches" role="status" class="mt-1 text-xs text-gray-500">Компании не найдены</p>
          <p v-if="companiesError" role="alert" class="mt-1 text-sm text-red-600">
            {{ companiesError }} <button type="button" class="underline" @click="fetchCompanies()">Повторить</button>
          </p>
          <p v-if="fieldErrors.owner_company_id" role="alert" class="mt-1 text-sm text-red-600">{{ fieldErrors.owner_company_id }}</p>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Марки ТС</label>
          <SearchableDropdown
            v-model="form.brand_ids"
            :items="markOptions"
            :selected-items="selectedMarks"
            :multiple="true"
            :remote="true"
            :loading="loadingMarks"
            :disabled="submitting"
            :teleport-to="dropdownTarget || 'body'"
            :empty-label="marksError || 'Марки не найдены'"
            placeholder="Выберите марки ТС"
            search-placeholder="Поиск по названию марки..."
            @search="fetchMarks"
          />
          <div v-if="selectedMarks.length" class="mt-2 flex flex-wrap gap-2">
            <span v-for="mark in selectedMarks" :key="mark.id" class="inline-flex items-center gap-1 rounded bg-blue-50 px-2 py-1 text-sm text-blue-800">
              {{ mark.name }}
              <button type="button" :aria-label="`Убрать марку ${mark.name}`" :disabled="submitting" @click="removeMark(mark.id)">×</button>
            </span>
            <button type="button" class="text-sm underline" :disabled="submitting" @click="form.brand_ids = []">Очистить марки</button>
          </div>
          <p v-if="marksError" role="alert" class="mt-1 text-sm text-red-600">
            {{ marksError }} <button type="button" class="underline" @click="fetchMarks()">Повторить</button>
          </p>
          <p v-if="noMarkMatches" role="status" class="mt-1 text-xs text-gray-500">Марки не найдены</p>
          <p v-if="fieldErrors.brand_ids" role="alert" class="mt-1 text-sm text-red-600">{{ fieldErrors.brand_ids }}</p>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Категория ТС</label>
          <SearchableDropdown
            v-model="form.category_id"
            :items="categoryOptions"
            :loading="loadingCategories"
            :disabled="!form.brand_ids.length || loadingCategories || !!categoriesError || submitting"
            :teleport-to="dropdownTarget || 'body'"
            placeholder="Выберите категорию ТС"
            clear-label="Не указана"
            search-placeholder="Поиск по названию категории..."
            empty-label="Для выбранных марок категории не найдены"
          />
          <p v-if="!form.brand_ids.length" class="mt-1 text-xs text-gray-500">Сначала выберите марку ТС</p>
          <p v-else-if="loadingCategories" role="status" class="mt-1 text-xs text-gray-500">Загрузка категорий...</p>
          <p v-else-if="categoriesError" role="alert" class="mt-1 text-sm text-red-600">
            {{ categoriesError }} <button type="button" class="underline" @click="fetchCategories">Повторить</button>
          </p>
          <p v-else-if="!categories.length" class="mt-1 text-xs text-gray-500">Для выбранных марок категории не найдены</p>
          <p v-if="categoryNotice" role="status" class="mt-1 text-xs text-gray-500">{{ categoryNotice }}</p>
          <p v-if="fieldErrors.category_id" role="alert" class="mt-1 text-sm text-red-600">{{ fieldErrors.category_id }}</p>
        </div>

        <!-- Город -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Город
          </label>
          <div v-if="!addingCity" class="flex gap-2 items-center">
            <SearchableDropdown
              v-model="form.city_id"
              class="flex-1"
              placeholder="Не указан"
              clear-label="Не указан"
              :items="cityOptions"
              label-key="name"
              value-key="id"
              search-placeholder="Поиск города..."
              :allow-clear="true"
              :loading="loadingCities"
              :empty-label="citiesError || 'Города не найдены'"
              :teleport-to="dropdownTarget || 'body'"
              :disabled="submitting"
            />
            <button
              type="button"
              class="btn-secondary whitespace-nowrap text-sm h-10"
              @click="addingCity = true"
            >
              + Новый
            </button>
          </div>
          <div v-else class="flex gap-2">
            <input
              v-model="newCityName"
              type="text"
              class="input-field flex-1"
              placeholder="Название города"
              @keyup.enter.prevent="createCity"
            />
            <button
              type="button"
              class="btn-primary whitespace-nowrap text-sm"
              :disabled="!newCityName.trim() || creatingCity"
              @click="createCity"
            >
              Создать
            </button>
            <button
              type="button"
              class="btn-secondary text-sm"
              @click="cancelAddCity"
            >
              Отмена
            </button>
          </div>
          <p v-if="loadingCities" class="mt-1 text-xs text-gray-400">Загрузка городов...</p>
          <p v-if="citiesError" role="alert" class="mt-1 text-sm text-red-600">
            {{ citiesError }} <button type="button" class="underline" @click="fetchCities">Повторить</button>
          </p>
        </div>

        <!-- Адрес -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Адрес склада <span class="text-red-500">*</span>
          </label>
          <input
            v-model="form.address"
            type="text"
            class="input-field"
            placeholder="г. Москва, ул. Примерная, д. 1"
            required
          />
        </div>

        <!-- Активность -->
        <div class="flex items-center pt-2">
          <input
            id="warehouse-is-active"
            v-model="form.is_active"
            type="checkbox"
            class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <label for="warehouse-is-active" class="ml-2 block text-sm font-medium text-gray-900 cursor-pointer">
            Склад активен
          </label>
        </div>

        <!-- Ошибка -->
        <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded-lg">
          <p class="text-sm text-red-600">{{ error }}</p>
        </div>

        <!-- Кнопки формы -->
        <div class="mt-6 flex justify-end space-x-3 pt-4 border-t border-gray-200">
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
            :disabled="submitting || loadingCompanies || loadingCategories || !!categoriesError"
          >
            <span v-if="submitting">Сохранение...</span>
            <span v-else>{{ isEditing ? 'Сохранить' : 'Создать' }}</span>
          </button>
        </div>
      </form>
  </Modal>
</template>

<script setup lang="ts">
import type { City, Company } from '~/types/features'
import type { Warehouse, WarehouseOwnerType, WarehouseMark, WarehouseCategory } from '../types'
import { createWarehousesApi } from '../api/warehousesApi'
import { useWarehouseLookup } from '../useWarehouseLookup'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import Modal from '~/components/ui/Modal.vue'

const props = defineProps<{ warehouse?: Warehouse | null }>()
const emit = defineEmits(['close', 'success'])
const api = createWarehousesApi(useRuntimeConfig())
const isEditing = computed(() => !!props.warehouse)
const dropdownTarget = ref<HTMLFormElement | null>(null)
const form = ref({
  name: props.warehouse?.name || '',
  owner_company_id: props.warehouse?.owner_company_id || '',
  owner_company_type: (props.warehouse?.owner_company_type as WarehouseOwnerType) || 'dealer',
  brand_ids: [...(props.warehouse?.brand_ids || [])],
  category_id: props.warehouse?.category_id || null as string | null,
  city_id: props.warehouse?.city_id || null as string | null,
  address: props.warehouse?.address || '',
  is_active: props.warehouse?.is_active ?? true
})

const knownCompanies = ref<Company[]>(props.warehouse ? [{
  id: props.warehouse.owner_company_id,
  name: props.warehouse.owner_company_name || props.warehouse.company_name || '',
  company_type: props.warehouse.owner_company_type,
  is_active: true
}] : [])
const knownMarks = ref<WarehouseMark[]>([...(props.warehouse?.selected_brands || [])])
const mergeRecords = <T extends { id: string }>(previous: T[], incoming: T[]): T[] =>
  [...new Map([...previous, ...incoming].map(item => [item.id, item])).values()]

const companyLookup = useWarehouseLookup<Company>(async (search, page) => {
  const responses = await Promise.all(['dealer', 'distributor'].map(company_type =>
    api.getCompanies({ search, company_type, page, limit: 100 })
  ))
  return {
    items: responses.flatMap(response => response.companies),
    pages: Math.max(...responses.map(response => response.pagination.pages))
  }
}, 'Не удалось загрузить компании')
const { loading: loadingCompanies, error: companiesError, empty: noCompanyMatches } = companyLookup
const fetchCompanies = async (search?: string) => {
  const matches = await companyLookup.load(search)
  if (!matches) return
  knownCompanies.value = mergeRecords(knownCompanies.value, matches)
  if (!form.value.owner_company_id && matches.length === 1 && !search) {
    form.value.owner_company_id = matches[0].id
  }
  onCompanyChange()
}
const companyOption = (company: Company) => ({
  ...company,
  display_name: `${company.name}${company.inn ? ` (ИНН: ${company.inn})` : ''} — ${company.company_type === 'distributor' ? 'Дистрибьютор' : 'Дилер'}`
})
const companyOptions = computed(() => companyLookup.items.value.map(companyOption))
const selectedCompanyOptions = computed(() => knownCompanies.value
  .filter(company => company.id === form.value.owner_company_id).map(companyOption))
const onCompanyChange = () => {
  const selected = knownCompanies.value.find(company => company.id === form.value.owner_company_id)
  if (selected) {
    form.value.owner_company_type = selected.company_type === 'distributor' ? 'distributor' : 'dealer'
  }
}

const markLookup = useWarehouseLookup<WarehouseMark>(async (search, page) => {
  const response = await api.getWarehouseMarkOptions({ search, page, limit: 100 })
  return { items: response.marks, pages: response.pagination.pages }
}, 'Не удалось загрузить марки ТС')
const { loading: loadingMarks, error: marksError, empty: noMarkMatches } = markLookup
const fetchMarks = async (search?: string) => {
  const matches = await markLookup.load(search)
  if (matches) knownMarks.value = mergeRecords(knownMarks.value, matches)
}
const selectedMarks = computed(() => knownMarks.value.filter(mark => form.value.brand_ids.includes(mark.id)))
const markOptions = computed(() => markLookup.items.value.map(mark => ({ ...mark })))
const removeMark = (id: string) => {
  form.value.brand_ids = form.value.brand_ids.filter(brandId => brandId !== id)
}

const categories = ref<WarehouseCategory[]>([])
const selectedCategory = ref<WarehouseCategory | null>(props.warehouse?.category_id ? {
  id: props.warehouse.category_id,
  name: props.warehouse.category_name || ''
} : null)
const categoryOptions = computed(() => mergeRecords(
  selectedCategory.value && selectedCategory.value.id === form.value.category_id ? [selectedCategory.value] : [],
  categories.value
).map(category => ({ ...category })))
const loadingCategories = ref(false)
const categoriesError = ref('')
const categoryNotice = ref('')
let categoryRevision = 0
const fetchCategories = async () => {
  const revision = ++categoryRevision
  const brandIds = [...form.value.brand_ids]
  categories.value = []
  categoriesError.value = ''
  categoryNotice.value = ''
  if (!brandIds.length) {
    form.value.category_id = null
    selectedCategory.value = null
    loadingCategories.value = false
    return
  }
  loadingCategories.value = true
  try {
    const available: WarehouseCategory[] = []
    let page = 1
    let pages = 1
    do {
      const response = await api.getWarehouseCategories(brandIds, page, 100)
      if (revision !== categoryRevision) return
      available.push(...response.categories)
      pages = response.pagination.pages
      page += 1
    } while (page <= pages)
    categories.value = available
    const selected = available.find(category => category.id === form.value.category_id)
    if (form.value.category_id && !selected) {
      form.value.category_id = null
      categoryNotice.value = 'Выберите категорию для выбранных марок'
    }
    selectedCategory.value = selected || null
  } catch {
    if (revision === categoryRevision) categoriesError.value = 'Не удалось загрузить категории ТС'
  } finally {
    if (revision === categoryRevision) loadingCategories.value = false
  }
}
watch(() => [...form.value.brand_ids], fetchCategories)
watch(() => form.value.category_id, id => {
  if (id) selectedCategory.value = categories.value.find(category => category.id === id) || null
  if (id) categoryNotice.value = ''
})

const cities = ref<City[]>([])
const loadingCities = ref(false)
const citiesError = ref('')
const addingCity = ref(false)
const newCityName = ref('')
const creatingCity = ref(false)
const cityOptions = computed(() => cities.value.map(city => ({ ...city })))
const fetchCities = async () => {
  loadingCities.value = true
  citiesError.value = ''
  try {
    // The city endpoint returns the complete directory without pagination.
    const response = await api.getCities()
    cities.value = response.cities
  } catch {
    citiesError.value = 'Не удалось загрузить города'
  } finally {
    loadingCities.value = false
  }
}
const cancelAddCity = () => {
  addingCity.value = false
  newCityName.value = ''
}
const createCity = async () => {
  const name = newCityName.value.trim()
  if (!name) return
  creatingCity.value = true
  try {
    const response = await api.createCity(name)
    cities.value = mergeRecords(cities.value, [response.city]).sort((a, b) => a.name.localeCompare(b.name))
    form.value.city_id = response.city.id
    cancelAddCity()
  } catch (err: unknown) {
    error.value = apiErrorMessage(err, 'Ошибка при создании города')
  } finally {
    creatingCity.value = false
  }
}

const error = ref('')
const fieldErrors = ref<Record<string, string>>({})
const submitting = ref(false)
interface FieldError { loc: (string | number)[]; msg: string }
const apiErrorMessage = (err: unknown, fallback: string): string => {
  const data = (err as { data?: { detail?: string | FieldError[]; error?: string; message?: string } }).data
  if (Array.isArray(data?.detail)) {
    for (const issue of data.detail) {
      const field = issue.loc[1]
      if (typeof field === 'string') fieldErrors.value[field] = issue.msg
    }
    return 'Проверьте поля формы'
  }
  return data?.detail || data?.error || data?.message || fallback
}
const handleSubmit = async () => {
  if (submitting.value || loadingCategories.value || categoriesError.value) return
  error.value = ''
  fieldErrors.value = {}
  if (!form.value.name.trim()) {
    error.value = 'Название склада обязательно для заполнения'
    return
  }
  if (!form.value.owner_company_id) {
    error.value = 'Компания-владелец обязательна для заполнения'
    return
  }
  if (!form.value.address.trim()) {
    error.value = 'Адрес склада обязателен для заполнения'
    return
  }
  submitting.value = true
  try {
    const body = {
      name: form.value.name.trim(),
      owner_company_id: form.value.owner_company_id,
      owner_company_type: form.value.owner_company_type,
      brand_ids: [...form.value.brand_ids],
      category_id: form.value.category_id,
      address: form.value.address.trim(),
      city_id: form.value.city_id,
      is_active: form.value.is_active
    }
    if (props.warehouse) await api.updateWarehouse(props.warehouse.id, body)
    else await api.createWarehouse(body)
    emit('success')
  } catch (err: unknown) {
    error.value = apiErrorMessage(err, 'Ошибка при сохранении склада')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  fetchCompanies('')
  fetchMarks('')
  fetchCities()
  fetchCategories()
})
onBeforeUnmount(() => { categoryRevision += 1 })
</script>
