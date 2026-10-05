<template>
  <div v-if="auth.isCarCraftEmployee" class="space-y-5">
    <h1 class="text-2xl font-semibold">Настройки анкет</h1>
    <nav class="flex gap-4 border-b pb-3" aria-label="Настройки анкет"><button v-for="tab in tabs" :key="tab.key" type="button" class="rounded px-3 py-2 text-sm" :class="activeTab === tab.key ? 'bg-blue-100 text-blue-900' : 'text-gray-700'" @click="activeTab = tab.key">{{ tab.label }}</button></nav>
    <p v-if="error" class="rounded border border-red-200 p-3 text-sm text-red-700" role="alert">{{ error }} <button type="button" class="underline" @click="load">Повторить</button></p>
    <p v-if="message" class="text-sm text-green-700" role="status">{{ message }}</p>
    <section v-if="activeTab === 'settings'" class="space-y-4">
      <label class="block max-w-xl text-sm">Лизинговая компания<select v-model="companyId" class="storefront-control mt-1 w-full rounded border px-3 py-2"><option value="">Выберите лизинговую компанию</option><option v-for="company in companies" :key="company.id" :value="company.id">{{ company.name }}</option></select></label>
      <p class="text-sm text-gray-600">Каждая лизинговая компания получает только включённые для неё сведения. Обязательные поля проверяются при назначении компании заявке.</p>
      <p v-if="loading" role="status">Загружаем настройки…</p>
      <form v-else-if="companyId" class="space-y-4" @submit.prevent="saveSettings">
        <table class="w-full border-collapse text-sm">
          <thead><tr class="border-b text-left"><th class="p-3">Поле анкеты</th><th class="p-3">Доступно ЛК</th><th class="p-3">Обязательно</th></tr></thead>
          <tbody>
            <tr v-for="row in settings" :key="row.field" class="border-b">
              <td class="p-3">
                {{ row.label }}
                <p v-if="!row.required_available" :id="`required-reason-${row.field}`" class="mt-1 text-xs text-gray-500">{{ row.required_unavailable_reason }}</p>
              </td>
              <td class="p-3"><input v-model="row.enabled" type="checkbox" :aria-label="`Доступно: ${row.label}`" @change="!row.enabled && (row.required = false)"></td>
              <td class="p-3"><input v-model="row.required" type="checkbox" :disabled="!row.enabled || !row.required_available" :aria-label="`Обязательно: ${row.label}`" :aria-describedby="!row.required_available ? `required-reason-${row.field}` : undefined"></td>
            </tr>
          </tbody>
        </table>
        <button type="submit" class="btn-primary" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сохранить настройки' }}</button>
      </form>
    </section>
    <section v-else class="space-y-4">
      <p class="text-sm text-gray-600">Неактивные значения сохраняются в ранее заполненных анкетах, но недоступны для новых выборов.</p>
      <form class="grid grid-cols-[1fr_2fr_auto] items-end gap-3 rounded border p-4" @submit.prevent="createItem"><label class="text-sm">Код<input v-model="newCode" required pattern="[a-z][a-z0-9_]*" class="storefront-control mt-1 w-full rounded border px-3 py-2"></label><label class="text-sm">Наименование<input v-model="newName" required class="storefront-control mt-1 w-full rounded border px-3 py-2"></label><button type="submit" class="btn-primary" :disabled="saving">Добавить</button></form>
      <p v-if="loading" role="status">Загружаем справочник…</p>
      <form v-for="item in items" :key="item.id" class="grid grid-cols-[1fr_2fr_auto_auto] items-center gap-3 rounded border p-3" @submit.prevent="saveItem(item)"><span class="text-xs text-gray-500">{{ item.code }}</span><input v-model="item.name" :aria-label="`Название: ${item.code}`" required class="storefront-control w-full rounded border px-3 py-2 text-sm"><label class="flex items-center gap-2 text-sm"><input v-model="item.is_active" type="checkbox">Активно</label><button type="submit" class="text-sm text-blue-700" :disabled="saving">Сохранить</button></form>
    </section>
  </div>
