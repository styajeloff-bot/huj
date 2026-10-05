<template>
  <div ref="root" class="se-searchable-select" @focusout="handleFocusOut">
    <div class="se-searchable-select__control">
      <MagnifyingGlassIcon aria-hidden="true" />
      <input
        v-model="search"
        type="search"
        role="combobox"
        autocomplete="off"
        :aria-label="label"
        :aria-expanded="open"
        :aria-controls="listboxId"
        :aria-activedescendant="activeOptionId"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        :aria-required="required"
        @focus="openList"
        @input="handleSearchInput"
        @keydown.down.prevent="moveActive(1)"
        @keydown.up.prevent="moveActive(-1)"
        @keydown.enter.prevent="selectActive"
        @keydown.esc.prevent="closeList"
      >
      <button
        v-if="modelValue && !disabled"
        type="button"
        class="se-searchable-select__clear"
        :aria-label="`Очистить поле «${label}»`"
        @click="clear"
      >
        <XMarkIcon aria-hidden="true" />
      </button>
    </div>

    <ul
      v-if="open"
      :id="listboxId"
      class="se-searchable-select__options"
      role="listbox"
      :aria-label="label"
    >
      <li v-if="filteredOptions.length === 0" class="se-searchable-select__empty">
        Ничего не найдено
      </li>
      <li v-for="(option, index) in filteredOptions" :key="option.id">
        <button
          :id="optionId(option.id)"
          type="button"
          role="option"
          :aria-selected="option.id === modelValue"
          :disabled="option.is_active === false"
          :class="{ 'se-searchable-select__option--active': index === activeIndex }"
          @mousedown.prevent
          @click="select(option.id)"
        >
          <span>{{ option.name }}</span>
          <small v-if="option.code">{{ option.code }}</small>
          <small v-if="option.is_active === false">Неактивно</small>
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type { CatalogNamedRef } from './types'

const props = withDefaults(defineProps<{
  modelValue: UUID | ''
  options: CatalogNamedRef[]
  label: string
  placeholder?: string
  disabled?: boolean
  required?: boolean
}>(), {
  placeholder: 'Начните вводить название',
  disabled: false,
  required: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: UUID | '']
  change: [value: UUID | null]
}>()

const root = ref<HTMLElement | null>(null)
const open = ref(false)
const activeIndex = ref(-1)
const listboxId = `catalog-searchable-${useId()}`
const selectedOption = computed(() => props.options.find(option => option.id === props.modelValue) ?? null)
const search = ref(selectedOption.value?.name ?? '')
const normalizedSearch = computed(() => search.value.trim().toLocaleLowerCase('ru-RU'))
const filteredOptions = computed(() => props.options.filter(option => {
  if (!normalizedSearch.value) return true
  return option.name.toLocaleLowerCase('ru-RU').includes(normalizedSearch.value)
    || option.code?.toLocaleLowerCase('ru-RU').includes(normalizedSearch.value)
}))
const activeOptionId = computed(() => {
  const option = filteredOptions.value[activeIndex.value]
  return option ? optionId(option.id) : undefined
})

watch(
  () => [props.modelValue, props.options] as const,
  () => {
    if (!open.value) search.value = selectedOption.value?.name ?? ''
  },
  { deep: true },
)
watch(filteredOptions, () => { activeIndex.value = filteredOptions.value.length > 0 ? 0 : -1 })

const optionId = (id: UUID): string => `${listboxId}-${id}`
const openList = () => {
  if (props.disabled) return
  open.value = true
  activeIndex.value = Math.max(0, filteredOptions.value.findIndex(option => option.id === props.modelValue))
}
const closeList = () => {
  open.value = false
  activeIndex.value = -1
  search.value = selectedOption.value?.name ?? ''
}
const select = (id: UUID) => {
  const option = props.options.find(item => item.id === id)
  if (option?.is_active === false) return
  emit('update:modelValue', id)
  emit('change', id)
  search.value = option?.name ?? ''
  open.value = false
}
const clear = () => {
  search.value = ''
  emit('update:modelValue', '')
  emit('change', null)
  openList()
}
const handleSearchInput = () => {
  openList()
}
const moveActive = (direction: -1 | 1) => {
  if (!open.value) openList()
  const count = filteredOptions.value.length
  if (!count) return
  activeIndex.value = (activeIndex.value + direction + count) % count
}
const selectActive = () => {
  const option = filteredOptions.value[activeIndex.value]
  if (option) select(option.id)
}
const handleFocusOut = async () => {
  await nextTick()
  if (!root.value?.contains(document.activeElement)) closeList()
}
</script>

<style scoped>
.se-searchable-select { position: relative; min-width: 0; }
.se-searchable-select__control { position: relative; display: flex; min-width: 0; align-items: center; }
.se-searchable-select__control > svg:first-child {
  position: absolute;
  left: 12px;
  width: 18px;
  height: 18px;
  color: hsl(var(--se-muted));
  pointer-events: none;
}
.se-searchable-select .se-searchable-select__control input[type="search"] {
  width: 100%;
  min-width: 0;
  padding: 9px 42px 9px 38px;
}
.se-searchable-select__clear {
  position: absolute;
  right: 4px;
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 8px;
  color: hsl(var(--se-muted));
}
.se-searchable-select__clear:hover { background: hsl(var(--se-surface-muted)); color: hsl(var(--se-text)); }
.se-searchable-select__clear svg { width: 18px; height: 18px; }
.se-searchable-select__options {
  position: absolute;
  z-index: 20;
  top: calc(100% + 6px);
  right: 0;
  left: 0;
  max-height: 260px;
  overflow-y: auto;
  margin: 0;
  padding: 6px;
  list-style: none;
  border: 1px solid hsl(var(--se-border));
  border-radius: var(--se-radius-sm);
  background: hsl(var(--se-surface));
  box-shadow: 0 16px 35px rgb(15 23 42 / 14%);
}
.se-searchable-select__options button {
  display: flex;
  width: 100%;
  min-height: 44px;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  text-align: left;
}
.se-searchable-select__options button:hover,
.se-searchable-select__option--active { background: hsl(var(--se-surface-muted)); }
.se-searchable-select__options button span { min-width: 0; flex: 1; }
.se-searchable-select__options small { color: hsl(var(--se-muted)); }
.se-searchable-select__empty { padding: 12px; color: hsl(var(--se-muted)); font-size: 14px; }
</style>
