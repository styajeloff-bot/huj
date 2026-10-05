<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">
        {{ label }}
      </label>
      <span v-if="validationError" class="text-xs text-red-500 font-medium">
        {{ validationError }}
      </span>
    </div>

    <!-- Mode Select -->
    <select
      :value="mode"
      :disabled="disabled"
      class="select-field"
      @change="handleModeChange(($event.target as HTMLSelectElement).value)"
    >
      <option
        v-for="opt in modeOptions"
        :key="opt.value"
        :value="opt.value"
      >
        {{ opt.label }}
      </option>
    </select>

    <!-- Selected items & Search input when mode requires items -->
    <div v-if="showItemSelector" class="p-3 bg-gray-50 border border-gray-200 rounded-md space-y-2">
      <!-- Chips of selected items -->
      <div v-if="items.length > 0" class="flex flex-wrap gap-1.5">
        <span
          v-for="item in items"
          :key="item.id"
          class="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-blue-50 text-blue-800 text-xs font-medium border border-blue-200"
        >
          <span>{{ item.name }}</span>
          <button
            v-if="!disabled"
            type="button"
            class="text-blue-500 hover:text-blue-700 focus:outline-none ml-0.5"
            :title="`Удалить ${item.name}`"
            @click="removeItem(item.id)"
          >
            &times;
          </button>
        </span>
      </div>
      <div v-else class="text-xs text-gray-400 italic">
        {{ emptyHint || 'Объекты не выбраны' }}
      </div>

      <!-- Search & Add Input -->
      <div v-if="!disabled" ref="containerRef" class="relative mt-2">
        <div class="relative">
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="placeholder || 'Поиск для добавления...'"
            class="storefront-control block w-full px-3 py-1.5 text-xs border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
            @focus="handleFocus"
            @input="handleInput"
            @keydown.down.prevent="navigateResults(1)"
            @keydown.up.prevent="navigateResults(-1)"
            @keydown.enter.prevent="selectHighlighted"
            @keydown.esc="closeDropdown"
          />
          <span
            v-if="isSearching"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-gray-400 animate-pulse"
          >
            Поиск...
          </span>
        </div>

        <!-- Autocomplete Dropdown -->
        <div
          v-if="isOpen"
          class="absolute z-20 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto"
        >
          <div
            v-if="searchResults.length === 0 && !isSearching"
            class="px-3 py-2 text-xs text-gray-500 text-center"
          >
            {{ searchQuery ? 'Ничего не найдено' : 'Начните ввод для поиска' }}
          </div>
          <button
            v-for="(res, index) in searchResults"
            :key="res.id"
            type="button"
            :class="[
              'w-full text-left px-3 py-2 text-xs transition-colors flex items-center justify-between',
              index === highlightedIndex ? 'bg-blue-50 text-blue-900 font-medium' : 'text-gray-700 hover:bg-gray-50'
            ]"
            @click="addItem(res)"
            @mouseenter="highlightedIndex = index"
          >
            <span>{{ res.name }}</span>
            <span v-if="res.description" class="text-gray-400 text-[10px] ml-2">
              {{ res.description }}
            </span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
export interface ObjectOptionItem {
  id: string
  name: string
  description?: string | null
}

export interface ModeOption {
  value: string
  label: string
}

const props = withDefaults(
  defineProps<{
    label: string
    mode: string
    modeOptions: ModeOption[]
    items: ObjectOptionItem[]
    disabled?: boolean
    placeholder?: string
    emptyHint?: string
    validationError?: string
    fetchLookup: (query: string) => Promise<ObjectOptionItem[]>
  }>(),
  {
    disabled: false,
    placeholder: 'Поиск для добавления...',
    emptyHint: 'Объекты не выбраны',
    validationError: '',
  },
)

const emit = defineEmits<{
  (e: 'update:mode', value: string): void
  (e: 'update:items', value: ObjectOptionItem[]): void
}>()

const showItemSelector = computed(() => {
  return (
    props.mode === 'selected' ||
    props.mode === 'except_selected' ||
    props.mode === 'own_and_selected'
  )
})

const containerRef = ref<HTMLElement | null>(null)
const searchQuery = ref('')
const isSearching = ref(false)
const searchResults = ref<ObjectOptionItem[]>([])
const isOpen = ref(false)
const highlightedIndex = ref(-1)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

const handleModeChange = (newMode: string) => {
  emit('update:mode', newMode)
}

const removeItem = (id: string) => {
  emit(
    'update:items',
    props.items.filter((item) => item.id !== id),
  )
}

const addItem = (item: ObjectOptionItem) => {
  if (!props.items.some((i) => i.id === item.id)) {
    emit('update:items', [...props.items, item])
  }
  searchQuery.value = ''
  searchResults.value = []
  isOpen.value = false
  highlightedIndex.value = -1
}

const performSearch = async (query: string) => {
  isSearching.value = true
  try {
    const results = await props.fetchLookup(query)
    // Filter out already selected items
    const selectedIds = new Set(props.items.map((i) => i.id))
    searchResults.value = results.filter((r) => !selectedIds.has(r.id))
    isOpen.value = true
    highlightedIndex.value = -1
  } catch (err) {
    searchResults.value = []
  } finally {
    isSearching.value = false
  }
}

const handleInput = () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    performSearch(searchQuery.value)
  }, 250)
}

const handleFocus = () => {
  if (!isOpen.value) {
    performSearch(searchQuery.value)
  }
}

const closeDropdown = () => {
  isOpen.value = false
  highlightedIndex.value = -1
}

const navigateResults = (direction: number) => {
  if (!isOpen.value || searchResults.value.length === 0) return
  highlightedIndex.value =
    (highlightedIndex.value + direction + searchResults.value.length) %
    searchResults.value.length
}

const selectHighlighted = () => {
  if (
    isOpen.value &&
    highlightedIndex.value >= 0 &&
    highlightedIndex.value < searchResults.value.length
  ) {
    addItem(searchResults.value[highlightedIndex.value])
  }
}

const handleDocumentClick = (event: MouseEvent) => {
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    closeDropdown()
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
})

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
  document.removeEventListener('click', handleDocumentClick)
})
</script>
