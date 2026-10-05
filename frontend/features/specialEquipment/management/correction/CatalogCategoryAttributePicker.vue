<template>
  <div class="se-category-attribute-picker" :aria-busy="loading">
    <label class="se-field">
      <span>Группа характеристик</span>
      <select
        ref="groupSelect"
        v-model="selectedGroupKey"
        class="select-field"
        :disabled="loading || Boolean(errorMessage) || availableAttributes.length === 0"
        @change="changeGroup"
      >
        <option value="">Сначала выберите группу</option>
        <option v-for="group in selectableGroups" :key="group.id" :value="group.id">
          {{ group.name }}
        </option>
        <option v-if="hasUngroupedAttributes" value="ungrouped">Прочие</option>
      </select>
    </label>

    <div v-if="loading" class="se-attribute-picker-state" role="status" aria-live="polite">
      Загружаем характеристики…
    </div>
    <div v-else-if="errorMessage" class="se-attribute-picker-state se-attribute-picker-state--error" role="alert">
      <strong>Не удалось загрузить характеристики</strong>
      <span>{{ errorMessage }}</span>
      <button ref="retryButton" type="button" class="se-button se-button--secondary se-button--small" @click="requestRetry">
        Повторить
      </button>
    </div>
    <div v-else-if="availableAttributes.length === 0" class="se-quiet-state">
      Все характеристики уже добавлены или справочник пока пуст.
    </div>
    <template v-else-if="selectedGroupKey">
      <label class="se-field">
        <span>Поиск в группе</span>
        <input
          ref="searchInput"
          v-model.trim="search"
          type="search"
          autocomplete="off"
          placeholder="Найдите характеристику"
          @keydown.esc.prevent="clearSearch"
        >
      </label>

      <div v-if="filteredAttributes.length === 0" class="se-quiet-state">
        В этой группе нет доступных характеристик{{ search ? ' по вашему запросу' : '' }}.
      </div>
      <div v-else class="se-checkbox-picker__list" aria-label="Характеристики выбранной группы">
        <label v-for="attribute in filteredAttributes" :key="attribute.id">
          <input
            class="se-checkbox"
            type="checkbox"
            :checked="selectedIds.has(attribute.id)"
            @change="toggle(attribute.id)"
            @keydown.space.prevent="toggle(attribute.id)"
          >
          <span>
            <strong>{{ attribute.name }}</strong>
            <small>{{ attribute.unit || attribute.code }}</small>
          </span>
        </label>
      </div>

      <div class="se-category-attribute-picker__actions">
        <span aria-live="polite">
          {{ selectedIds.size ? `Выбрано: ${selectedIds.size}` : 'Ничего не выбрано' }}
        </span>
        <button
          type="button"
          class="se-button se-button--secondary"
          :disabled="selectedIds.size === 0"
          @click="apply"
          @keydown.enter.prevent="apply"
        >
          Применить{{ selectedIds.size ? ` (${selectedIds.size})` : '' }}
        </button>
      </div>
    </template>
    <div v-else class="se-quiet-state">
      Выберите группу, затем отметьте одну или несколько характеристик.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import type { UUID } from '~/types/ids'
import {
  applyCategoryAttributeSelection,
  beginCategoryAttributeRetry,
  createCategoryAttributePickerState,
  pruneLinkedCategoryAttributes,
  selectCategoryAttributeGroup,
  settleCategoryAttributeRetry,
  setCategoryAttributeSearch,
  toggleCategoryAttribute,
  type CategoryAttributeGroupKey,
  type CategoryAttributePickerState,
} from './categoryAttributePickerState'
import type { CatalogAttribute, CatalogAttributeGroup } from './types'

const props = withDefaults(defineProps<{
  attributes: CatalogAttribute[]
  groups: CatalogAttributeGroup[]
  linkedAttributeIds: UUID[]
  loading?: boolean
  errorMessage?: string
}>(), {
  loading: false,
  errorMessage: '',
})
const emit = defineEmits<{
  apply: [attributeIds: UUID[]]
  retry: []
}>()

const interaction = reactive(createCategoryAttributePickerState())
const replaceInteraction = (state: CategoryAttributePickerState) => Object.assign(interaction, state)
const selectedGroupKey = computed<CategoryAttributeGroupKey>({
  get: () => interaction.selectedGroupKey,
  set: value => { interaction.selectedGroupKey = value },
})
const search = computed({
  get: () => interaction.search,
  set: value => replaceInteraction(setCategoryAttributeSearch(interaction, value)),
})
const selectedIds = computed(() => new Set(interaction.selectedIds))
const groupSelect = ref<HTMLSelectElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const retryButton = ref<HTMLButtonElement | null>(null)

