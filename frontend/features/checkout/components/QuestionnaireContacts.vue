<template>
  <div data-storefront-block="client.checkout" class="space-y-4">
    <section class="rounded-lg border p-4">
      <h5 class="mb-3 font-medium">Основной контакт</h5>
      <div class="grid grid-cols-2 gap-3">
        <label v-for="field in contactFields" :key="field.key" class="text-sm">{{ field.label }}
          <input :value="formData.contact_person[field.key]" :type="field.type" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" :name="`contact_person.${field.key}`" @input="updateContact(field.key, ($event.target as HTMLInputElement).value)">
        </label>
      </div>
    </section>
    <section class="rounded-lg border p-4">
      <h5 class="mb-3 font-medium">Контакты организации</h5>
      <div class="grid grid-cols-2 gap-3">
        <label class="text-sm">Телефон организации<input :value="formData.company_phone" name="company_phone" type="tel" placeholder="+7 (___) ___-__-__" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="formData.company_phone = formatPhone(($event.target as HTMLInputElement).value)"></label>
        <label class="text-sm">Email организации<input v-model="formData.company_email" name="company_email" type="email" class="storefront-control mt-1 w-full rounded-md border px-3 py-2"></label>
        <label class="text-sm">Сайт организации<input v-model="formData.company_website" name="company_website" type="text" placeholder="company.ru" class="storefront-control mt-1 w-full rounded-md border px-3 py-2"></label>
      </div>
      <label class="mt-3 flex items-center gap-2 text-sm"><input v-model="formData.website_in_blocked_domains_registry" name="website_in_blocked_domains_registry" type="checkbox">Сайт организации включён в реестр запрещённых доменов</label>
    </section>
    <section class="space-y-3 rounded-lg border p-4">
      <h5 class="font-medium">Адреса</h5>
      <label class="block text-sm">Юридический адрес<textarea v-model="formData.legal_address" name="legal_address" rows="2" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="legalAddressEdited = true" /></label>
      <label class="flex items-center gap-2 text-sm"><input v-model="formData.actual_address_same_as_legal" name="actual_address_same_as_legal" type="checkbox">Фактический адрес совпадает с юридическим</label>
      <label class="block text-sm">Фактический адрес<textarea v-model="formData.actual_address" name="actual_address" rows="2" :disabled="formData.actual_address_same_as_legal" class="storefront-control mt-1 w-full rounded-md border px-3 py-2 disabled:bg-gray-100" /></label>
      <label class="flex items-center gap-2 text-sm"><input v-model="formData.postal_address_matches_legal" name="postal_address_matches_legal" type="checkbox">Почтовый адрес совпадает с юридическим</label>
      <label class="block text-sm">Почтовый адрес<textarea v-model="formData.postal_address" name="postal_address" rows="2" :disabled="formData.postal_address_matches_legal" class="storefront-control mt-1 w-full rounded-md border px-3 py-2 disabled:bg-gray-100" /></label>
    </section>
    <p v-for="message in errors" :key="message" class="text-sm text-red-700" role="alert">{{ message }}</p>
  </div>