</template>
<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import type { QuestionnaireDictionaryItem, QuestionnaireDictionaryKind, QuestionnaireFieldSetting } from '~/features/questionnaire/types'
// TODO(TZ40): This per-LC enabled/required editor is not TZ40's field-to-many-LCs
// screen with LC/section/name filters, reset and company multi-select.
// "Использовать" does not define requiredness or the document collection stage;
// settle those separately when implementing the future screen.
// See specs/task_2026-09-30_16-03-41_MSK.md,
// section "Отложенное ТЗ №40 и устранение блокировки дозапросов".
definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace', 'require-admin'] })
const auth = useAuthStore(); const config = useRuntimeConfig()
const tabs: Array<{ key: 'settings' | QuestionnaireDictionaryKind; label: string }> = [{ key: 'settings', label: 'Поля для лизинговых компаний' }, { key: 'beneficial_owner_bases', label: 'Основания бенефициаров' }, { key: 'beneficial_owner_absence_reasons', label: 'Причины отсутствия бенефициара' }]
const activeTab = ref<'settings' | QuestionnaireDictionaryKind>('settings')
const companies = ref<Array<{ id: string; name: string }>>([]); const companyId = ref(''); const settings = ref<QuestionnaireFieldSetting[]>([])
const items = ref<QuestionnaireDictionaryItem[]>([]); const newCode = ref(''); const newName = ref('')
const loading = ref(false); const saving = ref(false); const error = ref(''); const message = ref('')
const options = () => ({ baseURL: config.public.apiBase, credentials: 'include' as const })
let requestVersion = 0
const load = async () => {
  const version = ++requestVersion; error.value = ''; message.value = ''; loading.value = true
  try {
    if (activeTab.value === 'settings') { settings.value = []; if (companyId.value) { const result = await $fetch<{ fields: QuestionnaireFieldSetting[] }>(`/api/v1/leasing/companies/${companyId.value}/questionnaire-settings`, options()); if (version === requestVersion) settings.value = result.fields } }
    else { const result = await $fetch<{ items: QuestionnaireDictionaryItem[] }>(`/api/v1/questionnaire-dictionaries/${activeTab.value}`, { ...options(), query: { include_inactive: true } }); if (version === requestVersion) items.value = result.items }
  } catch { if (version === requestVersion) error.value = 'Не удалось загрузить настройки.' }
  finally { if (version === requestVersion) loading.value = false }
}
const save = async (operation: () => Promise<unknown>) => { if (saving.value) return; saving.value = true; error.value = ''; message.value = ''; try { await operation(); message.value = 'Изменения сохранены' } catch (cause) { const detail = (cause as { data?: { detail?: unknown } }).data?.detail; error.value = typeof detail === 'string' ? detail : 'Не удалось сохранить. Проверьте данные и повторите.' } finally { saving.value = false } }
const saveSettings = () => save(() => $fetch<unknown>(`/api/v1/leasing/companies/${companyId.value}/questionnaire-settings`, { ...options(), method: 'PUT', body: { fields: settings.value.map(({ field, enabled, required }) => ({ field, enabled, required })) } }))
const saveItem = (item: QuestionnaireDictionaryItem) => save(() => $fetch<unknown>(`/api/v1/questionnaire-dictionaries/${activeTab.value}/${item.id}`, { ...options(), method: 'PATCH', body: { name: item.name.trim(), is_active: item.is_active } }))
const createItem = () => save(async () => { await $fetch<unknown>(`/api/v1/questionnaire-dictionaries/${activeTab.value}`, { ...options(), method: 'POST', body: { code: newCode.value.trim(), name: newName.value.trim(), is_active: true } }); newCode.value = ''; newName.value = ''; await load() })
watch([activeTab, companyId], load)
onMounted(async () => { try { const result = await $fetch<{ companies: Array<{ id: string; name: string }> }>('/api/v1/leasing/companies', options()); companies.value = result.companies } catch { error.value = 'Не удалось загрузить список лизинговых компаний.' } })
</script>
