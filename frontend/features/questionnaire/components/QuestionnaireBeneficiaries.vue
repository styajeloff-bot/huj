<template>
  <section class="space-y-4 rounded-lg border p-4">
    <div class="flex items-center justify-between"><h5 class="font-medium">Бенефициарные владельцы</h5><button v-if="!absent" type="button" class="text-sm text-blue-700" @click="add">Добавить бенефициара</button></div>
    <label class="flex items-center gap-2 text-sm"><input :checked="absent" name="no_beneficial_owner" type="checkbox" @change="setAbsent(($event.target as HTMLInputElement).checked)">Бенефициарный владелец отсутствует</label>
    <p v-if="dictionaryError" role="alert" class="text-sm text-red-700">{{ dictionaryError }} <button type="button" class="underline" @click="loadDictionaries">Повторить</button></p>
    <template v-if="absent">
      <label class="block text-sm">Причина отсутствия <span class="text-red-700">*</span><select :value="store.questionnaireData.no_beneficial_owner_reason || ''" name="no_beneficial_owner_reason" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @change="setReason(($event.target as HTMLSelectElement).value)"><option value="">Выберите причину</option><option v-for="item in reasons" :key="item.id" :value="item.id">{{ item.name }}{{ item.is_active ? '' : ' (неактивно)' }}</option></select></label>
      <label v-if="reasonIsOther" class="block text-sm">Укажите причину <span class="text-red-700">*</span><textarea :value="store.questionnaireData.no_beneficial_owner_reason_details || ''" name="no_beneficial_owner_reason_details" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="emit('update', { no_beneficial_owner_reason_details: ($event.target as HTMLTextAreaElement).value })" /></label>
    </template>
    <article v-for="(person, index) in people" v-else :key="person.id" class="space-y-3 rounded-lg border p-4">
      <div class="flex items-center justify-between"><h6 class="font-medium">Бенефициар {{ index + 1 }}</h6><button type="button" class="text-sm text-red-700" @click="remove(index)">Удалить</button></div>
      <div class="grid grid-cols-2 gap-3">
        <label class="text-sm">ФИО<input :value="person.full_name || ''" :name="`beneficiaries.${index}.full_name`" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="edit(index, 'full_name', ($event.target as HTMLInputElement).value)"></label>
        <label class="text-sm">ИНН<input :value="person.inn || ''" inputmode="numeric" maxlength="12" :name="`beneficiaries.${index}.inn`" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="edit(index, 'inn', ($event.target as HTMLInputElement).value.replace(/\D/g, '').slice(0, 12))"></label>
        <label class="text-sm">Доля владения, %<input :value="person.share_percentage ?? ''" type="number" min="0" max="100" step="0.01" :name="`beneficiaries.${index}.share_percentage`" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="edit(index, 'share_percentage', ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value))"></label>
        <label class="text-sm">Адрес регистрации / проживания<input :value="person.registration_address || ''" :name="`beneficiaries.${index}.registration_address`" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="edit(index, 'registration_address', ($event.target as HTMLInputElement).value)"></label>
        <label class="col-span-2 text-sm">Основание отнесения к бенефициарам<select :value="person.beneficial_owner_basis || ''" :name="`beneficiaries.${index}.beneficial_owner_basis`" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @change="edit(index, 'beneficial_owner_basis', ($event.target as HTMLSelectElement).value)"><option value="">Выберите основание</option><option v-for="item in bases" :key="item.id" :value="item.id" :disabled="!item.is_active && item.id !== person.beneficial_owner_basis">{{ item.name }}{{ item.is_active ? '' : ' (неактивно)' }}</option></select></label>
        <label v-if="basisIsOther(person)" class="col-span-2 text-sm">Укажите причину <span class="text-red-700">*</span><textarea :value="person.beneficial_owner_basis_details || ''" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="edit(index, 'beneficial_owner_basis_details', ($event.target as HTMLTextAreaElement).value)" /></label>
      </div>
      <button v-if="!savedIds.has(person.id || '')" type="button" class="btn-primary" :disabled="saving || !person.full_name?.trim()" @click="savePerson">{{ saving ? 'Сохраняем…' : 'Сохранить и заполнить паспорт' }}</button>
      <QuestionnaireSopd v-else :application-id="applicationId" :sopd-signer-candidates="[candidate(person)]" @update="onSopdUpdate" :run-passport-confirmation="runPassportConfirmation" />
    </article>
    <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
  </section>
