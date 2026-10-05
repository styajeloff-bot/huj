<template>
  <article class="dr-document" :data-document-id="document.id">
    <div class="dr-document-heading"><div class="dr-title-line"><span v-if="document.is_main" class="dr-main-badge">Основной</span><span class="dr-type-badge">{{ typeLabels[document.document_type] }}</span><h3>{{ document.name }} <span class="dr-number">№{{ document.contract_number }}</span></h3></div><span class="dr-status" :class="document.status">{{ statusLabels[document.status] }}</span></div>
    <p class="dr-meta">Действует: {{ dateLabel(document.current_version.valid_from) }} → {{ dateLabel(document.current_version.valid_to) }} · Версия {{ document.current_version.version_number }} · Сохранил: {{ document.current_version.uploaded_by.display_name }}, {{ dateLabel(document.current_version.uploaded_at) }}</p>
    <p v-if="companyLines(document.related_companies).length" class="dr-meta">Связанные компании: {{ companyLines(document.related_companies).join(', ') }}</p>
    <div class="dr-files"><button v-for="file in document.current_version.files" :key="file.id" type="button" class="dr-file" :disabled="downloading === file.id" @click="download(file)">{{ file.name }}</button><button v-if="document.version_count > 1" type="button" class="dr-link" @click="emit('history', document)">История версий ({{ document.version_count }})</button></div>
    <div v-if="canManage" class="dr-document-actions"><button type="button" class="dr-link" :disabled="busy" @click="emit('edit', document)">Редактировать</button><button type="button" class="dr-link" :disabled="busy" @click="emit('activate', document)">{{ document.active ? 'Деактивировать' : 'Активировать' }}</button><button type="button" class="dr-danger" :disabled="busy" @click="emit('remove', document)">Удалить</button></div>
    <p v-if="error" class="dr-error" role="alert">{{ error }}</p>
  </article>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import type { DocumentRegistryApi } from '../api'
import { registryError } from '../api'
import { companyLines, dateLabel, statusLabels, typeLabels, type ReferenceDocument, type RegistryFile } from '../types'
const props = defineProps<{ api: DocumentRegistryApi; document: ReferenceDocument; canManage?: boolean; busy?: boolean }>()
const emit = defineEmits<{ history: [document: ReferenceDocument]; edit: [document: ReferenceDocument]; activate: [document: ReferenceDocument]; remove: [document: ReferenceDocument] }>()
const downloading = ref(''); const error = ref('')
async function download(file: RegistryFile) { downloading.value = file.id; error.value = ''; try { await props.api.download(file) } catch (failure) { error.value = registryError(failure) } finally { downloading.value = '' } }
</script>
