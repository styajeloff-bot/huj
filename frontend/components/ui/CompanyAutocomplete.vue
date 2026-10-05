<template>
  <div data-storefront-block="shared.form">
    <div class="flex gap-2">
      <input
        v-model="searchQuery"
        type="text"
        class="storefront-control select-field flex-1"
        :placeholder="placeholder"
        @input="handleSearch"
        @focus="handleFocus"
        @keydown="handleKeyDown"
      />
    </div>
    
    <div
      v-if="showResults && (suggestions.length > 0 || loading)"
      class="mt-2 w-full border border-[color:var(--storefront-border,#d1d5db)] rounded-lg overflow-hidden bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]"
      :class="{ 'border-[color:var(--storefront-error-border,#ef4444)] ring-2 ring-[color:var(--storefront-error-border,#ef4444)] ring-opacity-20': required && !selectedValue }"
    >
      <div class="px-3 py-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#4b5563)] text-sm border-b border-[color:var(--storefront-border,#e5e7eb)]">
        {{ loading ? 'Поиск компаний...' : 'Выберите компанию из списка' }}
      </div>
      <div ref="suggestionsContainer" class="max-h-60 overflow-y-auto">
        <div
          v-for="(suggestion, index) in suggestions"
          :key="(suggestion.inn || suggestion.name) + '-' + index"
          :ref="(el: unknown) => { if (el) suggestionRefs[index] = el as HTMLElement }"
          class="px-3 py-2 cursor-pointer hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#f3f4f6)] last:border-b-0 transition-colors"
          :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))]': selectedSuggestionIndex !== null && selectedSuggestionIndex === index }"
          @click="selectSuggestion(index)"
        >
          <div class="text-sm text-[color:var(--storefront-text,#111827)] whitespace-normal break-words leading-relaxed">
            {{ formatSuggestionDisplay(suggestion) }}
          </div>
        </div>
      </div>
    </div>
    
    <div v-if="showResults && !loading && searchQuery && suggestions.length === 0" class="mt-2 p-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-md text-[color:var(--storefront-text-muted,#4b5563)] text-sm">
      Компании не найдены.
    </div>
    
    <div v-if="selectedCompany && showSelectedDetails" class="mt-3 p-4 bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-success-border,#bbf7d0)] rounded-lg">
      <div class="space-y-2">
        <div>
          <span class="text-sm font-medium text-[color:var(--storefront-text,#374151)]">Название:</span>
          <div class="text-sm text-[color:var(--storefront-text,#111827)]">{{ selectedCompany.name }}</div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div v-if="selectedCompany.inn">
            <span class="text-xs font-medium text-[color:var(--storefront-text-muted,#4b5563)]">ИНН:</span>
            <div class="text-sm text-[color:var(--storefront-text,#1f2937)] font-mono">{{ selectedCompany.inn }}</div>
          </div>

          <div v-if="selectedCompany.kpp">
            <span class="text-xs font-medium text-[color:var(--storefront-text-muted,#4b5563)]">КПП:</span>
            <div class="text-sm text-[color:var(--storefront-text,#1f2937)] font-mono">{{ selectedCompany.kpp }}</div>
          </div>

          <div v-if="selectedCompany.ogrn">
            <span class="text-xs font-medium text-[color:var(--storefront-text-muted,#4b5563)]">ОГРН:</span>
            <div class="text-sm text-[color:var(--storefront-text,#1f2937)] font-mono">{{ selectedCompany.ogrn }}</div>
          </div>
        </div>

        <div v-if="selectedCompany.legal_address">
          <span class="text-xs font-medium text-[color:var(--storefront-text-muted,#4b5563)]">Адрес:</span>
          <div class="text-sm text-[color:var(--storefront-text,#1f2937)]">{{ selectedCompany.legal_address }}</div>
        </div>

        <div v-if="selectedCompany.manager_name">
          <span class="text-xs font-medium text-[color:var(--storefront-text-muted,#4b5563)]">Руководитель:</span>
          <div class="text-sm text-[color:var(--storefront-text,#1f2937)]">{{ selectedCompany.manager_name }}</div>
        </div>
      </div>
    </div>
    
    <div v-if="required && !selectedValue && attempted" class="text-[color:var(--storefront-error-text,#ef4444)] text-xs mt-1">
      Необходимо выбрать компанию из списка
    </div>
  </div>
</template>

<script setup lang="ts">
interface CompanySuggestion {
  inn?: string | null
  name: string
  kpp?: string
  ogrn?: string
  legal_address?: string
  manager_name?: string
  entity_type?: string
  phone?: string
  email?: string
  [key: string]: unknown
}

interface CompanySearchResult {
  items: CompanySuggestion[]
}

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: 'Введите название компании или ИНН'
  },
  required: {
    type: Boolean,
    default: false
  },
  presetOptions: {
    type: Array as PropType<CompanySuggestion[]>,
    default: () => []
  },
  showSelectedDetails: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue', 'validation', 'select'])

const searchQuery = ref(props.modelValue)
const selectedValue = ref(props.modelValue)
const selectedCompany = ref<CompanySuggestion | null>(null)
const selectedSuggestionIndex = ref<number | null>(null)
const suggestions = ref<CompanySuggestion[]>([])
const showResults = ref(false)
const loading = ref(false)
const attempted = ref(false)
const searchTimeout = ref<ReturnType<typeof setTimeout> | null>(null)
const suggestionsContainer = ref<HTMLElement | null>(null)
const suggestionRefs = ref<Record<number, HTMLElement>>({})
const skipSelectedValueModelEmit = ref(false)