</template>
<script setup lang="ts">
import type { QuestionnaireData } from '~/features/applications/constants/application'
import type { QuestionnairePerson, QuestionnaireDictionaryItem } from '~/features/questionnaire/types'
import type { SopdSignerCandidate } from '~/features/checkout/types/sopdSigners'
import QuestionnaireSopd from '~/features/checkout/components/QuestionnaireSopd.vue'
const props = defineProps<{ applicationId?: string | null; saveBeneficiaries: () => Promise<boolean>; runPassportConfirmation: (confirm: () => Promise<void>) => Promise<void> }>()
const emit = defineEmits<{ update: [data: Partial<QuestionnaireData>] }>()
const store = useCheckoutStore(); const config = useRuntimeConfig()
const bases = ref<QuestionnaireDictionaryItem[]>([]); const reasons = ref<QuestionnaireDictionaryItem[]>([])
const dictionaryError = ref(''); const error = ref(''); const saving = ref(false)
const people = computed(() => store.questionnaireData.beneficiaries || [])
const absent = computed(() => store.questionnaireData.has_beneficiary === false)
const savedIds = ref(new Set(people.value.map(person => person.id).filter((id): id is string => Boolean(id))))
const reasonIsOther = computed(() => reasons.value.some(item => item.id === store.questionnaireData.no_beneficial_owner_reason && item.code === 'other'))
const basisIsOther = (person: QuestionnairePerson) => bases.value.some(item => item.id === person.beneficial_owner_basis && item.code === 'other_control_basis')
const loadDictionaries = async () => {
  dictionaryError.value = ''
  try {
    const result = await Promise.all(['beneficial_owner_bases', 'beneficial_owner_absence_reasons'].map(async kind => {
      const selected = kind === 'beneficial_owner_bases' ? people.value.map(person => person.beneficial_owner_basis).filter(Boolean) : [store.questionnaireData.no_beneficial_owner_reason].filter(Boolean)
      const responses = await Promise.all((selected.length ? selected : [undefined]).map(selected_id => $fetch<{ items: QuestionnaireDictionaryItem[] }>(`/api/v1/questionnaire-dictionaries/${kind}`, { baseURL: config.public.apiBase, credentials: 'include', query: { selected_id } })))
      return [...new Map(responses.flatMap(response => response.items).map(item => [item.id, item])).values()]
    }))
    bases.value = result[0]; reasons.value = result[1]
  } catch { dictionaryError.value = 'Не удалось загрузить справочники бенефициаров.' }
}
const onSopdUpdate = (data: Record<string, unknown>) => {
  if (Array.isArray(data.beneficiaries)) emit('update', { beneficiaries: data.beneficiaries as QuestionnairePerson[] })
}
const setAbsent = (value: boolean) => emit('update', { has_beneficiary: !value, beneficiaries: value ? [] : people.value, no_beneficial_owner_reason: null, no_beneficial_owner_reason_details: null })
const setReason = (value: string) => emit('update', { no_beneficial_owner_reason: value || null, no_beneficial_owner_reason_details: null })
const add = () => emit('update', { has_beneficiary: true, beneficiaries: [...people.value, { id: crypto.randomUUID(), full_name: '', is_pdl: false, name_changed: false }] })
const remove = (index: number) => emit('update', { beneficiaries: people.value.filter((_, i) => i !== index) })
const edit = <K extends keyof QuestionnairePerson>(index: number, key: K, value: QuestionnairePerson[K]) => {
  const updated = people.value.map((person, i) => i === index ? { ...person, [key]: value } : person)
  if (key === 'beneficial_owner_basis' && !basisIsOther(updated[index])) updated[index].beneficial_owner_basis_details = ''
  emit('update', { beneficiaries: updated })
}
const candidate = (person: QuestionnairePerson): SopdSignerCandidate => ({ key: `beneficiary:${person.id}`, full_name: person.full_name || '', role: 'beneficiary', role_label: 'Бенефициарный владелец', inn: person.inn || null, signing_method: 'sms', source: 'questionnaire', sort_order: 0 })
const savePerson = async () => {
  if (!props.applicationId) return
  saving.value = true; error.value = ''
  try {
    if (!await props.saveBeneficiaries()) {
      error.value = 'Не удалось сохранить бенефициара. Проверьте сообщение об ошибке в анкете и повторите.'
      return
    }
    savedIds.value = new Set(people.value.map(person => person.id).filter((id): id is string => Boolean(id)))
  }
  catch { error.value = 'Не удалось сохранить бенефициара. Проверьте поля и повторите.' }
  finally { saving.value = false }
}
const validate = () => absent.value ? Boolean(store.questionnaireData.no_beneficial_owner_reason && (!reasonIsOther.value || store.questionnaireData.no_beneficial_owner_reason_details?.trim())) : people.value.every(person => Boolean(person.full_name?.trim()) && (person.share_percentage == null || (person.share_percentage >= 0 && person.share_percentage <= 100)) && (!basisIsOther(person) || Boolean(person.beneficial_owner_basis_details?.trim())))
onMounted(loadDictionaries)
defineExpose({ validate })
</script>
