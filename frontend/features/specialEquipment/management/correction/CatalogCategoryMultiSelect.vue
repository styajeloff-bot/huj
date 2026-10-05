<template>
  <div class="se-category-multiselect">
    <button
      ref="trigger"
      type="button"
      class="se-category-picker-trigger"
      :aria-expanded="open"
      :aria-required="required"
      :disabled="disabled"
      @click="openPicker"
    >
      <span>{{ summary }}</span>
      <ChevronDownIcon aria-hidden="true" />
    </button>

    <Teleport to="body">
      <div v-if="open" class="se-category-picker-wrap" @keydown="handleKeydown">
        <button type="button" class="se-category-picker-overlay" tabindex="-1" aria-label="Закрыть выбор категорий" @click="closePicker" />
        <section
          ref="dialog"
          class="se-category-picker"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
        >
          <header>
            <div>
              <p>Связи каталога</p>
              <h3 :id="titleId">{{ title }}</h3>
            </div>
            <button type="button" class="se-icon-button" aria-label="Закрыть выбор категорий" @click="closePicker">
              <XMarkIcon aria-hidden="true" />
            </button>
          </header>
          <div class="se-category-picker__body">
            <label class="se-search">
              <MagnifyingGlassIcon aria-hidden="true" />
              <span class="sr-only">Поиск категории</span>
              <input ref="searchInput" v-model="search" type="search" placeholder="Найти категорию">
            </label>
            <p v-if="filteredPlacements.length === 0" class="se-quiet-state">Подходящих категорий нет.</p>
            <div v-else class="se-category-checks">
              <label
                v-for="placement in filteredPlacements"
                :key="placement.key"
                class="se-checkbox-row se-category-check"
                :style="{ paddingLeft: categoryIndent(placement.depth) }"
              >
                <input
                  class="se-checkbox"
                  type="checkbox"
                  :checked="pendingValue.includes(placement.category.id)"
                  :disabled="disabledIds?.includes(placement.category.id) && !pendingValue.includes(placement.category.id)"
                  @change="toggle(placement.category.id)"
                >
                <span>
                  <strong>{{ placement.category.name }}</strong>
                  <small>
                    {{ placement.pathNames.join(' → ') }}
                    · {{ placement.category.code }}
                    · {{ placement.category.usage_metric === 'mileage_km' ? 'Пробег' : 'Моточасы' }}
                    <template v-if="placement.category.is_active === false"> · Неактивна — снимите выбор</template>
                  </small>
                </span>
              </label>
            </div>
          </div>
          <footer>
            <button type="button" class="se-button se-button--secondary" @click="pendingValue = []">Очистить</button>
            <button type="button" class="se-button se-button--primary" @click="applyAndClose">Готово</button>
          </footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import {
  ChevronDownIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type { CatalogCategory } from './types'

const props = withDefaults(defineProps<{
  modelValue: UUID[]
  categories: CatalogCategory[]
  title?: string
  disabledIds?: UUID[]
  allowedIds?: UUID[]
  required?: boolean
  disabled?: boolean
}>(), {
  title: 'Выберите категории',
  disabledIds: () => [],
  required: false,
  disabled: false,
})
const emit = defineEmits<{ 'update:modelValue': [value: UUID[]] }>()
const open = ref(false)
const search = ref('')
const trigger = ref<HTMLButtonElement | null>(null)
const dialog = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const pendingValue = ref<UUID[]>([])
const titleId = `category-picker-${useId()}`
const focusTrigger = () => trigger.value?.focus()
defineExpose({ focusTrigger })
let previousOverflow = ''
let backgroundDrawer: HTMLElement | null = null
let drawerWasInert = false
let drawerAriaHidden: string | null = null

const selectedNames = computed(() => props.categories
  .filter(category => props.modelValue.includes(category.id))
  .map(category => category.name))
const summary = computed(() => selectedNames.value.length
  ? selectedNames.value.length <= 2
    ? selectedNames.value.join(', ')
    : `Выбрано категорий: ${selectedNames.value.length}`
  : 'Категории не выбраны')

interface CategoryPlacement {
  key: string
  category: CatalogCategory
  depth: number
  pathNames: string[]
}

const compareCategories = (left: CatalogCategory, right: CatalogCategory): number =>
  left.sort_order - right.sort_order
  || left.name.localeCompare(right.name, 'ru')
  || left.id.localeCompare(right.id)

const categoryPlacements = computed<CategoryPlacement[]>(() => {
  const categories = [...props.categories].sort(compareCategories)
  const categoriesById = new Map(categories.map(category => [category.id, category]))
  const childrenByParent = new Map<UUID, CatalogCategory[]>()
  for (const category of categories) {
    for (const parentId of category.parent_ids) {
      if (!categoriesById.has(parentId)) continue
      const children = childrenByParent.get(parentId) ?? []
      children.push(category)
      childrenByParent.set(parentId, children)
    }
  }
  for (const children of childrenByParent.values()) children.sort(compareCategories)

  const roots = categories.filter(category =>
    category.parent_ids.every(parentId => !categoriesById.has(parentId)))
  const placements: CategoryPlacement[] = []
  const placedCategoryIds = new Set<UUID>()

  const appendBranch = (root: CatalogCategory) => {
    const pending: Array<{
      category: CatalogCategory
      pathIds: UUID[]
      pathNames: string[]
    }> = [{ category: root, pathIds: [], pathNames: [] }]

    while (pending.length > 0) {
      const current = pending.pop()
      if (!current || current.pathIds.includes(current.category.id)) continue
      const pathIds = [...current.pathIds, current.category.id]
      const pathNames = [...current.pathNames, current.category.name]
      placements.push({
        key: pathIds.join('>'),
        category: current.category,
        depth: current.pathIds.length,
        pathNames,
      })
      placedCategoryIds.add(current.category.id)

      const children = childrenByParent.get(current.category.id) ?? []
      for (let index = children.length - 1; index >= 0; index -= 1) {
        pending.push({ category: children[index]!, pathIds, pathNames })
      }
    }
  }

  for (const root of roots) appendBranch(root)
  // A malformed historical cycle must not make categories disappear from the
  // selector. The API still rejects creating new cycles.
  for (const category of categories) {
    if (!placedCategoryIds.has(category.id)) appendBranch(category)
  }
  return placements
})

const filteredPlacements = computed(() => {
  const query = search.value.trim().toLocaleLowerCase('ru-RU')
  const allowed = props.allowedIds ? new Set(props.allowedIds) : null
  const placements = allowed
    ? categoryPlacements.value.filter(placement => allowed.has(placement.category.id))
    : categoryPlacements.value
  return query
    ? placements.filter(placement =>
        `${placement.pathNames.join(' ')} ${placement.category.code}`
          .toLocaleLowerCase('ru-RU')
          .includes(query))
    : placements
})
const categoryIndent = (depth: number): string =>
  `${12 + Math.min(depth, 6) * 18}px`
const toggle = (categoryId: UUID) => {
  pendingValue.value = pendingValue.value.includes(categoryId)
    ? pendingValue.value.filter(id => id !== categoryId)
    : [...pendingValue.value, categoryId]
}
const openPicker = async () => {
  if (props.disabled) return
  pendingValue.value = [...props.modelValue]
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  backgroundDrawer = trigger.value?.closest<HTMLElement>('.se-drawer') ?? null
  if (backgroundDrawer) {
    drawerWasInert = backgroundDrawer.hasAttribute('inert')
    drawerAriaHidden = backgroundDrawer.getAttribute('aria-hidden')
    backgroundDrawer.setAttribute('inert', '')
    backgroundDrawer.setAttribute('aria-hidden', 'true')
  }
  open.value = true
  await nextTick()
  searchInput.value?.focus()
}
const restoreBackgroundDrawer = () => {
  if (!backgroundDrawer) return
  if (!drawerWasInert) backgroundDrawer.removeAttribute('inert')
  if (drawerAriaHidden === null) backgroundDrawer.removeAttribute('aria-hidden')
  else backgroundDrawer.setAttribute('aria-hidden', drawerAriaHidden)
  backgroundDrawer = null
}
const closePicker = async () => {
  open.value = false
  document.body.style.overflow = previousOverflow
  restoreBackgroundDrawer()
  await nextTick()
  trigger.value?.focus()
}
const applyAndClose = async () => {
  emit('update:modelValue', [...pendingValue.value])
  await closePicker()
}
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    event.preventDefault()
    void closePicker()
    return
  }
  if (event.key !== 'Tab' || !dialog.value) return
  const controls = [...dialog.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )]
  const first = controls[0]
  const last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}
