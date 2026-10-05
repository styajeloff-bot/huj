<template>
  <Modal
    :show="true"
    :close-on-overlay="false"
    :closable="!saving"
    @close="requestClose"
    title="Информация о компании"
    size="5xl"
    :show-footer="false"
    body-class="pb-0"
  >
    <div data-storefront-block="client.cabinet" class="space-y-6">
      <div class="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
        <div class="space-y-4">
          <section class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4">
            <h4 class="mb-4 text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Основная информация</h4>
            <div v-if="editing" class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <FormField label="Название" required :error="fieldErrors.name"><input v-model="draft.name" class="input-field" maxlength="500" /></FormField>
              <FormField label="Тип" required :error="fieldErrors.company_type">
                <select v-model="draft.company_type" :class="['select-field', fieldErrors.company_type ? 'border-red-500 focus:border-red-500 focus:ring-red-500' : '']"><option v-for="type in companyTypes" :key="type.value" :value="type.value">{{ type.label }}</option></select>
                <section
                  v-if="transitionBlockers.length"
                  class="mt-2 max-h-40 overflow-y-auto rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"
                  role="alert"
                  aria-labelledby="company-type-transition-conflict-title"
                  tabindex="0"
                >
                  <h5 id="company-type-transition-conflict-title" class="font-semibold">Нельзя изменить тип компании</h5>
                  <ul class="mt-2 space-y-2" aria-label="Препятствия для изменения типа компании">
                    <li v-for="blocker in transitionBlockers" :key="`${blocker.label}-${blocker.count}-${blocker.resolution_hint}`">
                      <span class="font-medium">{{ blocker.label }}: {{ blocker.count }}.</span>
                      <span class="ml-1">{{ blocker.resolution_hint }}</span>
                    </li>
                  </ul>
                </section>
              </FormField>
              <FormField label="ИНН" required :error="fieldErrors.inn"><input v-model="draft.inn" class="input-field" inputmode="numeric" maxlength="12" @input="draft.inn = digitsOnly($event)" /></FormField>
              <FormField label="КПП" required :error="fieldErrors.kpp"><input v-model="draft.kpp" class="input-field" inputmode="numeric" maxlength="9" @input="draft.kpp = digitsOnly($event)" /></FormField>
              <FormField label="ОГРН" required :error="fieldErrors.ogrn"><input v-model="draft.ogrn" class="input-field" inputmode="numeric" maxlength="13" @input="draft.ogrn = digitsOnly($event)" /></FormField>
              <FormField label="Статус" required :error="fieldErrors.is_active">
                <select v-model="draft.is_active" class="select-field"><option :value="true">Активна</option><option :value="false">Неактивна</option></select>
              </FormField>
              <p v-if="willDeactivate" class="md:col-span-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
                Внимание: деактивация компании каскадно ограничит её доступность и доступ связанных пользователей в рабочих списках.
              </p>
            </div>
            <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Detail label="Название" :value="company.name" />
              <Detail label="Тип"><span class="mt-1 inline-flex rounded-full px-2 py-1 text-xs font-semibold" :class="getTypeColor(company.company_type)">{{ getTypeLabel(company.company_type) }}</span></Detail>
              <Detail v-if="company.inn" label="ИНН" :value="company.inn" /><Detail v-if="company.kpp" label="КПП" :value="company.kpp" /><Detail v-if="company.ogrn" label="ОГРН" :value="company.ogrn" />
              <Detail label="Статус"><StatusBadge :active="isCompanyActive(company.is_active)" /></Detail>
            </div>
          </section>

          <section class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4">
            <h4 class="mb-4 text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Контактная информация</h4>
            <div v-if="editing" class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <FormField label="Телефон" :error="fieldErrors.phone"><input :value="draft.phone" class="input-field" type="tel" inputmode="tel" autocomplete="tel" maxlength="18" placeholder="+7 (495) 100-02-00" @input="updatePhone($event)" @paste.prevent="pastePhone($event)" /></FormField>
              <FormField label="Email" :error="fieldErrors.email"><input v-model="draft.email" class="input-field" type="email" maxlength="255" /></FormField>
              <FormField class="md:col-span-2" label="Веб-сайт" :error="fieldErrors.website"><input v-model="draft.website" class="input-field" type="url" maxlength="255" /></FormField>
              <FormField class="md:col-span-2" label="Юридический адрес" required :error="fieldErrors.legal_address"><textarea v-model="draft.legal_address" class="input-field min-h-20" maxlength="1000" /></FormField>
              <FormField class="md:col-span-2" label="Фактический адрес" :error="fieldErrors.actual_address"><textarea v-model="draft.actual_address" class="input-field min-h-20" maxlength="1000" /></FormField>
            </div>
            <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Detail v-if="company.phone" label="Телефон" :value="formatCompanyPhone(company.phone)" /><Detail v-if="company.email" label="Email" :value="company.email" />
              <Detail v-if="company.website" class="md:col-span-2" label="Веб-сайт"><a :href="company.website" target="_blank" class="mt-1 block text-sm text-[color:var(--storefront-link,#2563eb)]">{{ company.website }}</a></Detail>
              <Detail v-if="company.legal_address" class="md:col-span-2" label="Юридический адрес" :value="company.legal_address" /><Detail v-if="company.actual_address" class="md:col-span-2" label="Фактический адрес" :value="company.actual_address" />
            </div>
          </section>

          <div v-if="canEdit && editing" class="flex justify-start gap-3">
            <button type="button" class="btn-primary" :disabled="saving" @click="save">{{ saving ? 'Сохранение...' : 'Сохранить изменения' }}</button>
            <button type="button" class="btn-secondary" :disabled="saving" @click="cancelEdit">Отмена</button>
          </div>

          <section class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4">
            <h4 class="mb-4 text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Статистика</h4>
            <div class="grid grid-cols-1 gap-4 md:grid-cols-3"><Stat :value="String(company.user_count || 0)" label="Пользователей" /><Stat :value="String(company.application_count || 0)" label="Заявок" /><Stat :value="formatDate(company.created_at)" label="Дата создания" /></div>
          </section>

          <p v-if="saveError" class="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{{ saveError }}</p>
        </div>

        <aside class="space-y-4">
          <button
            v-if="!editing && canEdit"
            type="button"
            class="btn-secondary w-full justify-center"
            :disabled="saving"
            @click="startEdit"
          >
            Редактировать
          </button>
          <button
            v-if="!editing && canEdit"
            type="button"
            class="btn-secondary w-full justify-center"
            @click="showChangeHistory = true"
          >
            Просмотреть историю изменений
          </button>

          <section v-if="!editing && isDistributor" class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4"><h4 class="text-lg font-semibold">Марки дистрибьютора</h4><SearchableDropdown v-model="distributorBrandIdsProxy" class="mt-4" label="Марка" placeholder="Выберите марки" :items="distributorBrandItems" label-key="name" value-key="id" multiple show-select-all :disabled="distributorBrandsLoading || distributorBrandsSaving" /><p v-if="distributorBrandsError" class="mt-3 text-sm text-red-600">{{ distributorBrandsError }}</p><button type="button" class="btn-primary mt-4" :disabled="distributorBrandsLoading || distributorBrandsSaving" @click="emit('save-distributor-brands')">{{ distributorBrandsSaving ? 'Сохранение...' : 'Сохранить' }}</button></section>
          <section v-if="!editing && isLeasingCompany" class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4"><h4 class="text-lg font-semibold">Связи с подрядчиками</h4><SearchableDropdown v-model="contractorIdsProxy" class="mt-4" label="Подрядчики" placeholder="Выберите подрядчиков" :items="contractorDropdownItems" label-key="display_name" value-key="id" multiple show-select-all :disabled="contractorLoading || contractorControlsDisabled" /><p v-if="contractorError" class="mt-3 text-sm text-red-600">{{ contractorError }}</p><button type="button" class="btn-primary mt-4" :disabled="contractorLoading || contractorSaving || contractorControlsDisabled" @click="emit('save-contractors')">{{ contractorSaving ? 'Сохранение...' : 'Сохранить связи' }}</button></section>
        </aside>
      </div>
      <section class="rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4"><CompanyMembersPanel :fixed-company-id="company.id" :fixed-company-name="company.name" /></section>
    </div>
  </Modal>

  <CompanyChangeHistoryModal
    v-if="showChangeHistory"
    :company-id="company.id"
    @close="showChangeHistory = false"
  />

  <Modal
    v-if="showDiscardDialog"
    :show="true"
    :closable="!saving"
    :close-on-overlay="false"
    :show-footer="true"
    title="Сохранить изменения?"
    size="sm"
    @close="cancelDiscard"
  >
    <p class="text-sm text-gray-700">Несохранённые изменения будут потеряны, если не сохранить их сейчас.</p>
    <template #footer>
      <button type="button" class="btn-primary" :disabled="saving" @click="saveAndClose">{{ saving ? 'Сохранение...' : 'Сохранить' }}</button>
      <button type="button" class="btn-danger" :disabled="saving" @click="discardAndClose">Не сохранять</button>
      <button type="button" class="btn-secondary" :disabled="saving" @click="cancelDiscard">Отмена</button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { defineComponent, h, watch } from 'vue'
