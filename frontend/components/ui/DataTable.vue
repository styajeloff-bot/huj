<template>
  <div data-storefront-block="shared.form" class="data-table">
    <!-- Header -->
    <div v-if="showHeader" class="flex items-center justify-between mb-4">
      <div>
        <h3 v-if="title" class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">{{ title }}</h3>
        <p v-if="description" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">{{ description }}</p>
      </div>
      <div class="flex items-center space-x-3">
        <!-- Search -->
        <div v-if="searchable" class="relative">
          <MagnifyingGlassIcon class="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-[color:var(--storefront-icon,#9ca3af)]" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Поиск..."
            class="storefront-control pl-10 pr-4 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
          />
        </div>
        
        <!-- Filters -->
        <div v-if="filterable" class="relative">
          <button
            @click="showFilters = !showFilters"
            class="storefront-action-ghost flex items-center px-3 py-2 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-md text-sm font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
          >
            <FunnelIcon class="h-4 w-4 mr-2" />
            Фильтры
            <span v-if="activeFiltersCount > 0" class="ml-2 bg-[color:rgb(var(--storefront-secondary-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-secondary-foreground,#1e40af)] text-xs rounded-full px-2 py-1">
              {{ activeFiltersCount }}
            </span>
          </button>
        </div>

        <!-- Export -->
        <button
          v-if="exportable"
          @click="exportData"
          class="storefront-action-primary flex items-center px-3 py-2 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-md text-sm font-medium hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]"
        >
          <ArrowDownTrayIcon class="h-4 w-4 mr-2" />
          Экспорт
        </button>

        <!-- Refresh -->
        <button
          v-if="refreshable"
          @click="$emit('refresh')"
          :disabled="loading"
          class="storefront-action-ghost flex items-center px-3 py-2 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-md text-sm font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50"
        >
          <ArrowPathIcon class="h-4 w-4" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <!-- Filters Panel -->
    <div v-if="filterable && showFilters" class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg p-4 mb-4">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div v-for="filter in filters" :key="filter.key" class="space-y-1">
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">{{ filter.label }}</label>
          
          <!-- Select Filter -->
          <select
            v-if="filter.type === 'select'"
            v-model="filterValues[filter.key]"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
          >
            <option value="">Все</option>
            <option v-for="option in filter.options" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>

          <!-- Date Filter -->
          <input
            v-else-if="filter.type === 'date'"
            v-model="filterValues[filter.key]"
            type="date"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
          />

          <!-- Text Filter -->
          <input
            v-else
            v-model="filterValues[filter.key]"
            type="text"
            :placeholder="filter.placeholder"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
          />
        </div>
      </div>
      
      <div class="flex items-center justify-between mt-4">
        <button
          @click="clearFilters"
          class="storefront-action-ghost text-sm text-[color:var(--storefront-ghost-foreground,#4b5563)] hover:text-[color:var(--storefront-ghost-hover-foreground,#111827)]"
        >
          Сбросить фильтры
        </button>
        <button
          @click="applyFilters"
          class="storefront-action-primary px-4 py-2 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-md text-sm font-medium hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]"
        >
          Применить
        </button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="flex items-center justify-center py-8">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <span class="ml-3 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем данные...</span>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredData.length === 0" class="text-center py-8">
      <div class="text-[color:var(--storefront-text-muted,#9ca3af)] mb-2">
        <component :is="emptyIcon" class="text-[color:var(--storefront-icon,inherit)] h-12 w-12 mx-auto" />
      </div>
      <p class="text-[color:var(--storefront-text-muted,#6b7280)]">{{ emptyMessage }}</p>
      <button
        v-if="emptyAction"
        @click="$emit('empty-action')"
        class="storefront-action-primary mt-4 px-4 py-2  text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-md text-sm font-medium hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]"
      >
        {{ emptyActionText }}
      </button>
    </div>

    <!-- Table -->
    <div v-else class="shadow ring-1 ring-[color:var(--storefront-border,#000000)] ring-opacity-5 md:rounded-lg overflow-x-auto">
      <table class="min-w-full divide-y divide-[color:var(--storefront-border,#d1d5db)]">
        <thead class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
          <tr>
            <!-- Selection Column -->
            <th v-if="selectable" class="relative w-12 px-6 sm:w-16 sm:px-8">
              <input
                type="checkbox"
                :checked="allSelected"
                @change="toggleSelectAll"
                class="storefront-control absolute left-4 top-1/2 -mt-2 h-4 w-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
              />
            </th>

            <!-- Column Headers -->
            <th
              v-for="column in visibleColumns"
              :key="column.key"
              :class="[
                'px-6 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider',
                column.sortable ? 'cursor-pointer hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]' : ''
              ]"
              @click="column.sortable ? toggleSort(column.key) : null"
            >
              <div class="flex items-center space-x-1">
                <span>{{ column.label }}</span>
                <div v-if="column.sortable" class="flex flex-col">
                  <ChevronUpIcon
                    :class="[
                      'h-3 w-3',
                      sortField === column.key && sortDirection === 'asc' ? 'text-[color:var(--storefront-icon,#2563eb)]' : 'text-[color:var(--storefront-icon,#9ca3af)]'
                    ]" 
                  />
                  <ChevronDownIcon
                    :class="[
                      'h-3 w-3 -mt-1',
                      sortField === column.key && sortDirection === 'desc' ? 'text-[color:var(--storefront-icon,#2563eb)]' : 'text-[color:var(--storefront-icon,#9ca3af)]'
                    ]" 
                  />
                </div>
              </div>
            </th>

            <!-- Actions Column -->
            <th v-if="actions.length > 0" class="relative px-2 py-3 text-right">
              <span class="sr-only">Действия</span>
            </th>
          </tr>
        </thead>
        <tbody class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
          <tr
            v-for="(item, index) in paginatedData"
            :key="getItemKey(item, index)"
            :class="[
              'hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]',
              selectedItems.includes(getItemKey(item, index)) ? 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]' : '',
              rowClickable ? 'cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#3b82f6)] focus-visible:ring-inset' : ''
            ]"
            :tabindex="rowClickable ? 0 : undefined"
            @click="handleRowClick(item)"
            @keydown.enter="handleRowClick(item)"
          >
            <!-- Selection Column -->
            <td v-if="selectable" class="relative w-12 px-6 sm:w-16 sm:px-8">
              <input
                type="checkbox"
                :checked="selectedItems.includes(getItemKey(item, index))"
                @click.stop
                @change.stop="toggleSelect(getItemKey(item, index))"
                class="storefront-control absolute left-4 top-1/2 -mt-2 h-4 w-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
              />
            </td>

            <!-- Data Columns -->
            <td
              v-for="column in visibleColumns"
              :key="column.key"
              class="px-6 py-4 whitespace-nowrap text-sm"
              :class="column.className || 'text-[color:var(--storefront-text,#111827)]'"
            >
              <!-- Custom Slot -->
              <slot
                v-if="$slots[`column-${column.key}`]"
                :name="`column-${column.key}`"
                :item="item"
                :value="getNestedValue(item, column.key)"
              />
              
              <!-- Status Badge -->
              <span
                v-else-if="column.type === 'status'"
                :class="getStatusClasses(getNestedValue(item, column.key))"
                class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
              >
                {{ formatValue(getNestedValue(item, column.key), column) }}
              </span>

              <!-- Currency -->
              <span v-else-if="column.type === 'currency'">
                {{ formatCurrency(getNestedValue(item, column.key)) }}
              </span>

              <!-- Date -->
              <span v-else-if="column.type === 'date'">
                {{ formatDate(getNestedValue(item, column.key)) }}
              </span>

              <!-- Default -->
              <span v-else>
                {{ formatValue(getNestedValue(item, column.key), column) }}
              </span>
            </td>

            <!-- Actions Column -->
            <td v-if="actions.length > 0" class="relative whitespace-nowrap py-4 pl-1 pr-2 text-right text-sm font-medium">
              <div class="inline-flex items-center justify-end gap-1 align-middle">
                <button class="storefront-action-ghost"
                  v-for="action in actions"
                  v-show="!action.visible || action.visible(item)"
                  :key="action.key"
                  type="button"
                  @click.stop="$emit('action', { action: action.key, item })"
                  :class="[
                    'p-1 rounded hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))]',
                    action.className || 'text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)]'
                  ]"
                  :title="action.label"
                >
                  <component :is="action.icon" class="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="showPagination" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-6 py-3 flex items-center justify-between border-t border-[color:var(--storefront-border,#e5e7eb)]">
      <div class="flex flex-1 items-center justify-between">
        <div>
          <p class="text-sm text-[color:var(--storefront-text,#374151)]">
            Показано <span class="font-medium">{{ startIndex + 1 }}</span> -
            <span class="font-medium">{{ Math.min(endIndex, totalItemsCount) }}</span> из
            <span class="font-medium">{{ totalItemsCount }}</span> результатов
          </p>
        </div>
        <div>
          <nav class="relative z-0 inline-flex rounded-md shadow-sm -space-x-px">
            <button
              @click="previousPage"
              :disabled="actualCurrentPage === 1"
              class="storefront-action-secondary relative inline-flex items-center px-2 py-2 rounded-l-md border border-[color:var(--storefront-secondary-border,#d1d5db)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-sm font-medium text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50"
            >
              <ChevronLeftIcon class="h-5 w-5" />
            </button>
            
            <button class="storefront-action-secondary"
              v-for="page in visiblePages"
              :key="page"
              @click="goToPage(page)"
              :class="[
                'relative inline-flex items-center px-4 py-2 border text-sm font-medium',
                page === actualCurrentPage
                  ? 'z-10 bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-primary-border,#3b82f6)] text-[color:var(--storefront-primary-foreground,#2563eb)]'
                  : 'bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-primary-border,#d1d5db)] text-[color:var(--storefront-primary-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]'
              ]"
            >
              {{ page }}
            </button>
            
            <button
              @click="nextPage"
              :disabled="actualCurrentPage === totalPages"
              class="storefront-action-secondary relative inline-flex items-center px-2 py-2 rounded-r-md border border-[color:var(--storefront-secondary-border,#d1d5db)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-sm font-medium text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50"
            >
              <ChevronRightIcon class="h-5 w-5" />
            </button>
          </nav>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  MagnifyingGlassIcon,
  FunnelIcon,
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DocumentIcon
} from '@heroicons/vue/24/outline'