const config = useRuntimeConfig()

// Инициализируем валидацию
onMounted(() => {
  const isValid = props.required ? !!selectedValue.value : true
  emit('validation', isValid)
})

watch(() => props.modelValue, (newValue) => {
  searchQuery.value = newValue
  selectedValue.value = newValue
  if (!newValue) {
    selectedCompany.value = null
  }
})

watch(selectedValue, (newValue) => {
  if (!skipSelectedValueModelEmit.value) {
    emit('update:modelValue', newValue)
  }
  const isValid = props.required ? !!newValue : true
  emit('validation', isValid)
})

watch(selectedSuggestionIndex, (newIndex) => {
  if (newIndex !== null && suggestionRefs.value[newIndex]) {
    nextTick(() => {
      if (newIndex !== null && suggestionRefs.value[newIndex]) {
        suggestionRefs.value[newIndex].scrollIntoView({
          behavior: 'smooth',
          block: 'nearest'
        })
      }
    })
  }
})

const searchCompanies = async (query: string) => {
  if (!query || query.length < 2) {
    suggestions.value = []
    suggestionRefs.value = {}
    return
  }

  loading.value = true
  suggestionRefs.value = {}

  try {
    const data = await $fetch<CompanySearchResult>('/api/v1/company/search', {
      method: 'GET',
      params: { q: query, limit: 10 },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    suggestions.value = data.items || []
  } catch (error) {
    console.error('Ошибка поиска компаний:', error)
    suggestions.value = []
  } finally {
    loading.value = false
  }
}

const handleFocus = () => {
  showResults.value = true
  if (!searchQuery.value || searchQuery.value === selectedValue.value) {
    suggestions.value = [...props.presetOptions]
  }
}

const formatDate = (timestamp: string | number | null | undefined): string => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleDateString('ru-RU')
}

// Форматирование имени в формат "Фамилия И.О."
const formatManagerName = (fullName: string): string => {
  if (!fullName) return ''
  const parts = fullName.trim().split(/\s+/).filter((p: string) => p)
  if (parts.length === 0) return ''
  if (parts.length === 1) return parts[0]

  const surname = parts[0]
  const initials = parts.slice(1).map((p: string) => p.charAt(0).toUpperCase() + '.').join('')
  return `${surname} ${initials}`
}

// Форматирование отображения варианта
const formatSuggestionDisplay = (suggestion: CompanySuggestion): string => {
  const inn = suggestion.inn || ''
  const managerName = suggestion.manager_name ? formatManagerName(suggestion.manager_name) : ''

  if (suggestion.entity_type === 'INDIVIDUAL' || !managerName) {
    return `${suggestion.name} (ИНН: ${inn})`
  }

  return `${suggestion.name} (ИНН: ${inn}) ${managerName}`
}

const handleKeyDown = (event: KeyboardEvent) => {
  if (!showResults.value || suggestions.value.length === 0) return

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (selectedSuggestionIndex.value === null || selectedSuggestionIndex.value >= suggestions.value.length - 1) {
      selectedSuggestionIndex.value = 0
    } else {
      selectedSuggestionIndex.value++
    }
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (selectedSuggestionIndex.value === null || selectedSuggestionIndex.value <= 0) {
      selectedSuggestionIndex.value = suggestions.value.length - 1
    } else {
      selectedSuggestionIndex.value--
    }
  } else if (event.key === 'Enter' && selectedSuggestionIndex.value !== null) {
    event.preventDefault()
    selectSuggestion(selectedSuggestionIndex.value)
  } else if (event.key === 'Escape') {
    showResults.value = false
  }
}

const handleSearch = () => {
  emit('update:modelValue', searchQuery.value)
  if (selectedValue.value && searchQuery.value !== selectedValue.value) {
    skipSelectedValueModelEmit.value = true
    selectedValue.value = ''
    selectedCompany.value = null
    emit('select', null)
    nextTick(() => {
      skipSelectedValueModelEmit.value = false
    })
  }

  if (!searchQuery.value || searchQuery.value.length < 2) {
    suggestions.value = [...props.presetOptions]
    showResults.value = suggestions.value.length > 0
    selectedSuggestionIndex.value = null
    return
  }

  showResults.value = true
  selectedSuggestionIndex.value = null

  if (searchTimeout.value) {
    clearTimeout(searchTimeout.value)
  }

  searchTimeout.value = setTimeout(() => {
    searchCompanies(searchQuery.value)
  }, 500)
}

const selectSuggestion = (index: number) => {
  attempted.value = true
  selectedSuggestionIndex.value = index

  if (suggestions.value[index]) {
    const suggestion = suggestions.value[index]
    selectedCompany.value = suggestion

    // Формируем строку для отправки в parent компонент
    const displayValue = formatSuggestionDisplay(suggestion)
    searchQuery.value = displayValue
    selectedValue.value = displayValue
    emit('select', suggestion)

    showResults.value = false
  }
}

onBeforeUnmount(() => {
  if (searchTimeout.value) {
    clearTimeout(searchTimeout.value)
  }
})
</script>
