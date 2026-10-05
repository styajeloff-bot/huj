<template>
  <div data-storefront-block="equipment.filters.dialog" class="min-w-0 text-storefront-text">
    <p :class="labelClasses">{{ label }}</p>
    <button
      ref="trigger"
      type="button"
      :class="triggerClasses"
      aria-haspopup="dialog"
      :aria-expanded="isOpen"
      :aria-controls="dialogId"
      :aria-describedby="disabled ? disabledDescriptionId : undefined"
      :disabled="disabled"
      @click="open"
    >
      <span class="min-w-0 truncate">{{ triggerLabel }}</span>
      <span
        v-if="modelValue.length"
        class="shrink-0 rounded-full bg-storefront-selected px-2 py-0.5 text-xs tabular-nums text-storefront-link"
        aria-hidden="true"
      >
        {{ modelValue.length }}
      </span>
      <ChevronDownIcon v-else class="h-4 w-4 shrink-0 text-storefront-icon-muted" aria-hidden="true" />
    </button>
    <p v-if="disabled && disabledReason" :id="disabledDescriptionId" class="sr-only">
      {{ disabledReason }}
    </p>

    <dialog
      :id="dialogId"
      ref="dialogElement"
      class="special-equipment-facet-dialog inset-0 m-auto h-auto max-h-[min(42rem,calc(100dvh-2rem))] w-full max-w-lg overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface p-0 text-storefront-text storefront-shadow-2xl"
      :aria-labelledby="titleId"
      @cancel.prevent="cancel"
      @click="handleBackdropClick"
      @keydown.stop
      @close="handleNativeClose"
    >
      <div class="flex min-h-0 max-h-[min(42rem,calc(100dvh-2rem))] flex-col">
        <header class="flex shrink-0 items-center justify-between gap-3 border-b border-storefront-border px-5 py-3">
          <div class="min-w-0">
            <h2 :id="titleId" class="truncate text-lg font-bold text-storefront-title">{{ label }}</h2>
            <p class="mt-0.5 text-xs text-storefront-text-muted" aria-live="polite">
              Выбрано: {{ draftSelection.length }}
            </p>
          </div>
          <button
            type="button"
            class="grid min-h-11 min-w-11 shrink-0 place-items-center rounded-lg border border-storefront-border text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
            :aria-label="`Закрыть выбор: ${label.toLocaleLowerCase('ru-RU')}`"
            @click="cancel"
          >
            <XMarkIcon class="h-5 w-5 text-storefront-icon" aria-hidden="true" />
          </button>
        </header>

        <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
          <label class="relative block">
            <MagnifyingGlassIcon class="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-storefront-icon-muted" aria-hidden="true" />
            <span class="sr-only">Поиск: {{ label.toLocaleLowerCase('ru-RU') }}</span>
            <input
              ref="searchInput"
              v-model="searchQuery"
              type="search"
              autocomplete="off"
              :placeholder="`Найти: ${label.toLocaleLowerCase('ru-RU')}`"
              class="h-11 w-full rounded-lg border border-storefront-border bg-storefront-surface pl-10 pr-3 text-base text-storefront-text placeholder:text-storefront-placeholder focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-control"
            >
          </label>

          <div v-if="visibleOptions.length" class="mt-3" role="group" :aria-label="`Варианты: ${label.toLocaleLowerCase('ru-RU')}`">
            <label
              v-for="option in visibleOptions"
              :key="option.id"
              class="grid min-h-11 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-2 text-sm text-storefront-text hover:bg-storefront-secondary-hover focus-within:bg-storefront-selected focus-within:ring-2 focus-within:ring-storefront-focus"
            >
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-storefront-border text-storefront-link focus:ring-0 storefront-control"
                :checked="draftSelection.includes(option.id)"
                @change="toggle(option.id)"
              >
              <span class="min-w-0 break-words leading-snug">{{ option.name }}</span>
              <span class="shrink-0 text-xs tabular-nums text-storefront-text-muted">{{ option.count }}</span>
            </label>
          </div>
          <p v-else class="mt-6 rounded-lg bg-storefront-background px-4 py-8 text-center text-sm text-storefront-text-muted">
            Ничего не найдено
          </p>
        </div>

        <footer class="grid shrink-0 grid-cols-[auto_1fr_auto] gap-2 border-t border-storefront-border bg-storefront-surface px-5 py-4">
          <button
            type="button"
            class="min-h-11 rounded-lg border border-storefront-border px-3 text-sm font-semibold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
            @click="reset"
          >
            Сбросить выбор
          </button>
          <button
            type="button"
            class="min-h-11 justify-self-end rounded-lg border border-storefront-border px-3 text-sm font-semibold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
            @click="cancel"
          >
            Отмена
          </button>
          <button
            type="button"
            class="col-span-1 min-h-11 rounded-lg bg-storefront-primary px-4 text-sm font-bold text-storefront-primary-foreground hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-primary"
            @click="apply"
          >
            Применить
          </button>
        </footer>
      </div>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import {
  ChevronDownIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'

export interface SpecialEquipmentFacetDialogOption {
  id: UUID
  name: string
  count: number
}

const props = defineProps<{
  label: string
  options: SpecialEquipmentFacetDialogOption[]
  modelValue: UUID[]
  disabled?: boolean
  disabledReason?: string
}>()

const emit = defineEmits<{
  apply: [value: UUID[]]
}>()

const componentId = useId()
const dialogId = `special-equipment-facet-dialog-${componentId}`
const titleId = `${dialogId}-title`
const disabledDescriptionId = `${dialogId}-disabled-description`
const trigger = ref<HTMLButtonElement | null>(null)
const dialogElement = ref<HTMLDialogElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const isOpen = ref(false)
const searchQuery = ref('')
const draftSelection = ref<UUID[]>([])

const labelClasses = computed(() => [
  'mb-2 text-sm font-semibold transition-colors',
  props.disabled ? 'text-storefront-text-muted' : 'text-storefront-text',
])

const triggerClasses = computed(() => [
  'storefront-action-secondary flex min-h-11 w-full min-w-0 items-center justify-between gap-3 rounded-lg border px-3 text-left text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus',
  props.disabled
    ? 'cursor-not-allowed border-storefront-disabled-border bg-storefront-disabled text-storefront-disabled-foreground'
    : 'border-storefront-border bg-storefront-surface text-storefront-text hover:border-storefront-secondary-hover-border hover:bg-storefront-secondary-hover',
])

const triggerLabel = computed(() => props.modelValue.length
  ? `${props.label}: выбрано ${props.modelValue.length}`
  : `Выбрать: ${props.label.toLocaleLowerCase('ru-RU')}`)

const visibleOptions = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase('ru-RU')
  if (!query) return props.options
  return props.options.filter(option => option.name.toLocaleLowerCase('ru-RU').includes(query))
})