import type { PropType } from 'vue'
import type { DataTableColumn, DataTableFilter, DataTableAction } from '@/types'

const props = defineProps({
  data: { type: Array as PropType<Record<string, unknown>[]>, default: () => [] },
  columns: { type: Array as PropType<DataTableColumn[]>, required: true },
  loading: { type: Boolean, default: false },
  title: { type: String },
  description: { type: String },
  searchable: { type: Boolean, default: true },
  filterable: { type: Boolean, default: true },
  filters: { type: Array as PropType<DataTableFilter[]>, default: () => [] },
  sortable: { type: Boolean, default: true },
  paginated: { type: Boolean, default: true },
  pageSize: { type: Number, default: 10 },
  selectable: { type: Boolean, default: false },
  exportable: { type: Boolean, default: false },
  refreshable: { type: Boolean, default: true },
  actions: { type: Array as PropType<DataTableAction[]>, default: () => [] },
  rowClickable: { type: Boolean, default: false },
  emptyMessage: { type: String, default: 'Нет данных для отображения' },
  emptyActionText: { type: String },
  emptyAction: { type: Boolean, default: false },
  emptyIcon: { type: Object, default: () => DocumentIcon },
  showHeader: { type: Boolean, default: true },
  itemKey: { type: String, default: 'id' },
  // Server-side mode props
  serverSide: { type: Boolean, default: false },
  totalItems: { type: Number, default: 0 },
  currentServerPage: { type: Number, default: 1 },
  totalServerPages: { type: Number, default: 1 }
})

