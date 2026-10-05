<template>
  <section v-if="visible" class="space-y-3 rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-[color:var(--storefront-surface-muted,#f9fafb)] p-3">
    <div class="flex items-center justify-between gap-3">
      <h6 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">Проверка паспортных данных</h6>
      <span v-if="saving" class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">Сохраняем данные…</span>
    </div>
    <p class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">Проверьте распознанные данные и подтвердите их перед отправкой SMS или работой с шаблоном.</p>
    <div class="grid grid-cols-2 gap-3">
      <label v-for="field in fieldsConfig" :key="field.key" class="block text-xs text-[color:var(--storefront-text-muted,#4b5563)]">
        <span class="mb-1 flex items-center gap-1">
          {{ field.label }}<span v-if="required(field.key)" class="text-[color:var(--storefront-error-text,#dc2626)]">*</span>
          <span v-if="confidenceLabel(field.key)" :class="confidenceClass(field.key)">{{ confidenceLabel(field.key) }}</span>
        </span>
        <div v-if="field.key === 'nationality'" class="relative">
          <input
            :value="citizenshipQuery ?? fields.nationality"
            role="combobox"
            aria-autocomplete="list"
            :aria-expanded="citizenshipDropdownOpen"
            aria-controls="citizenship-options"
            :disabled="citizenshipsLoading"
            placeholder="Начните вводить гражданство"
            class="storefront-control w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-white px-2 py-1.5 text-sm"
            :class="fieldError(field.key) ? 'border-[color:var(--storefront-error-border,#dc2626)]' : ''"
            @focus="openCitizenshipDropdown"
            @input="searchCitizenship(($event.target as HTMLInputElement).value)"
            @blur="closeCitizenshipDropdown"
          >
          <ul v-if="citizenshipDropdownOpen && filteredCitizenships.length" id="citizenship-options" role="listbox" class="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded border bg-white shadow">
            <li v-for="citizenship in filteredCitizenships" :key="citizenship.id" role="option" class="cursor-pointer px-2 py-1.5 text-sm hover:bg-gray-100" @mousedown.prevent="selectCitizenship(citizenship.citizenship_name)">{{ citizenship.citizenship_name }}</li>
          </ul>
          <span v-else-if="citizenshipDropdownOpen && citizenshipQuery && !citizenshipsLoading" class="mt-1 block text-xs">Гражданство не найдено</span>
        </div>
        <select
          v-else-if="field.key === 'gender'"
          :value="fields.gender || ''"
          class="storefront-control w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-white px-2 py-1.5 text-sm"
          :class="fieldError(field.key) ? 'border-[color:var(--storefront-error-border,#dc2626)]' : ''"
          @change="edit(field.key, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">Выберите пол</option><option value="male">Мужской</option><option value="female">Женский</option>
        </select>
        <input
          v-else
          :value="fields[field.key] || ''"
          :maxlength="maxLength(field.key)"
          :placeholder="field.date ? 'ДД.ММ.ГГГГ' : field.key === 'code' && isRussian ? '000-000' : ''"
          :inputmode="numericField(field.key) ? 'numeric' : 'text'"
          class="storefront-control w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-white px-2 py-1.5 text-sm"
          :class="fieldError(field.key) ? 'border-[color:var(--storefront-error-border,#dc2626)]' : ''"
          @input="edit(field.key, ($event.target as HTMLInputElement).value)"
          @blur="touch(field.key)"
        >
        <span v-if="fieldError(field.key)" class="mt-1 block text-[color:var(--storefront-error-text,#dc2626)]">{{ fieldError(field.key) }}</span>
      </label>
    </div>
    <p v-if="error" class="text-xs text-[color:var(--storefront-error-text,#dc2626)]">{{ error }}</p>
    <div class="flex items-center gap-3">
      <button type="button" class="storefront-action-primary rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50" :disabled="!canSave || saving || hasClientErrors" @click="save">
        {{ saving ? 'Сохранение…' : 'Сохранить изменения' }}
      </button>
      <span v-if="!actionsAllowed" class="text-xs text-[color:var(--storefront-warning-text,#a16207)]">Подтвердите актуальные паспортные данные, чтобы продолжить.</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

export type PassportFieldKey = 'surname' | 'name' | 'patronymic' | 'nationality' | 'gender' | 'birthDate' | 'birthPlace' | 'passportSeries' | 'passportNumber' | 'givenDate' | 'code' | 'givenWhom'
export type PassportFields = Record<PassportFieldKey, string>
export type Citizenship = { id: number; code2: string; code3: string; citizenship_name: string }

const props = defineProps<{
  visible: boolean
  fields: PassportFields
  confidence: Partial<Record<PassportFieldKey, number | null>>
  showConfidence: boolean
  canSave: boolean
  saving: boolean
  actionsAllowed: boolean
  error: string
  fieldErrors: Partial<Record<PassportFieldKey, string>>
  citizenships: Citizenship[]
  citizenshipsLoading: boolean
}>()
const emit = defineEmits<{ (e: 'edit', key: PassportFieldKey, value: string): void; (e: 'save'): void }>()

