<template>
  <RegistryModal :title="'История версий · ' + document.contract_number" :busy="!!restoring" wide @close="emit('close')">
    <p>{{ document.name }}</p>
    <p v-if="canManage" class="dr-notice">Выбранная версия станет текущей в карточке, таблице, выгрузке и связанных условиях монетизации. Ручная деактивация документа сохранится.</p>
    <p v-if="loading" role="status" class="dr-meta">Загрузка версий…</p>
    <p v-if="error" class="dr-error" role="alert">{{ error }}</p>
    <section v-for="version in versions" :key="version.id" class="dr-version" :data-version-id="version.id" :data-version-number="version.version_number">
      <div class="version-heading">
        <h3>Версия {{ version.version_number }} <span v-if="version.id === document.current_version.id" class="dr-main-badge">Текущая</span></h3>
        <button v-if="canManage && version.id !== document.current_version.id" type="button" class="dr-secondary" :disabled="!!restoring || loading" @click="makeCurrent(version)">{{ restoring === version.id ? 'Переключение…' : 'Сделать текущей' }}</button>
      </div>
      <p class="version-name">{{ version.name }}</p>
      <p class="dr-meta">{{ dateLabel(version.valid_from) }} → {{ dateLabel(version.valid_to) }}</p>
      <p class="dr-meta">Связанные компании: {{ companyLines(version.related_companies).join(', ') || '—' }}</p>
      <p class="dr-meta">{{ version.uploaded_by.display_name }}, {{ dateLabel(version.uploaded_at) }}</p>
      <p v-if="version.metadata_backfilled" class="version-backfilled">Название и связанные компании восстановлены из прежних данных документа. Их исходные значения на момент создания этой версии неизвестны.</p>
      <div class="dr-files"><button v-for="file in version.files" :key="file.id" type="button" class="dr-file" @click="download(file)">{{ file.name }}</button></div>
    </section>
  </RegistryModal>
</template>
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { DocumentRegistryApi } from '../api'
import { registryError } from '../api'
import { companyLines, dateLabel, type ReferenceDocument, type RegistryFile, type RegistryVersion } from '../types'
import RegistryModal from './RegistryModal.vue'
const props = defineProps<{ api: DocumentRegistryApi; document: ReferenceDocument; canManage?: boolean }>()
const emit = defineEmits<{ close: []; changed: [document: ReferenceDocument] }>()
const versions = ref<RegistryVersion[]>([])
const loading = ref(true)
const restoring = ref('')
const error = ref('')
let generation = 0
async function download(file: RegistryFile) { try { await props.api.download(file) } catch (failure) { error.value = registryError(failure) } }
async function loadVersions() {
  const token = ++generation
  loading.value = true
  try { const result = await props.api.versions(props.document.id); if (token === generation) versions.value = result.items }
  catch (failure) { if (token === generation) error.value = registryError(failure) }
  finally { if (token === generation) loading.value = false }
}
async function makeCurrent(version: RegistryVersion) {
  if (!props.canManage || restoring.value || version.id === props.document.current_version.id) return
  restoring.value = version.id; error.value = ''
  try {
    const document = await props.api.activateVersion(props.document.id, version.id, props.document.current_version.id)
    emit('changed', document)
    await loadVersions()
  } catch (failure) { error.value = registryError(failure) }
  finally { restoring.value = '' }
}
onMounted(loadVersions)
onBeforeUnmount(() => { ++generation })
</script>
<style scoped>
.version-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.version-name { margin: 12px 0 6px; font-weight: 600; overflow-wrap: anywhere; }
.version-backfilled { margin: 8px 0; color: #6b7280; font-size: 12px; line-height: 1.5; }
</style>
