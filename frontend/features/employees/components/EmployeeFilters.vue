<template>
  <div class="bg-white p-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] shadow-sm space-y-4">
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div>
        <label for="filter-role" class="block text-xs font-medium text-gray-700 mb-1">Роль</label>
        <select id="filter-role" v-model="filters.role" class="select-field text-sm" @change="onRoleChange">
          <option value="">Все роли</option>
          <option value="dealer">Дилер</option>
          <option value="distributor">Дистрибьютор</option>
          <option value="client">Клиент</option>
          <option value="leasing_company">Лизинговая компания</option>
          <option value="carcraft_employee">Сотрудник КК</option>
        </select>
      </div>
      <!-- Компания -->
      <div v-if="filters.role !== 'dealer'">
        <label for="filter-company" class="block text-xs font-medium text-gray-700 mb-1">
          Компания
        </label>
        <select
          id="filter-company"
          v-model="filters.company_id"
          class="select-field text-sm"
        >
          <option value="">Все компании</option>
          <option
            v-for="company in companies"
            :key="company.id"
            :value="company.id"
          >
            {{ company.name }}
          </option>
        </select>
      </div>

      <div v-for="field in objectFilters" :key="field.key">
        <label :for="`filter-${field.key.replace('_id', '')}`" class="block text-xs font-medium text-gray-700 mb-1">{{ field.label }}</label>
        <select :id="`filter-${field.key.replace('_id', '')}`" v-model="filters[field.key]" class="select-field text-sm">
          <option value="">{{ field.allLabel }}</option>
          <option v-for="item in options[field.options]" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </div>

      <!-- Должность -->
      <div>
        <label for="filter-position" class="block text-xs font-medium text-gray-700 mb-1">
          Должность
        </label>
        <select
          id="filter-position"
          v-model="filters.position_id"
          class="select-field text-sm"
        >
          <option value="">Все должности</option>
          <option
            v-for="position in positions"
            :key="position.id"
            :value="position.id"
          >
            {{ position.name }}
          </option>
        </select>
      </div>

      <!-- ФИО -->
      <div>
        <label for="filter-name" class="block text-xs font-medium text-gray-700 mb-1">
          ФИО
        </label>
        <input
          id="filter-name"
          v-model="filters.name"
          type="text"
          placeholder="Поиск по ФИО"
          class="storefront-control block w-full px-3 py-2 text-sm border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          @keydown.enter.prevent="applyFilters"
        />
      </div>

      <!-- Телефон -->
      <div>
        <label for="filter-phone" class="block text-xs font-medium text-gray-700 mb-1">
          Телефон
        </label>
        <input
          id="filter-phone"
          v-model="filters.phone"
          type="text"
          placeholder="+7 (999) 000-00-00"
          class="storefront-control block w-full px-3 py-2 text-sm border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
          @keydown.enter.prevent="applyFilters"
        />
      </div>
    </div>

    <!-- Buttons -->
    <div class="flex items-center justify-end gap-3 pt-2 border-t border-gray-100">
      <button
        type="button"
        class="btn-secondary text-sm px-4 py-1.5"
        :disabled="loading"
        @click="resetFilters"
      >
        Сбросить
      </button>
      <button
        type="button"
        class="btn-primary text-sm px-4 py-1.5"
        :disabled="loading"
        @click="applyFilters"
      >
        Применить
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { UUID } from '~/types/ids'
import type { EmployeeRole, EmployeeFilterOptions } from '../api/employeesApi'

export interface FilterState {
  role: EmployeeRole | ''
  dealer_id: UUID | ''
  distributor_id: UUID | ''
  brand_id: UUID | ''
  warehouse_id: UUID | ''
  company_id: UUID | ''
  position_id: UUID | ''
  name: string
  phone: string
}

const props = withDefaults(
  defineProps<{
    companies?: Array<{ id: UUID; name: string }>
    options: EmployeeFilterOptions
    positions?: Array<{ id: UUID; name: string }>
    initialFilters?: Partial<FilterState>
    loading?: boolean
  }>(),
  {
    companies: () => [],
    positions: () => [],
    initialFilters: () => ({}),
    loading: false,
  },
)

const emit = defineEmits<{
  (e: 'apply', filters: FilterState): void
  (e: 'reset'): void
}>()

const emptyFilters = (): FilterState => ({
  role: '', company_id: '', position_id: '', dealer_id: '', distributor_id: '',
  brand_id: '', warehouse_id: '', name: '', phone: '',
})

const filters = ref<FilterState>({ ...emptyFilters(), ...props.initialFilters })

watch(() => props.initialFilters, (value) => {
  filters.value = { ...emptyFilters(), ...value }
}, { deep: true })

type ObjectFilterKey = 'dealer_id' | 'distributor_id' | 'brand_id' | 'warehouse_id'
const objectFilters = computed<Array<{
  key: ObjectFilterKey; label: string; allLabel: string; options: keyof EmployeeFilterOptions
}>>(() => {
  if (filters.value.role === 'dealer') return [
    { key: 'distributor_id', label: 'Дистрибьютор', allLabel: 'Все дистрибьюторы', options: 'distributors' },
    { key: 'dealer_id', label: 'Дилер', allLabel: 'Все дилеры', options: 'dealers' },
    { key: 'warehouse_id', label: 'Склад', allLabel: 'Все склады', options: 'warehouses' },
  ]
  if (filters.value.role === 'distributor') return [
    { key: 'brand_id', label: 'Марка', allLabel: 'Все марки', options: 'brands' },
    { key: 'warehouse_id', label: 'Склад', allLabel: 'Все склады', options: 'warehouses' },
  ]
  return []
})

const onRoleChange = () => {
  filters.value.dealer_id = ''
  filters.value.distributor_id = ''
  filters.value.brand_id = ''
  filters.value.warehouse_id = ''
  if (filters.value.role === 'dealer') filters.value.company_id = ''
  emit('apply', { ...filters.value })
}

const applyFilters = () => emit('apply', { ...filters.value })
const resetFilters = () => {
  filters.value = emptyFilters()
  emit('reset')
}
</script>