const fieldsConfig: Array<{ key: PassportFieldKey; label: string; date?: boolean }> = [
  { key: 'name', label: 'Имя' }, { key: 'surname', label: 'Фамилия' }, { key: 'patronymic', label: 'Отчество' },
  { key: 'nationality', label: 'Гражданство' }, { key: 'gender', label: 'Пол' }, { key: 'birthDate', label: 'Дата рождения', date: true },
  { key: 'birthPlace', label: 'Место рождения' }, { key: 'passportSeries', label: 'Серия документа' }, { key: 'passportNumber', label: 'Номер документа' },
  { key: 'givenDate', label: 'Дата выдачи', date: true }, { key: 'code', label: 'Код подразделения' }, { key: 'givenWhom', label: 'Кем выдан' },
]
const touched = ref<Partial<Record<PassportFieldKey, boolean>>>({})
const citizenshipQuery = ref<string | null>(null)
const citizenshipDropdownOpen = ref(false)
const filteredCitizenships = computed(() => {
  const query = (citizenshipQuery.value || '').toLocaleLowerCase('ru-RU')
  return props.citizenships.filter(citizenship => citizenship.citizenship_name.toLocaleLowerCase('ru-RU').startsWith(query))
})
const selectCitizenship = (citizenshipName: string) => {
  citizenshipQuery.value = null
  citizenshipDropdownOpen.value = false
  edit('nationality', citizenshipName)
}
const openCitizenshipDropdown = () => {
  citizenshipQuery.value = null
  citizenshipDropdownOpen.value = true
}
const closeCitizenshipDropdown = () => {
  citizenshipDropdownOpen.value = false
  citizenshipQuery.value = null
  touch('nationality')
}
const searchCitizenship = (query: string) => { citizenshipQuery.value = query }
const isRussian = computed(() => props.fields.nationality === 'Российская Федерация')
const isForeign = computed(() => props.fields.nationality.trim() !== '' && !isRussian.value)
const required = (key: PassportFieldKey) => isForeign.value
  ? ['surname', 'name', 'nationality', 'gender', 'birthDate', 'passportNumber'].includes(key)
  : true
const numericField = (key: PassportFieldKey) => isRussian.value && ['passportSeries', 'passportNumber', 'code'].includes(key)
const maxLength = (key: PassportFieldKey) => {
  if (key === 'givenWhom') return 250
  if (key === 'birthDate' || key === 'givenDate') return 10
  if (isForeign.value) return 30
  if (key === 'passportSeries' || key === 'passportNumber') return 10
  if (key === 'code') return 7
  return undefined
}
const calendarDate = (value: string) => {
  if (!/^\d{2}\.\d{2}\.\d{4}$/.test(value)) return false
  const [day, month, year] = value.split('.').map(Number)
  const date = new Date(year, month - 1, day)
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
}
const clientError = (key: PassportFieldKey): string => {
  const value = props.fields[key].trim()
  if (key === 'nationality' && !value) return 'Укажите гражданство'
  if (key === 'nationality' && !props.citizenships.some(citizenship => citizenship.citizenship_name === value)) return 'Выберите гражданство из списка'
  if (required(key) && !value) return 'Поле обязательно для заполнения'
  if ((key === 'birthDate' || key === 'givenDate') && value && !calendarDate(value)) return 'Укажите реальную дату в формате ДД.ММ.ГГГГ'
  if (!isRussian.value || !value) return ''
  if ((key === 'passportSeries' || key === 'passportNumber') && !/^\d{1,10}$/.test(value)) return 'Только цифры, не более 10 символов'
  if (key === 'code' && !/^\d{3}-\d{3}$/.test(value)) return 'Укажите код в формате 000-000'
  return ''
}
const fieldError = (key: PassportFieldKey) => props.fieldErrors[key] || ((touched.value[key] || key === 'nationality') ? clientError(key) : '')
const hasClientErrors = computed(() => fieldsConfig.some(field => clientError(field.key) !== ''))
const touch = (key: PassportFieldKey) => { touched.value[key] = true }
const normalizeInput = (key: PassportFieldKey, raw: string) => {
  if (key === 'givenWhom') return raw.slice(0, 250)
  if (!isRussian.value) {
    if (key === 'birthDate' || key === 'givenDate') {
      const digits = raw.replace(/\D/g, '').slice(0, 8)
      return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)].filter(Boolean).join('.')
    }
    return raw.slice(0, 30)
  }
  if (key === 'passportSeries' || key === 'passportNumber') return raw.replace(/\D/g, '').slice(0, 10)
  if (key === 'code') {
    const digits = raw.replace(/\D/g, '').slice(0, 6)
    return digits.length > 3 ? `${digits.slice(0, 3)}-${digits.slice(3)}` : digits
  }
  if (key === 'birthDate' || key === 'givenDate') {
    const digits = raw.replace(/\D/g, '').slice(0, 8)
    return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)].filter(Boolean).join('.')
  }
  return raw
}
const edit = (key: PassportFieldKey, value: string) => { touch(key); emit('edit', key, normalizeInput(key, value)) }
const save = () => { for (const field of fieldsConfig) touch(field.key); if (!hasClientErrors.value) emit('save') }
const confidenceLabel = (key: PassportFieldKey) => props.showConfidence && props.confidence[key] !== null && props.confidence[key] !== undefined ? `${props.confidence[key]}%` : ''
const confidenceClass = (key: PassportFieldKey) => { const confidence = props.confidence[key] ?? 0; return confidence >= 91 ? 'text-[color:#16a34a]' : confidence >= 61 ? 'text-[color:#ca8a04]' : 'text-[color:#dc2626]' }
</script>