const emit = defineEmits(['refresh', 'action', 'row-click', 'export', 'filter', 'sort', 'select', 'empty-action', 'page-change', 'search'])

// Reactive data
const searchQuery = ref('')
const showFilters = ref(false)
const filterValues = ref<Record<string, string>>({})
const sortField = ref('')
const sortDirection = ref<'asc' | 'desc'>('asc')
const currentPage = ref(1)
const selectedItems = ref<Array<string | number>>([])

// Computed properties
const visibleColumns = computed(() => {
  return props.columns.filter(col => !col.hidden)
})

const filteredData = computed(() => {
  // В server-side режиме данные уже отфильтрованы сервером
  if (props.serverSide) {
    return props.data
  }

  let result = [...props.data]

  // Apply search
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(item => {
      return props.columns.some(col => {
        const value = getNestedValue(item, col.key)
        return value && value.toString().toLowerCase().includes(query)
      })
    })
  }

  // Apply filters
  Object.keys(filterValues.value).forEach(key => {
    const value = filterValues.value[key]
    if (value) {
      result = result.filter(item => {
        const itemValue = getNestedValue(item, key)
        if (typeof value === 'string') {
          return itemValue && itemValue.toString().toLowerCase().includes(value.toLowerCase())
        }
        return itemValue === value
      })
    }
  })

  // Apply sorting
  if (sortField.value) {
    result.sort((a, b) => {
      const aVal = getNestedValue(a, sortField.value)
      const bVal = getNestedValue(b, sortField.value)
      
      if (aVal === bVal) return 0

      const comparison = String(aVal ?? '') > String(bVal ?? '') ? 1 : -1
      return sortDirection.value === 'asc' ? comparison : -comparison
    })
  }

  return result
})

const paginatedData = computed(() => {
  // В server-side режиме данные уже пагинированы сервером
  if (props.serverSide) {
    return props.data
  }
  
  if (!props.paginated) return filteredData.value
  
  const start = (currentPage.value - 1) * props.pageSize
  return filteredData.value.slice(start, start + props.pageSize)
})

const totalPages = computed(() => {
  if (props.serverSide) {
    return props.totalServerPages
  }
  return Math.ceil(filteredData.value.length / props.pageSize)
})

