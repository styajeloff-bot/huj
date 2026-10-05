<template>
  <div ref="container" class="dr-company-picker">
    <SearchableDropdown :teleport-to="teleportTarget" :anchor-to-control="true" :model-value="null" :items="options" :label="label" placeholder="Название или ИНН" search-placeholder="Название или ИНН" label-key="label" value-key="selection_id" :remote="true" :loading="loading" :error="!!error" @search="search" @update:model-value="choose" />
    <div v-if="selectedIds.length" class="dr-tags"><span v-for="id in selectedIds" :key="id" class="dr-tag">{{ selectedName(id) }}<button type="button" :aria-label="'Убрать ' + selectedName(id)" @click="remove(id)">×</button></span></div>
    <p v-if="error" class="dr-error" role="alert">{{ error }}</p>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import type { DocumentRegistryApi } from '../api'
import { registryError } from '../api'
import { companyId, type CompanyRole, type RegistryCompany } from '../types'
const props = defineProps<{ api: DocumentRegistryApi; role: CompanyRole; label: string; selectedIds: string[]; companies: RegistryCompany[]; single?: boolean }>()
const emit = defineEmits<{ change: [ids: string[], companies: RegistryCompany[]] }>()
const container = ref<HTMLElement | null>(null); const teleportTarget = ref<string | HTMLElement>('body')
const items = ref<RegistryCompany[]>([]); const loading = ref(false); const error = ref(''); let generation = 0
const options = computed(() => items.value.filter(item => companyId(item) && !props.selectedIds.includes(companyId(item)!)).map(item => ({ ...item, selection_id: companyId(item), label: `${item.name} · ИНН ${item.inn || 'не указан'}` })))
function selectedName(id: string) { return [...props.companies, ...items.value].find(item => companyId(item) === id)?.name ?? 'Выбрана компания' }
async function search(value: string) {
  const token = ++generation; loading.value = true; error.value = ''
  try { const result = await props.api.companies(props.role, value.trim()); if (token === generation) items.value = result.items }
  catch (failure) { if (token === generation) error.value = registryError(failure) }
  finally { if (token === generation) loading.value = false }
}
function choose(value: unknown) {
  const item = items.value.find(item => companyId(item) === value); if (!item) return
  const id = companyId(item); if (!id) return
  emit('change', props.single ? [id] : [...props.selectedIds, id], props.single ? [item] : [...props.companies, item])
}
function remove(id: string) { emit('change', props.selectedIds.filter(value => value !== id), props.companies.filter(item => companyId(item) !== id)) }
onMounted(() => { teleportTarget.value = container.value?.closest('dialog') ?? 'body'; if (props.selectedIds.length) void search('') })
onBeforeUnmount(() => ++generation)
</script>