import CompanyMembersPanel from './CompanyMembersPanel.vue'
import CompanyChangeHistoryModal from './CompanyChangeHistoryModal.vue'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { createCompaniesAdminApi, type AdminCompanyDetail, type AdminCompanyTypeTransitionBlocker, type AdminCompanyUpdateField, type AdminCompanyUpdatePayload, type AdminCompanyValidationError } from '~/features/admin/companies/manage/api/companiesAdminApi'
import { formatCompanyPhone } from '~/features/company/utils/companyPhone'
import type { DropdownItem } from '~/types/index'
import type { CatalogId, UUID } from '~/types/ids'
import type { CompanyType } from '~/types/features'

interface ContractorDropdownItem extends DropdownItem { id: UUID; display_name: string }
interface DistributorBrandDropdownItem extends DropdownItem { id: CatalogId; name: string }
interface CompanyDraft { name: string; company_type: CompanyType; inn: string; kpp: string; ogrn: string; is_active: boolean; phone: string; email: string; website: string; legal_address: string; actual_address: string }
type FieldErrors = Partial<Record<AdminCompanyUpdateField, string>>

const FormField = defineComponent({
  inheritAttrs: false,
  props: { label: { type: String, required: true }, required: { type: Boolean, default: false }, error: { type: String, default: '' } },
  setup(fieldProps, { attrs, slots }) {
    return () => h('div', attrs, [
      h('label', { class: 'mb-1 block text-sm font-medium text-gray-700' }, `${fieldProps.label}${fieldProps.required ? ' *' : ''}`),
      slots.default?.(),
      fieldProps.error ? h('p', { class: 'mt-1 text-sm text-red-600' }, fieldProps.error) : null
    ])
  }
})
const Detail = defineComponent({
  inheritAttrs: false,
  props: { label: { type: String, required: true }, value: { type: String, default: '' } },
  setup(detailProps, { attrs, slots }) {
    return () => h('div', attrs, [h('label', { class: 'block text-sm font-medium text-gray-700' }, detailProps.label), slots.default?.() ?? h('p', { class: 'mt-1 text-sm text-gray-900' }, detailProps.value)])
  }
})
const Stat = defineComponent({
  props: { value: { type: String, required: true }, label: { type: String, required: true } },
  setup(statProps) { return () => h('div', { class: 'text-center' }, [h('div', { class: 'text-2xl font-semibold text-gray-700' }, statProps.value), h('div', { class: 'text-sm text-gray-500' }, statProps.label)]) }
})
const StatusBadge = defineComponent({
  props: { active: { type: Boolean, default: false } },
  setup(statusProps) { return () => h('span', { class: statusProps.active ? 'mt-1 inline-flex rounded-full bg-green-100 px-2 py-1 text-xs font-semibold text-green-800' : 'mt-1 inline-flex rounded-full bg-red-100 px-2 py-1 text-xs font-semibold text-red-800' }, statusProps.active ? 'Активна' : 'Неактивна') }
})

