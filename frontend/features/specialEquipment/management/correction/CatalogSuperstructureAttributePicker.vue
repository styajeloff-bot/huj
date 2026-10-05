<template>
  <div class="se-superstructure-picker">
    <div class="se-picker-step">
      <h4>Добавление характеристик</h4>
      <div class="se-field-row">
        <label class="se-field">
          <span>Группа характеристик <b>*</b></span>
          <select
            v-model="selectedGroupId"
            :disabled="disabled || loadingCandidates"
            @change="loadCandidates"
          >
            <option value="">Выберите группу</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">
              {{ g.name }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="loadingCandidates" class="se-quiet-state">
        Загрузка характеристик группы…
      </div>

      <div v-else-if="candidateError" class="se-form-alert se-form-alert--error" role="alert">
        <p>{{ candidateError }}</p>
        <button type="button" class="se-button se-button--secondary se-button--small" @click="loadCandidates">
          Повторить
        </button>
      </div>

      <div v-else-if="selectedGroupId && unassignedCandidates.length === 0" class="se-quiet-state">
        Все характеристики этой группы уже добавлены.
      </div>

      <div v-else-if="selectedGroupId" class="se-candidates-list">
        <label
          v-for="cand in unassignedCandidates"
          :key="cand.attribute_id"
          class="se-candidate-item"
        >
          <input
            v-model="selectedCandidateIds"
            class="se-checkbox"
            type="checkbox"
            :value="cand.attribute_id"
            :disabled="disabled"
          >
          <span>
            <strong>{{ cand.attribute_name }}</strong>
            <small v-if="cand.unit">({{ cand.unit }})</small>
            <small class="se-candidate-meta">{{ cand.attribute_code }}</small>
          </span>
        </label>

        <button
          type="button"
          class="se-button se-button--secondary se-button--small se-add-btn"
          :disabled="disabled || selectedCandidateIds.length === 0"
          @click="addSelected"
        >
          Добавить выбранные ({{ selectedCandidateIds.length }})
        </button>
      </div>
    </div>

    <div class="se-assigned-section">
      <div class="se-assigned-header">
        <h4>Назначенные характеристики</h4>
        <span
          class="se-card-counter"
          :class="{ 'se-card-counter--limit': cardCount >= 6 }"
        >
          В карточке: <strong>{{ cardCount }}</strong> из 6
        </span>
      </div>

      <div v-if="modelValue.length === 0" class="se-quiet-state">
        Характеристики ещё не назначены.
      </div>

      <div v-else class="se-attribute-bindings">
        <article
          v-for="(link, index) in modelValue"
          :key="link.attribute_id"
          class="se-attribute-binding"
        >
          <div class="se-attribute-binding__heading">
            <div>
              <strong>{{ link.attribute_name || link.attribute_code || link.attribute_id }}</strong>
              <small v-if="link.unit"> ({{ link.unit }})</small>
            </div>
            <span class="se-group-badge">{{ link.group_name || 'Группа' }}</span>
          </div>

          <div class="se-link-options">
            <label class="se-toggle-label">
              <input
                class="se-checkbox"
                type="checkbox"
                :checked="link.is_required"
                :disabled="disabled"
                @change="patchAttribute(index, 'is_required', ($event.target as HTMLInputElement).checked)"
              >
              Обязательная
            </label>

            <label
              class="se-toggle-label"
              :class="{ 'se-disabled-opt': cardCount >= 6 && !link.is_visible }"
            >
              <input
                class="se-checkbox"
                type="checkbox"
                :checked="link.is_visible"
                :disabled="disabled || (cardCount >= 6 && !link.is_visible)"
                @change="patchAttribute(index, 'is_visible', ($event.target as HTMLInputElement).checked)"
              >
              В карточке
            </label>

            <label class="se-toggle-label">
              <input
                class="se-checkbox"
                type="checkbox"
                :checked="link.is_filterable"
                :disabled="disabled"
                @change="patchAttribute(index, 'is_filterable', ($event.target as HTMLInputElement).checked)"
              >
              В фильтре
            </label>

            <label class="se-order-label">
              <span>Порядок</span>
              <input
                type="number"
                min="0"
                step="1"
                class="se-sort-input"
                :value="link.sort_order"
                :disabled="disabled"
                @input="patchAttribute(index, 'sort_order', Number(($event.target as HTMLInputElement).value) || 0)"
              >
            </label>

            <button
              type="button"
              class="se-button se-button--ghost-danger se-button--small"
              :disabled="disabled"
              @click="removeAttribute(index)"
            >
              Удалить
            </button>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { UUID } from '~/types/ids'
import type {
  CatalogAttributeGroup,
  CatalogSuperstructureAttribute,
  CatalogSuperstructureAttributeCandidate,
} from './types'
import { createCatalogCorrectionApi } from './api'

const props = defineProps<{
  modelValue: CatalogSuperstructureAttribute[]
  groups: CatalogAttributeGroup[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [items: CatalogSuperstructureAttribute[]]
}>()

const api = createCatalogCorrectionApi(useRuntimeConfig())

const selectedGroupId = ref<string>('')
const candidates = ref<CatalogSuperstructureAttributeCandidate[]>([])
const loadingCandidates = ref(false)
const candidateError = ref('')
const selectedCandidateIds = ref<UUID[]>([])

const assignedIds = computed(() => new Set(props.modelValue.map(a => a.attribute_id)))

const unassignedCandidates = computed(() =>
  candidates.value.filter(c => Boolean(c && c.attribute_id) && !assignedIds.value.has(c.attribute_id)),
)

const cardCount = computed(() =>
  props.modelValue.filter(a => a.is_visible).length,
)

const loadCandidates = async () => {
  selectedCandidateIds.value = []
  candidateError.value = ''
  if (!selectedGroupId.value) {
    candidates.value = []
    return
  }
  loadingCandidates.value = true
  try {
    const res = await api.listSuperstructureAttributeCandidates(selectedGroupId.value as UUID)
    candidates.value = (res.items || []).filter(c => Boolean(c && c.attribute_id))
  } catch (err: unknown) {
    candidateError.value = err instanceof Error ? err.message : 'Не удалось загрузить характеристики'
  } finally {
    loadingCandidates.value = false
  }
}

const addSelected = () => {
  if (selectedCandidateIds.value.length === 0) return
  const currentGroup = props.groups.find(g => g.id === selectedGroupId.value)
  const groupName = currentGroup?.name ?? ''

  const nextOrder = props.modelValue.length > 0
    ? Math.max(...props.modelValue.map(a => a.sort_order)) + 1
    : 0

  const toAdd: CatalogSuperstructureAttribute[] = []
  let orderOffset = 0
  for (const id of selectedCandidateIds.value) {
    const cand = candidates.value.find(c => c.attribute_id === id)
    if (!cand) continue
    toAdd.push({
      attribute_id: cand.attribute_id,
      group_id: cand.group_id,
      group_name: groupName || cand.group_name,
      attribute_name: cand.attribute_name,
      attribute_code: cand.attribute_code,
      data_type: cand.data_type,
      unit: cand.unit,
      is_required: false,
      is_visible: false,
      is_filterable: false,
      sort_order: nextOrder + orderOffset,
    })
    orderOffset += 1
  }

  emit('update:modelValue', [...props.modelValue, ...toAdd])
  selectedCandidateIds.value = []
}

const patchAttribute = <K extends keyof CatalogSuperstructureAttribute>(
  index: number,
  key: K,
  value: CatalogSuperstructureAttribute[K],
) => {
  const next = [...props.modelValue]
  const current = next[index]
  if (!current) return
  next[index] = { ...current, [key]: value }
  emit('update:modelValue', next)
}

const removeAttribute = (index: number) => {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.se-superstructure-picker {
  display: grid;
  gap: 20px;
}
.se-picker-step {
  border: 1px solid hsl(var(--se-border));
  border-radius: 8px;
  padding: 16px;
  background: hsl(var(--se-card));
  display: grid;
  gap: 12px;
}
.se-picker-step h4,
.se-assigned-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.se-candidates-list {
  display: grid;
  gap: 8px;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid hsl(var(--se-border));
  border-radius: 6px;
  padding: 8px 12px;
  background: hsl(var(--se-background));
}
.se-candidate-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.se-candidate-meta {
  color: hsl(var(--se-muted));
  margin-left: 6px;
}
.se-add-btn {
  margin-top: 8px;
  justify-self: start;
}
.se-assigned-section {
  display: grid;
  gap: 12px;
}
.se-assigned-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.se-card-counter {
  font-size: 13px;
  color: hsl(var(--se-muted));
}
.se-card-counter--limit {
  color: #d97706;
  font-weight: 600;
}
.se-attribute-bindings {
  display: grid;
  gap: 10px;
}
.se-attribute-binding {
  border: 1px solid hsl(var(--se-border));
  border-radius: 6px;
  padding: 12px;
  background: hsl(var(--se-card));
  display: grid;
  gap: 8px;
}
.se-attribute-binding__heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.se-group-badge {
  font-size: 12px;
  padding: 2px 6px;
  background: hsl(var(--se-muted) / 0.15);
  border-radius: 4px;
}
.se-link-options {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.se-toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}
.se-disabled-opt {
  opacity: 0.5;
  cursor: not-allowed;
}
.se-order-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.se-sort-input {
  width: 60px;
  padding: 4px 6px;
  border: 1px solid hsl(var(--se-border));
  border-radius: 4px;
}
</style>
