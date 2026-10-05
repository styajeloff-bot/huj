<template>
  <div class="se-trim-picker">
    <div v-if="loading" class="se-quiet-state">Загрузка характеристик комплектации…</div>
    <div v-else-if="errorMessage" class="se-form-alert se-form-alert--error" role="alert">
      <strong>Не удалось загрузить кандидатов характеристик</strong>
      <p>{{ errorMessage }}</p>
      <button type="button" class="se-button se-button--secondary se-button--small" @click="emit('retry')">Повторить</button>
    </div>
    <div v-else-if="groups.length === 0" class="se-quiet-state">Для выбранной комплектации нет доступных характеристик.</div>
    <template v-else>
      <fieldset class="se-checkbox-picker">
        <legend>Группы характеристик</legend>
        <label v-for="group in groups" :key="group.group_id ?? 'ungrouped'">
          <input
            class="se-checkbox"
            type="checkbox"
            :checked="selectedGroupIds.includes(groupKey(group.group_id))"
            :disabled="groupDisabled(group)"
            @change="toggleGroup(group.group_id)"
          >
          <span>{{ group.group_name || 'Прочие' }}</span>
        </label>
      </fieldset>

      <fieldset class="se-checkbox-picker">
        <legend>Характеристики выбранных групп</legend>
        <div v-if="visibleAttributes.length === 0" class="se-quiet-state">Сначала выберите группу.</div>
        <div v-else class="se-checkbox-picker__list">
          <label v-for="attribute in visibleAttributes" :key="attribute.attribute_id">
            <input
              class="se-checkbox"
              type="checkbox"
              :checked="checkedAttributeIds.includes(attribute.attribute_id)"
              :disabled="attribute.is_available === false || (attribute.is_required && checkedAttributeIds.includes(attribute.attribute_id))"
              @change="toggleAttribute(attribute.attribute_id)"
            >
            <span>
              {{ attribute.attribute_name }}
              <small v-if="attribute.options.length">{{ attribute.options.map(option => option.name).join(', ') }}</small>
              <small v-if="!attribute.is_available">{{ blockedReason(attribute.block_reason) }}</small>
            </span>
          </label>
        </div>
      </fieldset>
      <button type="button" class="se-button se-button--secondary se-button--small" @click="apply">
        Применить
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { UUID } from '~/types/ids'
import type {
  CatalogTrimAttributeAssignment,
  CatalogTrimAttributeCandidate,
  CatalogTrimAttributeCandidateGroup,
} from './types'
import {
  initialTrimAttributeSelection,
  selectedTrimAttributeCandidates,
  trimAttributeGroupSelectionDisabled,
  toggleTrimAttributeGroupSelection,
  trimAttributeGroupKey,
} from './trimAttributePickerState'

const props = defineProps<{
  groups: CatalogTrimAttributeCandidateGroup[]
  modelValue: CatalogTrimAttributeAssignment[]
  loading?: boolean
  errorMessage?: string
}>()

const emit = defineEmits<{
  apply: [items: CatalogTrimAttributeAssignment[]]
  retry: []
}>()

const selectedGroupIds = ref<string[]>([])
const checkedAttributeIds = ref<UUID[]>([])
const groupKey = trimAttributeGroupKey
const groupDisabled = (group: CatalogTrimAttributeCandidateGroup): boolean =>
  trimAttributeGroupSelectionDisabled(group, {
    selectedGroupIds: selectedGroupIds.value,
    checkedAttributeIds: checkedAttributeIds.value,
  })

watch(
  [() => props.groups, () => props.modelValue],
  ([groups, modelValue]) => {
    const initial = initialTrimAttributeSelection(groups, modelValue)
    selectedGroupIds.value = initial.selectedGroupIds
    checkedAttributeIds.value = initial.checkedAttributeIds
  },
  { immediate: true },
)

const visibleAttributes = computed<CatalogTrimAttributeCandidate[]>(() => {
  const selected = new Set(selectedGroupIds.value)
  return props.groups
    .filter(group => selected.has(groupKey(group.group_id)))
    .flatMap(group => group.attributes)
})

const toggleGroup = (groupId: UUID | null) => {
  const selection = toggleTrimAttributeGroupSelection(props.groups, {
    selectedGroupIds: selectedGroupIds.value,
    checkedAttributeIds: checkedAttributeIds.value,
  }, groupId)
  selectedGroupIds.value = selection.selectedGroupIds
  checkedAttributeIds.value = selection.checkedAttributeIds
}

const toggleAttribute = (attributeId: UUID) => {
  const attribute = props.groups
    .flatMap(group => group.attributes)
    .find(candidate => candidate.attribute_id === attributeId)
  const selected = new Set(checkedAttributeIds.value)
  if (!attribute || attribute.is_available === false
    || (attribute.is_required && selected.has(attributeId))) return
  if (selected.has(attributeId)) selected.delete(attributeId)
  else selected.add(attributeId)
  checkedAttributeIds.value = [...selected]
}

const apply = () => {
  emit('apply', selectedTrimAttributeCandidates(
    props.groups,
    selectedGroupIds.value,
    checkedAttributeIds.value,
    props.modelValue,
  ))
}

const blockedReason = (reason: string | null): string => reason === 'ATTRIBUTE_ALREADY_USED_IN_MODIFICATION'
  ? 'Значение уже задано на уровне модификации'
  : 'Характеристика недоступна для комплектации'
</script>

<style scoped>
.se-trim-picker { display: grid; gap: 12px; }
.se-checkbox-picker legend { font-weight: 700; }
.se-checkbox-picker small { display: block; color: hsl(var(--se-muted)); }
</style>