const open = async () => {
  if (props.disabled) return
  const dialog = dialogElement.value
  if (!dialog || dialog.open) return
  draftSelection.value = [...props.modelValue]
  searchQuery.value = ''
  isOpen.value = true
  dialog.showModal()
  await nextTick()
  searchInput.value?.focus({ preventScroll: true })
}

const close = async () => {
  const dialog = dialogElement.value
  if (dialog?.open) dialog.close()
  isOpen.value = false
  await nextTick()
  trigger.value?.focus({ preventScroll: true })
}

const cancel = () => {
  draftSelection.value = [...props.modelValue]
  searchQuery.value = ''
  void close()
}

const apply = () => {
  emit('apply', [...draftSelection.value])
  searchQuery.value = ''
  void close()
}

const reset = () => {
  draftSelection.value = []
}

const toggle = (optionId: UUID) => {
  draftSelection.value = draftSelection.value.includes(optionId)
    ? draftSelection.value.filter(id => id !== optionId)
    : [...draftSelection.value, optionId]
}

const handleBackdropClick = (event: MouseEvent) => {
  if (event.target === dialogElement.value) cancel()
}

const handleNativeClose = () => {
  isOpen.value = false
}
</script>

<style scoped>
.special-equipment-facet-dialog { height: auto; max-height: min(42rem, calc(100dvh - 2rem)); }
.special-equipment-facet-dialog::backdrop { background: rgb(var(--storefront-overlay-rgb) / 45%); backdrop-filter: blur(1px); }
</style>
