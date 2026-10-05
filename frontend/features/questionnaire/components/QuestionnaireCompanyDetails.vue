<template>
  <section class="space-y-4 rounded-lg border p-4">
    <div class="flex items-center justify-between gap-4"><h5 class="font-medium">Реквизиты и сведения о компании</h5><button type="button" class="text-sm text-blue-700 disabled:opacity-50" :disabled="refreshing || !applicationId" @click="refresh">{{ refreshing ? 'Получаем сведения…' : 'Обновить данные и выписку ЕГРЮЛ' }}</button></div>
    <p v-if="refreshMessage" role="status" class="text-sm">{{ refreshMessage }}</p>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
    <div class="grid grid-cols-2 gap-3">
      <label v-for="field in fields" :key="field.key" class="text-sm">{{ field.label }}<input :value="store.questionnaireData[field.key] ?? ''" :name="field.key" :type="field.type || 'text'" :min="field.type === 'number' ? 0 : undefined" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="edit(field.key, ($event.target as HTMLInputElement).value, field.type)"></label>
    </div>
  </section>
</template>
<script setup lang="ts">
import type { QuestionnaireData } from '~/features/applications/constants/application'
import { useNotificationCompanyRequest } from '~/features/notifications'
const props = defineProps<{ applicationId?: string | null; saveBeforeRefresh?: () => Promise<boolean> }>()
const emit = defineEmits<{ update: [data: Partial<QuestionnaireData>] }>()
const store = useCheckoutStore()
const config = useRuntimeConfig()
const { request } = useNotificationCompanyRequest()
const refreshing = ref(false)
const error = ref('')
const refreshMessage = ref('')
const fields: Array<{ key: keyof QuestionnaireData; label: string; type?: string }> = [
  { key: 'full_company_name', label: 'Полное наименование' }, { key: 'short_company_name', label: 'Сокращённое наименование' },
  { key: 'foreign_company_name', label: 'Наименование на иностранном языке' },
  { key: 'inn', label: 'ИНН' }, { key: 'kpp', label: 'КПП' }, { key: 'ogrn', label: 'ОГРН' }, { key: 'legal_form', label: 'Организационно-правовая форма' },
  { key: 'okpo', label: 'ОКПО' }, { key: 'okato', label: 'ОКАТО' }, { key: 'okved_main', label: 'Основной ОКВЭД' }, { key: 'okved_additional', label: 'Дополнительные ОКВЭД' },
  { key: 'registration_date', label: 'Дата регистрации', type: 'date' }, { key: 'registration_authority_name', label: 'Регистрирующий орган' },
  { key: 'employee_count', label: 'Численность сотрудников', type: 'number' }, { key: 'bank_name', label: 'Наименование банка' },
  { key: 'bik', label: 'БИК' }, { key: 'settlement_account', label: 'Расчётный счёт' }, { key: 'correspondent_account', label: 'Корреспондентский счёт' },
  { key: 'director_position', label: 'Должность руководителя' }, { key: 'director_inn', label: 'ИНН руководителя' },
  { key: 'director_registration_address', label: 'Адрес регистрации руководителя' }, { key: 'director_phone', label: 'Телефон руководителя' }, { key: 'director_email', label: 'Email руководителя', type: 'email' },
]
const edit = (key: keyof QuestionnaireData, value: string, type?: string) => emit('update', { [key]: type === 'number' ? (value === '' ? null : Number(value)) : value })
const refresh = async () => {
  if (!props.applicationId || refreshing.value) return
  refreshing.value = true; error.value = ''; refreshMessage.value = ''
  try {
    if (props.saveBeforeRefresh && !await props.saveBeforeRefresh()) { error.value = 'Сначала исправьте ошибки сохранения анкеты.'; return }
    const original = JSON.stringify(store.questionnaireData)
    const result = await request<{ questionnaire: QuestionnaireData; sources: Record<string, string> }>(`/api/v1/questionnaire/${props.applicationId}/refresh`, { method: 'POST', baseURL: config.public.apiBase, credentials: 'include' })
    const before = JSON.parse(original) as QuestionnaireData
    const safe = Object.fromEntries(Object.entries(result.questionnaire).filter(([key]) => JSON.stringify(store.questionnaireData[key as keyof QuestionnaireData]) === JSON.stringify(before[key as keyof QuestionnaireData])))
    store.updateQuestionnaireData(safe)
    refreshMessage.value = Object.values(result.sources).some(value => value === 'unavailable') ? 'Часть источников сейчас недоступна. Сохранённые сведения не потеряны; повторите позже или заполните поля вручную.' : 'Данные обновлены. Ручные значения сохранены.'
  } catch (cause) { error.value = typeof (cause as { data?: { detail?: unknown } }).data?.detail === 'string' ? String((cause as { data: { detail: string } }).data.detail) : 'Не удалось обновить данные. Повторите запрос.' }
  finally { refreshing.value = false }
}
</script>
