<template>
  <section class="min-w-0 space-y-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:var(--storefront-surface,#ffffff)] p-5" data-testid="application-questionnaire">
    <div class="flex items-start justify-between gap-4">
      <div class="min-w-0">
        <h1 class="text-2xl font-semibold text-[color:var(--storefront-title,#111827)]">Анкета клиента</h1>
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Сохранённые сведения по этой заявке.</p>
      </div>
      <button type="button" class="shrink-0 text-sm text-[color:var(--storefront-link,#2563eb)]" :disabled="loading" @click="load">Обновить</button>
    </div>
    <p v-if="loading" role="status" class="text-sm">Загружаем анкету…</p>
    <div v-else-if="error" role="alert" class="text-sm text-red-700">
      <p>{{ error }}</p>
      <button type="button" class="mt-2 underline" @click="load">Повторить</button>
    </div>
    <p v-else-if="!rows.length" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Сведения анкеты пока не заполнены.</p>
    <dl v-else class="min-w-0 divide-y">
      <div v-for="[field, value] in rows" :key="field" class="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-4 py-3">
        <dt class="min-w-0 break-words text-sm font-medium text-[color:var(--storefront-text-muted,#6b7280)]">{{ questionnaireLabels[field] }}</dt>
        <dd class="min-w-0 break-words text-sm">
          <QuestionnaireValue :value="value" :field="field" :application-id="applicationId" :leasing-company-id="leasingCompanyId" :dictionary-names="dictionaryNames" />
        </dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import { withLeasingCompanyContext } from '~/utils/leasingCompanyContext'
import { useNotificationCompanyRequest } from '~/features/notifications'
import { questionnaireLabels } from '~/features/questionnaire/labels'
import type { QuestionnaireDictionaryItem } from '~/features/questionnaire/types'
import QuestionnaireValue from './QuestionnaireValue.vue'

const props = defineProps<{ applicationId: string; leasingCompanyId?: string }>()
const emit = defineEmits<{ loaded: [available: boolean] }>()
const config = useRuntimeConfig()
const { request, company } = useNotificationCompanyRequest()
const loading = ref(true)
const error = ref('')
const data = ref<Record<string, unknown>>({})
const dictionaryNames = ref<Record<string, string>>({})
let version = 0
const rows = computed(() => Object.entries(data.value).filter(([key]) =>
  Boolean(questionnaireLabels[key]) && !['created_at', 'updated_at'].includes(key),
))

const load = async () => {
  const current = ++version
  loading.value = true
  error.value = ''
  data.value = {}
  dictionaryNames.value = {}
  emit('loaded', false)
  try {
    const result = await request<{ questionnaire: Record<string, unknown> | null }>(
      withLeasingCompanyContext(`/api/v1/questionnaire/${props.applicationId}`, props.leasingCompanyId),
      { baseURL: config.public.apiBase, credentials: 'include' },
    )
    if (current !== version) return
    data.value = result.questionnaire || {}
    emit('loaded', true)
    const selectedBases = Array.isArray(data.value.beneficiaries)
      ? data.value.beneficiaries.flatMap(person => typeof person?.beneficial_owner_basis === 'string' ? [person.beneficial_owner_basis] : [])
      : []
    const selectedReasons = typeof data.value.no_beneficial_owner_reason === 'string' ? [data.value.no_beneficial_owner_reason] : []
    const queries = [
      { kind: 'beneficial_owner_bases', selected: selectedBases },
      { kind: 'beneficial_owner_absence_reasons', selected: selectedReasons },
    ]
    const responses = await Promise.all(queries.flatMap(({ kind, selected }) =>
      (selected.length ? [...new Set(selected)] : [undefined]).map(selected_id =>
        $fetch<{ items: QuestionnaireDictionaryItem[] }>(`/api/v1/questionnaire-dictionaries/${kind}`, {
          baseURL: config.public.apiBase, credentials: 'include', query: { selected_id },
        }).catch(() => ({ items: [] })),
      ),
    ))
    const purposes = await $fetch<{ purposes: Array<{ purpose_name: string; purpose_display_name: string }> }>(
      '/api/v1/applications/leasing-purposes', { baseURL: config.public.apiBase, credentials: 'include' },
    ).catch(() => ({ purposes: [] }))
    if (current === version) dictionaryNames.value = Object.fromEntries([
      ...responses.flatMap(response => response.items).map(item => [item.id, item.name]),
      ...purposes.purposes.map(item => [item.purpose_name, item.purpose_display_name]),
    ])
  } catch (cause) {
    if (current !== version) return
    const failure = cause as { statusCode?: number; status?: number; response?: { status?: number } }
    const status = failure.statusCode ?? failure.status ?? failure.response?.status
    error.value = status === 403 ? 'Нет доступа к анкете этой заявки.'
      : status === 404 ? 'Заявка не найдена.'
        : status === 401 ? 'Войдите в систему, чтобы открыть анкету.'
          : 'Не удалось загрузить анкету. Повторите попытку.'
  } finally {
    if (current === version) loading.value = false
  }
}
watch(() => [props.applicationId, props.leasingCompanyId, company()], load, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { version += 1 })
</script>
