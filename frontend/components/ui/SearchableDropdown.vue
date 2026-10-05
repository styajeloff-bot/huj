<template>
  <div data-storefront-block="shared.menu" class="relative" ref="dropdownRef">
    <label v-if="label" class="filter-label">{{ label }}</label>
    <button
      type="button"
      ref="controlRef"
      class="storefront-action-ghost w-full hero-filter-btn rounded-lg"
      :class="{ 'hero-filter-btn-active': hasValue, 'opacity-50 cursor-not-allowed': disabled, 'ring-2 ring-[color:var(--storefront-ghost-border,#ef4444)]': error }"
      :disabled="disabled"
      @click="toggleDropdown"
    >
      <span class="truncate flex-1 text-left">{{ selectedText }}</span>
      <svg class="w-4 h-4 flex-shrink-0 transition-transform" :class="{ 'rotate-180': showDropdown }"
        fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <Teleport :to="teleportTo">
      <Transition name="dropdown">
        <div
          v-if="showDropdown"
          ref="dropdownMenuRef"
          class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-xl border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden"
          :style="dropdownStyle"
        >
          <div v-if="searchable" class="p-2 border-b border-[color:var(--storefront-border,#f3f4f6)]">
            <div class="relative">
              <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[color:var(--storefront-icon,#9ca3af)]" fill="none"
                stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input v-model="searchQuery" type="text" :placeholder="searchPlaceholder"
                class="storefront-control w-full pl-9 pr-3 py-2 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg text-sm focus:ring-2 focus:border-transparent"
                style="--tw-ring-color: var(--storefront-primary,#3367bd);" @keydown.stop />
            </div>
          </div>
          <div class="overflow-y-auto custom-scrollbar" :style="dropdownListStyle">
            <button
              v-if="allowClear && !multiple"
              type="button"
              class="storefront-action-ghost w-full text-left px-3 py-2 text-sm hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] transition-colors"
              :class="{ 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]': modelValue === null || modelValue === undefined || modelValue === '' }"
              @click="selectValue(null)"
            >
              {{ clearLabel }}
            </button>
            <label
              v-if="!loading && multiple && showSelectAll && filteredItems.length > 0"
              class="flex items-center gap-2 px-3 py-2 hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] cursor-pointer text-sm transition-colors border-b border-[color:var(--storefront-border,#f3f4f6)]"
              :class="{ 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]': allFilteredSelected }"
            >
              <input
                type="checkbox"
                :checked="allFilteredSelected"
                @change="toggleAllFiltered"
                class="storefront-control w-4 h-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
              />
              <span class="flex-1 font-medium" :style="allFilteredSelected ? 'color: var(--storefront-link,#3367bd);' : ''">
                {{ selectAllLabel }}
              </span>
            </label>
            <template v-for="item in loading ? [] : filteredItems">
              <label
                v-if="multiple"
                :key="getItemValue(item)"
                class="flex items-center gap-2 px-3 py-2 hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] cursor-pointer text-sm transition-colors"
                :class="{ 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]': isSelected(getItemValue(item)) }"
              >
                <input
                  type="checkbox"
                  :checked="isSelected(getItemValue(item))"
                  @change="toggleValue(getItemValue(item))"
                  class="storefront-control w-4 h-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                />
                <span class="flex-1" :style="isSelected(getItemValue(item)) ? 'color: var(--storefront-link,#3367bd);' : ''"
                  v-html="highlightMatch(getItemLabel(item), searchQuery)"></span>
              </label>
              <button
                v-else
                :key="getItemValue(item)"
                type="button"
                class="w-full text-left px-3 py-2 text-sm hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] transition-colors"
                :class="{ 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]': isSelected(getItemValue(item)) }"
                @click="selectValue(getItemValue(item))"
              >
                <span v-html="highlightMatch(getItemLabel(item), searchQuery)"></span>
              </button>
            </template>
            <div v-if="loading" role="status" class="px-3 py-4 text-center text-[color:var(--storefront-text-muted,#9ca3af)] text-sm">Загрузка…</div>
            <div v-else-if="filteredItems.length === 0" class="px-3 py-4 text-center text-[color:var(--storefront-text-muted,#9ca3af)] text-sm">
              {{ emptyLabel }}
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { DropdownItem } from '@/types'

const props = defineProps({
  teleportTo: {
    type: [String, Object] as PropType<string | HTMLElement>,
    default: 'body'
  },
  modelValue: {
    type: [String, Number, Array, Object] as PropType<string | number | Array<string | number> | Record<string, unknown> | null>,
    default: null
  },
  items: {
    type: Array as PropType<DropdownItem[]>,
    default: () => []
  },
  selectedItems: {
    type: Array as PropType<DropdownItem[]>,
    default: () => []
  },
  anchorToControl: {
    type: Boolean,
    default: false
  },
  loading: {
    type: Boolean,
    default: false
  },
  emptyLabel: {
    type: String,
    default: 'Ничего не найдено'
  },
  remote: {
    type: Boolean,
    default: false
  },
  remoteDebounceMs: {
    type: Number,
    default: 300
  },
  label: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: 'Выберите значение'
  },
  labelKey: {
    type: String,
    default: 'name'
  },
  valueKey: {
    type: String,
    default: 'id'
  },
  multiple: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  searchable: {
    type: Boolean,
    default: true
  },
  allowClear: {
    type: Boolean,
    default: true
  },
  clearLabel: {
    type: String,
    default: 'Все'
  },
  searchPlaceholder: {
    type: String,
    default: 'Найти...'
  },
  error: {
    type: Boolean,
    default: false
  },
  showSelectAll: {
    type: Boolean,
    default: false
  },
  selectAllLabel: {
    type: String,
    default: 'Выбрать все'
  },
  searchKeys: {
    type: Array as PropType<string[]>,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'search'])

const dropdownRef = ref<HTMLElement | null>(null)
const controlRef = ref<HTMLButtonElement | null>(null)
const dropdownMenuRef = ref<HTMLElement | null>(null)
const showDropdown = ref(false)
const searchQuery = ref('')
const dropdownStyle = ref<Record<string, string>>({})
const dropdownListStyle = ref<Record<string, string>>({})

const dropdownGap = 4
const viewportPadding = 12
const defaultDropdownHeight = 320
const searchAreaHeight = 58

const getItemValue = (item: DropdownItem): string | number => {
  return item[props.valueKey] as string | number
}

const getItemLabel = (item: DropdownItem): string | number => {
  return item[props.labelKey] as string | number
}

const getSearchableText = (item: DropdownItem): string => {
  const keys = props.searchKeys.length > 0 ? props.searchKeys : [props.labelKey]
  return keys
    .map((key) => item[key])
    .filter((value) => value !== null && value !== undefined)
    .map((value) => String(value))
    .join(' ')
}

const hasValue = computed(() => {
  if (props.multiple) return Array.isArray(props.modelValue) && props.modelValue.length > 0
  return props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== ''
})

const selectedText = computed(() => {
  const displayItems = [...new Map(
    [...props.selectedItems, ...props.items].map(item => [getItemValue(item), item])
  ).values()]
  if (props.multiple) {
    const modelArr = (Array.isArray(props.modelValue) ? props.modelValue : []) as Array<string | number>
    const selectedItems = displayItems.filter(item => modelArr.includes(getItemValue(item)))
    if (selectedItems.length === 0) return props.placeholder
    if (selectedItems.length <= 2) return selectedItems.map(item => getItemLabel(item)).join(', ')
    return `${selectedItems.length} выбрано`
  }
  const selected = displayItems.find(item => getItemValue(item) === props.modelValue)
  return selected ? getItemLabel(selected) : props.placeholder
})

const filteredItems = computed(() => {
  if (props.remote) return props.items
  if (!searchQuery.value) return props.items
  const query = searchQuery.value.toLowerCase()
  return props.items.filter((item: DropdownItem) => getSearchableText(item).toLowerCase().includes(query))
})

const allFilteredSelected = computed(() => {
  if (!props.multiple || filteredItems.value.length === 0) return false
  const current = Array.isArray(props.modelValue) ? props.modelValue : []
  return filteredItems.value.every(item => current.includes(getItemValue(item)))
})

const updateDropdownPosition = () => {
  const anchor = props.anchorToControl ? controlRef.value : dropdownRef.value
  if (!anchor) return
  const rect = anchor.getBoundingClientRect()
  const viewportHeight = window.innerHeight
  const viewportWidth = window.innerWidth
  const spaceBelow = viewportHeight - rect.bottom - viewportPadding
  const spaceAbove = rect.top - viewportPadding
  const openUp = spaceBelow < defaultDropdownHeight && spaceAbove > spaceBelow
  const availableSpace = Math.max(
    openUp ? spaceAbove - dropdownGap : spaceBelow - dropdownGap,
    0
  )
  const maxHeight = Math.min(defaultDropdownHeight, availableSpace)
  const maxWidth = Math.max(viewportWidth - viewportPadding * 2, 0)
  const left = Math.min(
    Math.max(rect.left, viewportPadding),
    Math.max(viewportWidth - rect.width - viewportPadding, viewportPadding)
  )

  dropdownStyle.value = {
    position: 'fixed',
    top: openUp ? 'auto' : `${rect.bottom + dropdownGap}px`,
    bottom: openUp ? `${viewportHeight - rect.top + dropdownGap}px` : 'auto',
    left: `${left}px`,
    width: `${rect.width}px`,
    maxWidth: `${maxWidth}px`,
    maxHeight: `${maxHeight}px`,
    zIndex: '9999'
  }
  dropdownListStyle.value = {
    maxHeight: `${Math.max(maxHeight - (props.searchable ? searchAreaHeight : 0), 0)}px`
  }
}

const toggleDropdown = () => {
  if (props.disabled) return
  showDropdown.value = !showDropdown.value
  if (showDropdown.value) {
    nextTick(updateDropdownPosition)
  }
}

const closeDropdown = () => {
  showDropdown.value = false
  searchQuery.value = ''
}

const isSelected = (value: string | number) => {
  if (props.multiple) return ((Array.isArray(props.modelValue) ? props.modelValue : []) as Array<string | number>).includes(value)
  return props.modelValue === value
}

const toggleValue = (value: string | number) => {
  const current = Array.isArray(props.modelValue) ? [...props.modelValue] : []
  if (current.includes(value)) {
    emit('update:modelValue', current.filter(v => v !== value))
  } else {
    emit('update:modelValue', [...current, value])
  }
}

const toggleAllFiltered = () => {
  const current = Array.isArray(props.modelValue) ? [...props.modelValue] : []
  const values = filteredItems.value.map(item => getItemValue(item))
  if (values.every(value => current.includes(value))) {
    emit('update:modelValue', current.filter(value => !values.includes(value)))
    return
  }
  emit('update:modelValue', Array.from(new Set([...current, ...values])))
}

const selectValue = (value: string | number | null) => {
  emit('update:modelValue', value)
  closeDropdown()
}

const highlightMatch = (text: string | number | unknown, query: string) => {
  if (!query) return text
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return String(text).replace(new RegExp(escaped, 'gi'), match => `<mark class="bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))]">${match}</mark>`)
}

const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as Node | null
  const clickedInAnchor = dropdownRef.value && dropdownRef.value.contains(target)
  const clickedInMenu = dropdownMenuRef.value && dropdownMenuRef.value.contains(target)

  if (!clickedInAnchor && !clickedInMenu) closeDropdown()
}

onMounted(() => {
  // Modal dialogs stop bubbling clicks; capture still observes clicks outside
  // the control/menu when the menu is teleported into a modal's form.
  document.addEventListener('click', handleClickOutside, true)
})

watch(showDropdown, (value) => {
  if (value) {
    updateDropdownPosition()
    window.addEventListener('resize', updateDropdownPosition)
    window.addEventListener('scroll', updateDropdownPosition, true)
    if (props.remote) {
      emit('search', searchQuery.value || '')
    }
  } else {
    window.removeEventListener('resize', updateDropdownPosition)
    window.removeEventListener('scroll', updateDropdownPosition, true)
  }
})

let remoteSearchTimeout: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, (value) => {
  if (!props.remote) return
  if (remoteSearchTimeout) clearTimeout(remoteSearchTimeout)
  remoteSearchTimeout = setTimeout(() => {
    emit('search', value || '')
  }, props.remoteDebounceMs)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside, true)
  window.removeEventListener('resize', updateDropdownPosition)
  window.removeEventListener('scroll', updateDropdownPosition, true)
  if (remoteSearchTimeout) clearTimeout(remoteSearchTimeout)
})
</script>

<style scoped>
.filter-label {
  display: block;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--storefront-label,#6b7280);
  margin-bottom: 0.25rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.hero-filter-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.55rem 0.75rem;
  border: 1px solid var(--storefront-border,#e5e7eb);
  border-radius: 0.5rem;
  background: var(--storefront-surface,#fff);
  font-size: 0.875rem;
  color: var(--storefront-text,#111827);
  transition: all 0.2s ease;
}

.hero-filter-btn:hover {
  border-color: var(--storefront-border,#cbd5f5);
  background: var(--storefront-surface,#f8fafc);
}

.hero-filter-btn-active {
  border-color: var(--storefront-primary, #3367bd);
  background: var(--storefront-primary-muted, rgba(51, 103, 189, 0.08));
  color: var(--storefront-primary, #1f3f7a);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgb(var(--storefront-border-rgb,148 163 184) / 0.5);
  border-radius: 9999px;
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
