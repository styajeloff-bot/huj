<template>
  <section class="dr-group">
    <div class="dr-group-heading"><div class="dr-tags"><span v-for="label in companyLines(group.participants)" :key="label" class="dr-tag">{{ label }}</span><span v-if="group.participants.mark_name" class="dr-tag">{{ group.participants.mark_name }}{{ group.participants.model_name ? ' / ' + group.participants.model_name : '' }}</span><span v-if="!group.main_document" class="dr-meta">Связка документов</span></div><button v-if="group.can_manage && group.main_document" type="button" class="dr-link" @click="emit('add', group)">+ Документ в связку</button></div>
    <RegistryDocumentCard v-if="group.main_document" :api="api" :document="group.main_document" :can-manage="group.can_manage" :busy="busy" @history="emit('history', $event)" @edit="emit('edit', $event)" @activate="emit('activate', $event)" @remove="emit('remove', $event)" />
    <template v-if="expanded">
      <nav ref="tablist" class="workspace-tabs" role="tablist" aria-label="Типы дочерних документов">
        <button v-for="item in tabs" :id="tabId(item.code)" :key="item.code" type="button" role="tab" :aria-selected="selectedType === item.code" :aria-controls="panelId" :tabindex="selectedType === item.code ? 0 : -1" @click="selectType(item.code)" @keydown="handleTabKeydown($event, item.code)">{{ item.name }} ({{ item.count }})</button>
      </nav>
      <div :id="panelId" role="tabpanel" :aria-labelledby="tabId(selectedType)" tabindex="0">
      <div v-if="loading" class="dr-empty" role="status">Загрузка документов…</div><p v-if="error" class="dr-error" role="alert">{{ error }}</p>
      <RegistryDocumentCard v-for="document in children" :key="document.id" :api="api" :document="document" :can-manage="group.can_manage" :busy="busy" @history="emit('history', $event)" @edit="emit('edit', $event)" @activate="emit('activate', $event)" @remove="emit('remove', $event)" />
      <p v-if="!loading && !children.length" class="dr-empty">Дочерних документов этого типа нет.</p>
      <div v-if="hasMore" class="dr-center"><button type="button" class="dr-link" :disabled="loading" @click="load(true)">Показать ещё</button></div>
      </div>
    </template>
    <button v-if="group.children_count > 0 || !group.main_document" type="button" class="dr-expand" :aria-expanded="expanded" @click="toggle">{{ expanded ? 'Скрыть' : `Показать ещё ${group.children_count} документ(а/ов)` }}</button>
  </section>
</template>
<script setup lang="ts">
import '~/assets/css/workspace-tabs.css'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { DocumentRegistryApi } from '../api'
import { registryError } from '../api'
import { companyLines, typeLabels, type DocumentGroup, type ReferenceDocument } from '../types'
import RegistryDocumentCard from './RegistryDocumentCard.vue'
const props = defineProps<{ api: DocumentRegistryApi; group: DocumentGroup; busy?: boolean }>()
const emit = defineEmits<{ add: [group: DocumentGroup]; history: [document: ReferenceDocument]; edit: [document: ReferenceDocument]; activate: [document: ReferenceDocument]; remove: [document: ReferenceDocument] }>()
const expanded = ref(!props.group.main_document); const selectedType = ref(''); const documents = ref<ReferenceDocument[]>([]); const page = ref(0); const total = ref(0); const loading = ref(false); const error = ref(''); let generation = 0
const children = computed(() => documents.value.filter(item => !item.is_main))
const hasMore = computed(() => page.value * 20 < total.value)
const tablist = ref<HTMLElement | null>(null)
const panelId = computed(() => `registry-children-${props.group.group_id}`)
const tabId = (code: string) => `${panelId.value}-${code || 'all'}`
const tabs = computed(() => [
  { code: '', name: 'Все', count: props.group.children_count },
  ...Object.entries(typeLabels).map(([code, name]) => ({ code, name,
    count: Math.max(0, (props.group.counts_by_type[code] ?? 0) - (props.group.main_document?.document_type === code ? 1 : 0)),
  })),
])
async function load(append = false) {
  const token = ++generation; const nextPage = append ? page.value + 1 : 1; loading.value = true; error.value = ''
  if (!append) documents.value = []
  try { const result = await props.api.children(props.group.group_id, selectedType.value, nextPage); if (token === generation) { documents.value = append ? [...documents.value, ...result.items] : result.items; page.value = nextPage; total.value = result.pagination.total } }
  catch (failure) { if (token === generation) error.value = registryError(failure) } finally { if (token === generation) loading.value = false }
}
function toggle() { expanded.value = !expanded.value; if (expanded.value) { selectedType.value = ''; void load() } }
function selectType(type: string) { selectedType.value = type; void load() }
async function handleTabKeydown(event: KeyboardEvent, type: string) {
  const index = tabs.value.findIndex(item => item.code === type)
  let nextIndex: number
  if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.value.length
  else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.value.length) % tabs.value.length
  else if (event.key === 'Home') nextIndex = 0
  else if (event.key === 'End') nextIndex = tabs.value.length - 1
  else return
  event.preventDefault()
  selectType(tabs.value[nextIndex]!.code)
  await nextTick()
  tablist.value?.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus()
}
watch(() => props.group, () => { if (expanded.value) void load() }, { immediate: true })
onBeforeUnmount(() => ++generation)
</script>