const actualCurrentPage = computed(() => {
  return props.serverSide ? props.currentServerPage : currentPage.value
})

const totalItemsCount = computed(() => {
  return props.serverSide ? props.totalItems : filteredData.value.length
})

const showPagination = computed(() => {
  if (props.serverSide) {
    return props.paginated && totalPages.value > 1
  }
  return props.paginated && filteredData.value.length > props.pageSize
})

const startIndex = computed(() => {
  return (actualCurrentPage.value - 1) * props.pageSize
})

const endIndex = computed(() => {
  return startIndex.value + props.pageSize
})

const visiblePages = computed(() => {
  const pages = []
  const maxVisible = 5
  const current = actualCurrentPage.value
  let start = Math.max(1, current - Math.floor(maxVisible / 2))
  let end = Math.min(totalPages.value, start + maxVisible - 1)
  
  if (end - start < maxVisible - 1) {
    start = Math.max(1, end - maxVisible + 1)
  }
  
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  
  return pages
})

const activeFiltersCount = computed(() => {
  return Object.values(filterValues.value).filter(Boolean).length
})

const allSelected = computed(() => {
  return paginatedData.value.length > 0 && 
         paginatedData.value.every(item => selectedItems.value.includes(getItemKey(item)))
})

const { formatPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

// Methods
const getNestedValue = (obj: Record<string, unknown>, path: string): unknown => {
  return path.split('.').reduce((current: unknown, key: string) => (current as Record<string, unknown>)?.[key], obj)
}

const getItemKey = (item: Record<string, unknown>, index: number | null = null): string | number => {
  return (getNestedValue(item, props.itemKey) as string | number) || index || 0
}

const formatValue = (value: unknown, column: DataTableColumn): unknown => {
  if (value === null || value === undefined) return '-'

  if (column.formatter) {
    return column.formatter(value)
  }

  return value
}

const formatCurrency = (amount: unknown): string => {
  if (!amount) return '0 ₽'
  return formatPrice(Number(amount))
}

const formatDate = (date: unknown): string => {
  if (!date) return '-'
  return formatSharedDate(String(date))
}

const getStatusClasses = (status: unknown): string => {
  const statusClasses: Record<string, string> = {
    'approved': 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]',
    'rejected': 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]',
    'pending': 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#854d0e)]',
    'in_review': 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]',
    'cancelled': 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
  }
  return statusClasses[String(status)] || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
}

const toggleSort = (field: string) => {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDirection.value = 'asc'
  }
  emit('sort', { field: sortField.value, direction: sortDirection.value })
}

const toggleSelect = (key: string | number) => {
  const index = selectedItems.value.indexOf(key)
  if (index > -1) {
    selectedItems.value.splice(index, 1)
  } else {
    selectedItems.value.push(key)
  }
  emit('select', selectedItems.value)
}

const toggleSelectAll = () => {
  if (allSelected.value) {
    selectedItems.value = []
  } else {
    selectedItems.value = paginatedData.value.map(item => getItemKey(item))
  }
  emit('select', selectedItems.value)
}

const handleRowClick = (item: Record<string, unknown>) => {
  if (!props.rowClickable) return
  emit('row-click', item)
}

const clearFilters = () => {
  filterValues.value = {}
  applyFilters()
}

const applyFilters = () => {
  currentPage.value = 1
  emit('filter', filterValues.value)
}

const exportData = () => {
  emit('export', {
    data: filteredData.value,
    columns: visibleColumns.value
  })
}

const previousPage = () => {
  if (props.serverSide) {
    if (props.currentServerPage > 1) {
      emit('page-change', props.currentServerPage - 1)
    }
  } else {
    if (currentPage.value > 1) {
      currentPage.value--
    }
  }
}

const nextPage = () => {
  if (props.serverSide) {
    if (props.currentServerPage < totalPages.value) {
      emit('page-change', props.currentServerPage + 1)
    }
  } else {
    if (currentPage.value < totalPages.value) {
      currentPage.value++
    }
  }
}

const goToPage = (page: number) => {
  if (props.serverSide) {
    emit('page-change', page)
  } else {
    currentPage.value = page
  }
}

// Watch for search query changes in server-side mode
let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, (newValue) => {
  if (props.serverSide) {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
    searchDebounceTimer = setTimeout(() => {
      emit('search', newValue)
    }, 300)
  }
})

// Initialize filters
onMounted(() => {
  props.filters.forEach(filter => {
    filterValues.value[filter.key] = ''
  })
})

// Expose methods for parent component
defineExpose({
  clearSelection: () => { selectedItems.value = [] },
  selectAll: () => { selectedItems.value = filteredData.value.map(item => getItemKey(item)) },
  getSelectedItems: () => selectedItems.value,
  refresh: () => emit('refresh')
})
</script>
