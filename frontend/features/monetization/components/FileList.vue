<template>
  <ul class="file-list"><li v-for="file in files" :key="file.id">
    <div class="file-info"><button type="button" class="link" :disabled="!!downloading" @click="download(file)">{{ downloading === file.id ? 'Скачивание…' : file.file_name }}</button><span v-if="file.outdated" class="badge">Предыдущая версия</span><small v-if="file.uploaded_by_role" class="muted">{{ roleLabels[file.uploaded_by_role] || file.uploaded_by_role }}</small></div>
    <time v-if="file.uploaded_at" class="file-uploaded-at muted" :datetime="file.uploaded_at">{{ formatDate(file.uploaded_at) }}</time>
  </li></ul>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import type { Document } from '../types'
import type { MonetizationApi } from '../api'
import { errorMessage } from '../api'
const props = defineProps<{ files: Document[]; api: MonetizationApi }>()
const roleLabels: Record<string, string> = { leasing_company: 'ЛК', leasing: 'ЛК', dealer: 'Дилер', distributor: 'Дистрибьютор', admin: 'Администратор', carcraft_employee: 'Администратор', platform: 'Платформа МЛ' }
const error = ref('')
const downloading = ref<string | null>(null)
const formatDate = (value: string) => new Date(value).toLocaleDateString('ru-RU')
async function download(file: Document) {
  if (downloading.value) return
  error.value = ''; downloading.value = file.id
  try { await props.api.download(file) } catch (failure) { error.value = errorMessage(failure) } finally { downloading.value = null }
}
</script>
<style scoped>
.file-list li { justify-content:space-between; border-bottom:1px solid #f0f1f4; }
.file-list li:last-child { border-bottom:0; }
.file-info { display:flex; align-items:center; flex-wrap:wrap; gap:8px; min-width:0; }
.file-info>button { text-align:left; overflow-wrap:anywhere; }
.file-uploaded-at { font-size:12px; white-space:nowrap; }
</style>