</template>
<script setup lang="ts">
import type { UUID } from '~/types/ids'
import type { QuestionnaireContact } from '~/features/questionnaire/types'
import type { QuestionnaireData } from '~/features/applications/constants/application'
interface FormData {
  legal_address: string; actual_address: string; actual_address_same_as_legal: boolean
  postal_address: string; postal_address_matches_legal: boolean; tax_system: string
  company_phone: string; company_email: string; company_website: string
  website_in_blocked_domains_registry: boolean; contact_person: QuestionnaireContact; contacts: QuestionnaireContact[]
}
const props = defineProps<{ companyExternalData?: Record<string, unknown> | null; autofilledFields?: Record<string, boolean>; initialData?: Partial<QuestionnaireData> | null; userContact?: { name: string; phone: string; email: string } | null; companyId?: UUID | null }>()
const emit = defineEmits<{ update: [data: FormData] }>()
const contactFields: Array<{ key: keyof QuestionnaireContact; label: string; type: string }> = [
  { key: 'name', label: 'ФИО', type: 'text' }, { key: 'position', label: 'Должность', type: 'text' },
  { key: 'phone', label: 'Телефон', type: 'tel' }, { key: 'email', label: 'Email', type: 'email' },
]
const formatPhone = (value: string): string => {
  if (!value.trim()) return ''
  let digits = value.replace(/\D/g, '')
  if (digits.startsWith('8')) digits = '7' + digits.slice(1)
  if (!digits.startsWith('7')) digits = '7' + digits
  digits = digits.slice(0, 11)
  return '+7' + (digits.length > 1 ? ' (' + digits.slice(1, 4) : '') + (digits.length >= 4 ? ') ' + digits.slice(4, 7) : '') + (digits.length >= 7 ? '-' + digits.slice(7, 9) : '') + (digits.length >= 9 ? '-' + digits.slice(9, 11) : '')
}
const initial = props.initialData || {}
const savedContact = initial.contact_person || initial.contacts?.[0]
const contact: QuestionnaireContact = { name: savedContact?.name ?? props.userContact?.name ?? '', position: savedContact?.position ?? '', phone: formatPhone(savedContact?.phone ?? props.userContact?.phone ?? ''), email: savedContact?.email ?? props.userContact?.email ?? '' }
const formData = ref<FormData>({ legal_address: initial.legal_address || '', actual_address: initial.actual_address || '', actual_address_same_as_legal: initial.actual_address_same_as_legal === true, postal_address: initial.postal_address || '', postal_address_matches_legal: initial.postal_address_matches_legal === true, tax_system: initial.tax_system || '', company_phone: formatPhone(initial.company_phone || ''), company_email: initial.company_email || '', company_website: initial.company_website || '', website_in_blocked_domains_registry: initial.website_in_blocked_domains_registry === true, contact_person: contact, contacts: [{ ...contact }] })
watch(() => props.initialData, (next, previous) => {
  if (!next || !previous) return
  const fields = ['legal_address', 'actual_address', 'postal_address', 'company_phone', 'company_email', 'company_website', 'tax_system'] as const
  for (const key of fields) if (formData.value[key] === (previous[key] || '')) formData.value[key] = next[key] || ''
  for (const key of ['actual_address_same_as_legal', 'postal_address_matches_legal', 'website_in_blocked_domains_registry'] as const) if (formData.value[key] === (previous[key] === true)) formData.value[key] = next[key] === true
  if (JSON.stringify(formData.value.contact_person) === JSON.stringify(previous.contact_person) && next.contact_person && JSON.stringify(formData.value.contact_person) !== JSON.stringify(next.contact_person)) { formData.value.contact_person = { ...next.contact_person }; formData.value.contacts = [{ ...next.contact_person }] }
}, { deep: true })
const legalAddressEdited = ref(false)
let lastAutofilledLegalAddress: string | null = null
watch(() => [props.companyExternalData, props.companyId] as const, ([company, id]) => {
  if (!id || company?.id !== id || legalAddressEdited.value) return
  const address = typeof company.legal_address === 'string' ? company.legal_address : ''
  if (address && (!formData.value.legal_address || formData.value.legal_address === lastAutofilledLegalAddress)) { formData.value.legal_address = address; lastAutofilledLegalAddress = address }
}, { immediate: true, deep: true })
watch(() => [formData.value.legal_address, formData.value.actual_address_same_as_legal, formData.value.postal_address_matches_legal] as const, () => {
  if (formData.value.actual_address_same_as_legal) formData.value.actual_address = formData.value.legal_address
  if (formData.value.postal_address_matches_legal) formData.value.postal_address = formData.value.legal_address
}, { immediate: true })
const updateContact = (key: keyof QuestionnaireContact, value: string) => { formData.value.contact_person[key] = key === 'phone' ? formatPhone(value) : value; formData.value.contacts = [{ ...formData.value.contact_person }] }
const errors = computed(() => {
  const result: string[] = []
  const data = formData.value
  for (const [label, value] of [['Телефон организации', data.company_phone], ['Телефон контакта', data.contact_person.phone]]) if (value && value.replace(/\D/g, '').length !== 11) result.push(`${label}: укажите 11 цифр`)
  for (const [label, value] of [['Email организации', data.company_email], ['Email контакта', data.contact_person.email]]) if (value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) result.push(`${label}: проверьте адрес`)
  if (data.company_website) { try { const url = new URL(/^https?:\/\//i.test(data.company_website) ? data.company_website : `https://${data.company_website}`); if (!['http:', 'https:'].includes(url.protocol) || !url.hostname.includes('.')) throw new Error() } catch { result.push('Сайт организации: укажите корректный адрес сайта') } }
  return result
})
const getData = (): FormData => ({ ...formData.value, contact_person: { ...formData.value.contact_person }, contacts: [{ ...formData.value.contact_person }] })
const validate = () => errors.value.length === 0
const isComplete = () => validate() && Boolean(formData.value.legal_address && formData.value.actual_address && formData.value.contact_person.name && formData.value.contact_person.phone && formData.value.contact_person.email)
watch(formData, () => emit('update', getData()), { deep: true })
defineExpose({ getData, validate, isComplete })
</script>