const availableAttributes = computed(() => {
  const linkedIds = new Set(props.linkedAttributeIds)
  return props.attributes.filter(attribute => !linkedIds.has(attribute.id))
})
const selectableGroups = computed(() => {
  const availableGroupIds = new Set(availableAttributes.value.flatMap(attribute =>
    attribute.attribute_group_id ? [attribute.attribute_group_id] : []))
  return props.groups.filter(group => availableGroupIds.has(group.id))
})
const hasUngroupedAttributes = computed(() =>
  availableAttributes.value.some(attribute => !attribute.attribute_group_id))
const groupAttributes = computed(() => {
  if (!selectedGroupKey.value) return []
  if (selectedGroupKey.value === 'ungrouped') {
    return availableAttributes.value.filter(attribute => !attribute.attribute_group_id)
  }
  return availableAttributes.value.filter(attribute =>
    attribute.attribute_group_id === selectedGroupKey.value)
})
const filteredAttributes = computed(() => {
  const query = search.value.toLocaleLowerCase('ru-RU')
  if (!query) return groupAttributes.value
  return groupAttributes.value.filter(attribute =>
    `${attribute.name} ${attribute.code} ${attribute.unit ?? ''}`
      .toLocaleLowerCase('ru-RU')
      .includes(query))
})

const focusRequestedControl = async () => {
  await nextTick()
  if (interaction.requestedFocus === 'search') searchInput.value?.focus()
  else if (interaction.requestedFocus === 'retry') retryButton.value?.focus()
  else if (interaction.requestedFocus === 'group') groupSelect.value?.focus()
}
const changeGroup = async () => {
  replaceInteraction(selectCategoryAttributeGroup(interaction, selectedGroupKey.value))
  await focusRequestedControl()
}
const clearSearch = () => {
  replaceInteraction(setCategoryAttributeSearch(interaction, ''))
}
const toggle = (attributeId: UUID) => {
  replaceInteraction(toggleCategoryAttribute(interaction, attributeId))
}
const apply = async () => {
  if (interaction.selectedIds.length === 0) return
  const result = applyCategoryAttributeSelection(interaction)
  emit('apply', result.attributeIds)
  replaceInteraction(result.state)
  await focusRequestedControl()
}
const requestRetry = () => {
  replaceInteraction(beginCategoryAttributeRetry(interaction))
  emit('retry')
}

watch(
  () => props.linkedAttributeIds,
  (linkedAttributeIds) => {
    replaceInteraction(pruneLinkedCategoryAttributes(interaction, linkedAttributeIds))
    if (selectedGroupKey.value && groupAttributes.value.length === 0) {
      replaceInteraction(selectCategoryAttributeGroup(interaction, ''))
    }
  },
  { deep: true },
)
watch(
  () => [props.loading, props.errorMessage] as const,
  async ([loading, errorMessage], [wasLoading]) => {
    if (loading || !wasLoading || !interaction.restoreFocusAfterReload) return
    replaceInteraction(settleCategoryAttributeRetry(interaction, errorMessage))
    await focusRequestedControl()
  },
  { flush: 'sync' },
)
</script>

<style scoped>
.se-category-attribute-picker { display: grid; gap: 12px; }
.se-attribute-picker-state { display: grid; gap: 8px; padding: 12px; border-radius: var(--se-radius-sm); background: hsl(var(--se-surface-muted)); }
.se-attribute-picker-state--error { color: hsl(var(--se-danger)); }
.se-attribute-picker-state .se-button { justify-self: start; }
.se-checkbox-picker__list { display: grid; max-height: 280px; gap: 2px; overflow-y: auto; }
.se-checkbox-picker__list label { display: flex; min-height: 44px; align-items: center; gap: 10px; padding: 8px; border-radius: var(--se-radius-sm); }
.se-checkbox-picker__list label:hover { background: hsl(var(--se-surface-muted)); }
.se-checkbox-picker__list label:focus-within { outline: 2px solid hsl(var(--se-primary)); outline-offset: -2px; }
.se-checkbox-picker__list span { display: grid; min-width: 0; gap: 2px; }
.se-checkbox-picker__list small { color: hsl(var(--se-muted)); }
.se-category-attribute-picker__actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.se-category-attribute-picker__actions > span { color: hsl(var(--se-muted)); font-size: 14px; }
</style>