onBeforeUnmount(() => {
  if (!open.value) return
  document.body.style.overflow = previousOverflow
  restoreBackgroundDrawer()
})
</script>

<style scoped>
.se-category-picker-trigger {
  display: flex;
  width: 100%;
  min-height: 44px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 11px;
  border: 1px solid hsl(var(--se-border-strong));
  border-radius: var(--se-radius-sm);
  background: hsl(var(--se-surface));
  color: hsl(var(--se-text));
  text-align: left;
  cursor: pointer;
}
.se-category-picker-trigger span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.se-category-picker-trigger:disabled {
  background: hsl(var(--se-surface-strong));
  color: hsl(var(--se-muted));
  cursor: not-allowed;
}
.se-category-picker-wrap { position: fixed; z-index: 190; inset: 0; display: grid; place-items: center; padding: 20px; }
.se-category-picker-overlay { position: absolute; inset: 0; border: 0; background: hsl(var(--se-text) / .42); }
.se-category-picker { position: relative; display: grid; width: min(650px, 100%); max-height: min(760px, calc(100dvh - 40px)); grid-template-rows: auto minmax(0, 1fr) auto; overflow: hidden; border-radius: var(--se-radius-lg); background: hsl(var(--se-surface)); box-shadow: 0 24px 70px hsl(var(--se-text) / .22); }
.se-category-picker header, .se-category-picker footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; }
.se-category-picker header { border-bottom: 1px solid hsl(var(--se-border)); }
.se-category-picker footer { border-top: 1px solid hsl(var(--se-border)); }
.se-category-picker header p { margin: 0; color: hsl(var(--se-primary)); font-size: 12px; font-weight: 800; text-transform: uppercase; }
.se-category-picker h3 { margin: 2px 0 0; font-size: 20px; }
.se-category-picker__body { min-height: 0; overflow-y: auto; padding: 16px 20px; }
.se-category-checks { display: grid; gap: 8px; margin-top: 14px; }
.se-category-check small { display: block; overflow-wrap: anywhere; }
</style>
