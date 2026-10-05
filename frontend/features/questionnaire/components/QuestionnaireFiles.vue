<template>
  <section class="space-y-3 rounded-lg border p-4">
    <div class="flex items-center justify-between"><h5 class="font-medium">Документы, приложенные к заявке</h5><button type="button" class="text-sm text-blue-700" :disabled="loading" @click="load">Обновить список</button></div>
    <p v-if="loading" role="status" class="text-sm">Загружаем документы…</p>
    <p v-else-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
    <p v-else-if="!documents.length" class="text-sm text-gray-500">Документы пока не приложены. Выписка ЕГРЮЛ появится здесь после получения.</p>
    <ul v-else class="divide-y"><li v-for="document in documents" :key="document.id" class="flex items-center justify-between gap-4 py-2 text-sm"><span class="min-w-0 break-words">{{ document.file_name }}</span><span class="flex shrink-0 gap-3"><a :href="api.downloadUrl(`/api/v1/documents/${document.id}/content?disposition=inline`)" target="_blank" rel="noopener" class="text-blue-700 underline">Открыть</a><a :href="api.downloadUrl(`/api/v1/documents/${document.id}/content`)" download class="text-blue-700 underline">Скачать</a></span></li></ul>
  </section>
</template>
<script setup lang="ts">
import { createDocumentsApi, type Document } from '~/features/documents/api/documentsApi'
import { useNotificationCompanyContext } from '~/features/notifications'
const props = defineProps<{ applicationId?: string | null; leasingCompanyId?: string }>()
const company = useNotificationCompanyContext()
const api = createDocumentsApi(useRuntimeConfig(), () => props.leasingCompanyId, company)
const documents = ref<Document[]>([]); const loading = ref(false); const error = ref('')
let version = 0
const load = async () => { const request = ++version; documents.value = []; if (!props.applicationId) return; loading.value = true; error.value = ''; try { const result = await api.getApplicationDocuments(props.applicationId); if (version === request) documents.value = result.documents } catch { if (version === request) error.value = 'Не удалось загрузить документы. Повторите обновление списка.' } finally { if (version === request) loading.value = false } }
watch(() => [props.applicationId, props.leasingCompanyId, company()], load, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { version += 1 })
</script>