const props = withDefaults(defineProps<{ company: AdminCompanyDetail; contractorDropdownItems?: ContractorDropdownItem[]; contractorIds?: UUID[]; contractorLoading?: boolean; contractorSaving?: boolean; contractorError?: string; contractorControlsDisabled?: boolean; distributorBrandItems?: DistributorBrandDropdownItem[]; distributorBrandIds?: CatalogId[]; distributorBrandsLoading?: boolean; distributorBrandsSaving?: boolean; distributorBrandsError?: string }>(), { contractorDropdownItems: () => [], contractorIds: () => [], contractorLoading: false, contractorSaving: false, contractorError: '', contractorControlsDisabled: false, distributorBrandItems: () => [], distributorBrandIds: () => [], distributorBrandsLoading: false, distributorBrandsSaving: false, distributorBrandsError: '' })
const emit = defineEmits<{ close: []; updated: [company: AdminCompanyDetail]; 'save-contractors': []; 'save-distributor-brands': []; 'update:contractorIds': [value: UUID[]]; 'update:distributorBrandIds': [value: CatalogId[]] }>()
const authStore = useAuthStore()
const api = createCompaniesAdminApi(useRuntimeConfig())
const editing = ref(false)
const saving = ref(false)
const showDiscardDialog = ref(false)
const showChangeHistory = ref(false)
const saveError = ref('')
const fieldErrors = ref<FieldErrors>({})
const transitionBlockers = ref<AdminCompanyTypeTransitionBlocker[]>([])
const draft = ref<CompanyDraft>(draftFromCompany(props.company))
const canEdit = computed(() => authStore.isCarCraftEmployee)
const isLeasingCompany = computed(() => props.company.company_type === 'leasing_company')
const isDistributor = computed(() => props.company.company_type === 'distributor')
const willDeactivate = computed(() => props.company.is_active !== false && !draft.value.is_active)
const contractorIdsProxy = computed({ get: () => props.contractorIds, set: (value: UUID[]) => emit('update:contractorIds', value) })
const distributorBrandIdsProxy = computed({ get: () => props.distributorBrandIds, set: (value: CatalogId[]) => emit('update:distributorBrandIds', value) })
const companyTypes: Array<{ value: CompanyType; label: string }> = [{ value: 'dealer', label: 'Дилер' }, { value: 'leasing_company', label: 'Лизинговая компания' }, { value: 'distributor', label: 'Дистрибьютор' }, { value: 'other', label: 'Другое' }]
const typeLabels: Record<CompanyType, string> = { dealer: 'Дилер', leasing_company: 'Лизинговая компания', distributor: 'Дистрибьютор', other: 'Другое' }
const typeColors: Record<CompanyType, string> = { dealer: 'bg-green-100 text-green-800', leasing_company: 'bg-purple-100 text-purple-800', distributor: 'bg-orange-100 text-orange-800', other: 'bg-gray-100 text-gray-800' }

function draftFromCompany(company: AdminCompanyDetail): CompanyDraft { return { name: company.name, company_type: isCompanyType(company.company_type) ? company.company_type : 'other', inn: company.inn ?? '', kpp: company.kpp ?? '', ogrn: company.ogrn ?? '', is_active: isCompanyActive(company.is_active), phone: formatCompanyPhone(company.phone ?? ''), email: company.email ?? '', website: company.website ?? '', legal_address: company.legal_address ?? '', actual_address: company.actual_address ?? '' } }
function isCompanyActive(isActive: boolean | null | undefined): boolean { return isActive !== false }
function isCompanyType(value: string | undefined): value is CompanyType { return value === 'dealer' || value === 'leasing_company' || value === 'distributor' || value === 'other' }
function startEdit() { draft.value = draftFromCompany(props.company); fieldErrors.value = {}; saveError.value = ''; editing.value = true }
function cancelEdit() { if (!isDirty.value) discardEdit(); else showDiscardDialog.value = true }
function requestClose() { if (saving.value) return; if (!editing.value || !isDirty.value) { clearTransitionConflict(); emit('close') } else showDiscardDialog.value = true }
function cancelDiscard() { if (!saving.value) showDiscardDialog.value = false }
function clearTransitionConflict() { transitionBlockers.value = [] }
function discardEdit() { draft.value = draftFromCompany(props.company); editing.value = false; fieldErrors.value = {}; saveError.value = '' }
function discardAndClose() { if (saving.value) return; showDiscardDialog.value = false; discardEdit(); clearTransitionConflict(); emit('close') }
const isDirty = computed(() => hasChanges(props.company, draft.value))
watch(() => draft.value.company_type, (companyType) => { if (companyType === props.company.company_type) clearTransitionConflict() })
function normalizeOptional(value: string): string | null { const normalized = value.trim(); return normalized || null }
function digitsOnly(event: Event): string { return (event.target as HTMLInputElement).value.replace(/\D/g, '') }
function russianSubscriberDigits(value: string): string { const digits = value.replace(/\D/g, ''); return (digits.startsWith('7') || digits.startsWith('8') ? digits.slice(1) : digits).slice(0, 10) }
function normalizeRussianPhone(value: string): string | null { const digits = russianSubscriberDigits(value); return digits ? `+7${digits}` : null }
function updatePhone(event: Event) { draft.value.phone = formatCompanyPhone((event.target as HTMLInputElement).value) }
function pastePhone(event: ClipboardEvent) { draft.value.phone = formatCompanyPhone(event.clipboardData?.getData('text') ?? '') }
function validate(): boolean {
  const errors: FieldErrors = {}
  const payload = changedPayload(props.company, draft.value)
  const name = draft.value.name.trim()
  const inn = draft.value.inn.trim()
  const kpp = draft.value.kpp.trim()
  const ogrn = draft.value.ogrn.trim()
  const legalAddress = draft.value.legal_address.trim()
  if (!name) errors.name = 'Укажите название компании'
  else if ('name' in payload && name.length > 500) errors.name = 'Название не должно быть длиннее 500 символов'
  if (!isCompanyType(draft.value.company_type)) errors.company_type = 'Выберите тип компании'
  if (!inn) errors.inn = 'Укажите ИНН'
  else if ('inn' in payload && !/^\d{10}(\d{2})?$/.test(inn)) errors.inn = 'ИНН должен содержать 10 или 12 цифр'
  if (!kpp) errors.kpp = 'Укажите КПП'
  else if ('kpp' in payload && !/^\d{9}$/.test(kpp)) errors.kpp = 'КПП должен содержать 9 цифр'
  if (!ogrn) errors.ogrn = 'Укажите ОГРН'
  else if ('ogrn' in payload && !/^\d{13}$/.test(ogrn)) errors.ogrn = 'ОГРН должен содержать 13 цифр'
  if (typeof draft.value.is_active !== 'boolean') errors.is_active = 'Укажите статус компании'
  if (!legalAddress) errors.legal_address = 'Укажите юридический адрес'
  else if ('legal_address' in payload && legalAddress.length > 1000) errors.legal_address = 'Юридический адрес не должен быть длиннее 1000 символов'
  if (typeof payload.actual_address === 'string' && payload.actual_address.length > 1000) errors.actual_address = 'Фактический адрес не должен быть длиннее 1000 символов'
  if (typeof payload.phone === 'string' && !/^\+7\d{10}$/.test(payload.phone)) errors.phone = 'Введите телефон в формате +7 (XXX) XXX-XX-XX'
  if (typeof payload.email === 'string' && (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email) || payload.email.length > 255)) errors.email = 'Укажите корректный email длиной до 255 символов'
  if (typeof payload.website === 'string' && (!isValidWebsite(payload.website) || payload.website.length > 255)) errors.website = 'Укажите корректный адрес сайта длиной до 255 символов'
  fieldErrors.value = errors
  return Object.keys(errors).length === 0
}
function isValidWebsite(value: string): boolean { try { const url = new URL(value); return url.protocol === 'http:' || url.protocol === 'https:' } catch { return false } }
function changedPayload(company: AdminCompanyDetail, value: CompanyDraft): AdminCompanyUpdatePayload {
  const payload: AdminCompanyUpdatePayload = {}
  const name = value.name.trim()
  const companyType = value.company_type
  const inn = value.inn.trim()
  const kpp = value.kpp.trim()
  const ogrn = value.ogrn.trim()
  const phone = normalizeRussianPhone(value.phone)
  const email = normalizeOptional(value.email)
  const website = normalizeOptional(value.website)
  const legalAddress = value.legal_address.trim()
  const actualAddress = normalizeOptional(value.actual_address)
  if (name !== company.name) payload.name = name
  if (companyType !== company.company_type) payload.company_type = companyType
  if (inn !== (company.inn ?? '')) payload.inn = inn
  if (kpp !== (company.kpp ?? '')) payload.kpp = kpp
  if (ogrn !== (company.ogrn ?? '')) payload.ogrn = ogrn
  if (value.is_active !== company.is_active) payload.is_active = value.is_active
  if (phone !== normalizeRussianPhone(company.phone ?? '')) payload.phone = phone
  if (email !== (company.email ?? null)) payload.email = email
  if (website !== (company.website ?? null)) payload.website = website
  if (legalAddress !== (company.legal_address ?? '')) payload.legal_address = legalAddress
  if (actualAddress !== (company.actual_address ?? null)) payload.actual_address = actualAddress
  return payload
}
function hasChanges(company: AdminCompanyDetail, value: CompanyDraft): boolean { return Object.keys(changedPayload(company, value)).length > 0 }
async function save(): Promise<boolean> { if (saving.value || !isDirty.value || !validate()) return false; saving.value = true; saveError.value = ''; try { const response = await api.patchAdminCompany(props.company.id, changedPayload(props.company, draft.value)); clearTransitionConflict(); emit('updated', response.company); editing.value = false; return true } catch (error: unknown) { const errors = readFieldErrors(error); fieldErrors.value = errors.fields; saveError.value = errors.message; if (errors.transitionBlockers !== null) transitionBlockers.value = errors.transitionBlockers; return false } finally { saving.value = false } }
async function saveAndClose() { const saved = await save(); if (!saved) { showDiscardDialog.value = false; return }; showDiscardDialog.value = false; emit('close') }
function readFieldErrors(error: unknown): { fields: FieldErrors; message: string; transitionBlockers: AdminCompanyTypeTransitionBlocker[] | null } { const data = (error as { data?: { code?: unknown; field_errors?: unknown; detail?: unknown; message?: unknown; blockers?: unknown } }).data; const blockers = transitionConflictBlockers(data); if (blockers) return { fields: { company_type: 'Изменение типа компании сейчас невозможно.' }, message: '', transitionBlockers: blockers }; const fields: FieldErrors = {}; if (Array.isArray(data?.field_errors)) { for (const item of data.field_errors) { const fieldError = item as AdminCompanyValidationError; if (isUpdateField(fieldError.field) && typeof fieldError.message === 'string') fields[fieldError.field] = fieldError.message } } const message = typeof data?.message === 'string' ? data.message : typeof data?.detail === 'string' ? data.detail : Object.keys(fields).length ? 'Исправьте поля с ошибками.' : 'Не удалось сохранить изменения. Попробуйте ещё раз.'; return { fields, message, transitionBlockers: null } }
function transitionConflictBlockers(data: { code?: unknown; field_errors?: unknown; blockers?: unknown } | undefined): AdminCompanyTypeTransitionBlocker[] | null {
  const fieldError = Array.isArray(data?.field_errors) ? data.field_errors.find((item) => (item as { field?: unknown; code?: unknown }).field === 'company_type' && (item as { code?: unknown }).code === 'TYPE_TRANSITION_CONFLICT') as { blockers?: unknown } | undefined : undefined
  if (data?.code !== 'TYPE_TRANSITION_CONFLICT' && !fieldError) return null
  const blockers = Array.isArray(data?.blockers) ? data.blockers : Array.isArray(fieldError?.blockers) ? fieldError.blockers : []
  return blockers as AdminCompanyTypeTransitionBlocker[]
}
function isUpdateField(value: unknown): value is AdminCompanyUpdateField { return typeof value === 'string' && ['name', 'company_type', 'inn', 'kpp', 'ogrn', 'is_active', 'phone', 'email', 'website', 'legal_address', 'actual_address'].includes(value) }
function getTypeLabel(type: string | undefined): string { return isCompanyType(type) ? typeLabels[type] : type || '' }
function getTypeColor(type: string | undefined): string { return isCompanyType(type) ? typeColors[type] : typeColors.other }
function formatDate(value: string | undefined): string { return value ? new Date(value).toLocaleDateString('ru-RU') : '' }
</script>
