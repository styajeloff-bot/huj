<template>
  <Modal :show="show" :title="item.display_name" size="lg" :close-on-overlay="!sending" :closable="!sending" @close="emit('close')">
    <form class="space-y-5" @submit.prevent="submit">
      <fieldset :disabled="sending" class="space-y-4">
        <p v-if="comments" class="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-900">{{ comments }}</p>
        <template v-if="item.has_form">
          <div v-if="kind === 'main_counterparties'" class="space-y-3">
            <h4 class="font-medium">{{ labelFor('counterparties', 'Основные контрагенты') }}</h4>
            <div v-for="(row, index) in counterparties" :key="index" class="grid grid-cols-[1fr_2fr_auto] gap-2">
              <label class="text-sm">{{ labelFor('inn', 'ИНН') }} <span class="text-red-700">*</span><input :value="row.inn" inputmode="numeric" maxlength="12" class="storefront-control mt-1 w-full rounded-md border px-3 py-2 text-sm" :placeholder="placeholderFor('inn', 'ИНН')" @beforeinput="insertDigits($event, row.inn, 12, value => counterparties[index].inn = value)" @paste="pasteDigits($event, row.inn, 12, value => counterparties[index].inn = value)" @input="updateCounterpartyInn(index, $event)"></label>
              <label class="text-sm">{{ labelFor('name', 'Название') }} <span class="text-red-700">*</span><input v-model="row.name" class="storefront-control mt-1 w-full rounded-md border px-3 py-2 text-sm" :placeholder="placeholderFor('name', 'Название')"></label>
              <button v-if="counterparties.length > itemLimits.min" type="button" class="self-end pb-2 text-sm text-red-700" @click="counterparties.splice(index, 1)">Удалить</button>
              <label class="col-span-3 text-sm">Комментарий (необязательно)<textarea v-model="row.comment" rows="2" class="storefront-control mt-1 w-full rounded-md border px-3 py-2 text-sm" /></label>
            </div>
            <button v-if="counterparties.length < itemLimits.max" type="button" class="text-sm text-blue-700" @click="counterparties.push(emptyCounterparty())">Добавить ещё контрагента</button>
          </div>
          <label v-else-if="kind === 'snils'" class="block text-sm font-medium">{{ labelFor('number', 'СНИЛС') }} <span class="text-red-700">*</span><input :value="snils" inputmode="numeric" maxlength="11" class="storefront-control mt-1 block w-full rounded-md border px-3 py-2 text-sm" :placeholder="placeholderFor('number', '12345678901')" aria-describedby="snils-format" @beforeinput="insertDigits($event, snils, 11, value => snils = value)" @paste="pasteDigits($event, snils, 11, value => snils = value)" @input="updateSnils"></label>
          <p v-if="kind === 'snils'" id="snils-format" class="text-xs text-gray-600">11 цифр</p>
          <div v-else-if="kind === 'open_bank_accounts'" class="space-y-3">
            <h4 class="font-medium">{{ labelFor('accounts', 'Открытые расчётные счета') }}</h4>
            <div v-for="(row, index) in accounts" :key="index" class="space-y-2 rounded-md border border-gray-200 p-3">
              <label class="block text-sm">{{ bankFormVersion === 2 ? 'Наименование банка' : 'Название банка' }} <span class="text-red-700">*</span><input v-model="row.bank.name" class="storefront-control mt-1 block w-full rounded-md border px-3 py-2 text-sm" :placeholder="placeholderFor('bank_name', 'Название банка')"></label>
              <label class="block text-sm">БИК <span class="text-red-700">*</span><input :value="row.bank.bik" inputmode="numeric" maxlength="9" class="storefront-control mt-1 block w-full rounded-md border px-3 py-2 text-sm" :placeholder="placeholderFor('bik', 'БИК')" @beforeinput="insertDigits($event, row.bank.bik, 9, value => accounts[index].bank.bik = value)" @paste="pasteDigits($event, row.bank.bik, 9, value => accounts[index].bank.bik = value)" @input="updateBik(index, $event)"></label>
              <label class="block text-sm">Расчётный счёт <span class="text-red-700">*</span><input :value="row.acc_number" inputmode="numeric" maxlength="20" class="storefront-control mt-1 block w-full rounded-md border px-3 py-2 text-sm" :placeholder="placeholderFor('acc_number', 'Номер счёта')" @beforeinput="insertDigits($event, row.acc_number, 20, value => accounts[index].acc_number = value)" @paste="pasteDigits($event, row.acc_number, 20, value => accounts[index].acc_number = value)" @input="updateAccountNumber(index, $event)"></label>
              <label v-if="bankFormVersion === 2" class="block text-sm">Корр. счёт <span class="text-red-700">*</span><input :value="row.correspondent_account" inputmode="numeric" maxlength="20" class="storefront-control mt-1 block w-full rounded-md border px-3 py-2 text-sm" placeholder="Корреспондентский счёт" @beforeinput="insertDigits($event, row.correspondent_account, 20, value => accounts[index].correspondent_account = value)" @paste="pasteDigits($event, row.correspondent_account, 20, value => accounts[index].correspondent_account = value)" @input="updateCorrespondentAccount(index, $event)"></label>
              <button v-if="accounts.length > itemLimits.min" type="button" class="text-sm text-red-700" @click="accounts.splice(index, 1)">Удалить счёт</button>
            </div>
            <button v-if="accounts.length < itemLimits.max" type="button" class="text-sm text-blue-700" @click="accounts.push(emptyAccount())">Добавить ещё счёт</button>
          </div>
          <label v-else-if="kind === 'beneficial_owner'" class="block text-sm font-medium">{{ labelFor('fio', 'ФИО') }}<input v-model="beneficialOwner" class="storefront-control mt-1 block w-full rounded-md border px-3 py-2 text-sm" :placeholder="placeholderFor('fio', 'Иванов Иван Иванович')"></label>
        </template>
        <div class="space-y-2">
          <div class="flex items-center justify-between gap-3"><span class="text-sm font-medium">Файлы <span v-if="!filesOptional" class="text-red-700">*</span><span v-else class="font-normal text-gray-500"> (необязательно)</span></span><button type="button" class="text-sm text-blue-700" :disabled="files.length >= maxFiles" @click="openFilePicker">Добавить ещё файл</button></div>
          <input ref="fileInput" type="file" multiple class="sr-only" @change="selectFiles">
          <p v-if="!files.length" class="text-sm text-gray-600">{{ filesOptional ? noFileMessage : 'Выберите от 1 до 10 файлов.' }}</p>
          <ul v-else class="divide-y rounded-md border">
            <li v-for="(file, index) in files" :key="fileKey(file, index)" class="flex items-center justify-between gap-3 px-3 py-2 text-sm"><div class="min-w-0 flex-1"><p class="truncate">{{ file.name }}</p><label class="mt-2 block text-xs">Название документа в анкете<input v-model="userTitles[index]" class="storefront-control mt-1 w-full rounded border px-2 py-1" maxlength="255" required></label></div><span class="shrink-0 text-gray-600">{{ formatFileSize(file.size) }}</span><button type="button" class="shrink-0 text-red-700" @click="removeFile(index)">Удалить</button></li>
          </ul>
        </div>
        <p v-if="formError || fileError" role="alert" class="text-sm text-red-700">{{ formError || fileError }}</p>
        <p v-if="submitError" role="alert" class="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{{ submitError }}</p>
      </fieldset>
      <div class="flex justify-end gap-2 border-t pt-4"><button type="button" class="btn-secondary" :disabled="sending" @click="emit('close')">Отмена</button><button type="submit" class="btn-primary" :disabled="sending">{{ sending ? 'Отправляем…' : 'Отправить' }}</button></div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import Modal from '~/components/ui/Modal.vue'
import type { DocumentRequestHistoryItem } from '~/features/documents/api/documentsApi'

const maxFiles = 10
const props = defineProps<{ show: boolean; item: DocumentRequestHistoryItem; comments: string | null; sending?: boolean; submitError?: string }>()
const emit = defineEmits<{ close: []; submit: [files: File[], formData?: Record<string, unknown>, userTitles?: string[]] }>()
const counterparties = ref([{ inn: '', name: '', comment: '' }])
const snils = ref('')
const emptyAccount = () => ({ bank: { name: '', bik: '' }, acc_number: '', correspondent_account: '' })
const accounts = ref([emptyAccount()])
const beneficialOwner = ref('')
const files = ref<File[]>([])
const userTitles = ref<string[]>([])
const filesOptional = computed(() => props.item.has_form || new Set(['snils', 'main_counterparties', 'open_bank_accounts', 'beneficial_owner', 'loans_docs', 'third_member_guarantees', 'additional_collateral', 'state_defense_order', 'appointment_docs', 'management_company']).has(props.item.document_type))
const noFileMessage = computed(() => props.item.document_type === 'loans_docs' ? 'Без файла в анкете будет указано: Данные о кредитах, займах и лизинге отсутствуют.' : 'Можно отправить сведения без файла или приложить до 10 файлов.')
const fileInput = ref<HTMLInputElement | null>(null)
const fileError = ref('')
const formError = ref('')
const kind = computed(() => props.item.form_schema?.kind ?? null)
const schema = computed(() => props.item.form_schema)
const bankFormVersion = computed(() => schema.value?.schema_version)
const itemLimits = computed(() => {
  const rawMin = schema.value?.min_items
  const rawMax = schema.value?.max_items
  const min = typeof rawMin === 'number' && Number.isInteger(rawMin) ? Math.min(Math.max(rawMin, 1), 10) : 1
  const max = typeof rawMax === 'number' && Number.isInteger(rawMax) ? Math.min(Math.max(rawMax, min), 10) : 10
  return { min, max }
})
const fieldDefinition = (key: string) => schema.value?.fields?.[key]
const labelFor = (key: string, fallback: string) => fieldDefinition(key)?.label ?? schema.value?.labels?.[key] ?? fallback
const placeholderFor = (key: string, fallback: string) => fieldDefinition(key)?.placeholder ?? fallback
const emptyCounterparty = () => ({ inn: '', name: '', comment: '' })
const initialRows = <T>(factory: () => T) => Array.from({ length: itemLimits.value.min }, factory)
const digits = (value: string, maxLength?: number) => value.replace(/[^0-9]/g, '').slice(0, maxLength)
const replaceSelectedDigits = (input: HTMLInputElement, value: string, inserted: string, maxLength: number) => {
  const start = input.selectionStart ?? value.length
  const end = input.selectionEnd ?? start
  const before = value.slice(0, start)
  const after = value.slice(end)
  const available = maxLength - before.length - after.length
  const accepted = digits(inserted, Math.max(available, 0))
  return { value: before + accepted + after, caret: before.length + accepted.length }
}
const setDigitValue = (input: HTMLInputElement, value: string, inserted: string, maxLength: number, update: (value: string) => void) => {
  const next = replaceSelectedDigits(input, value, inserted, maxLength)
  input.value = next.value
  input.setSelectionRange(next.caret, next.caret)
  update(next.value)
}
const insertDigits = (event: InputEvent, value: string, maxLength: number, update: (value: string) => void) => {
  if (!event.inputType.startsWith('insert') || event.data === null) return
  if (!digits(event.data)) { event.preventDefault(); return }
  event.preventDefault()
  setDigitValue(event.target as HTMLInputElement, value, event.data, maxLength, update)
}
const pasteDigits = (event: ClipboardEvent, value: string, maxLength: number, update: (value: string) => void) => {
  event.preventDefault()
  setDigitValue(event.target as HTMLInputElement, value, event.clipboardData?.getData('text') ?? '', maxLength, update)
}
const normalizeInput = (event: Event, maxLength: number, update: (value: string) => void) => {
  const input = event.target as HTMLInputElement
  const value = digits(input.value, maxLength)
  input.value = value
  update(value)
}
const updateSnils = (event: Event) => normalizeInput(event, 11, value => snils.value = value)
const updateCounterpartyInn = (index: number, event: Event) => normalizeInput(event, 12, value => counterparties.value[index].inn = value)
const updateBik = (index: number, event: Event) => normalizeInput(event, 9, value => accounts.value[index].bank.bik = value)
const updateAccountNumber = (index: number, event: Event) => normalizeInput(event, 20, value => accounts.value[index].acc_number = value)
const updateCorrespondentAccount = (index: number, event: Event) => normalizeInput(event, 20, value => accounts.value[index].correspondent_account = value)
const openFilePicker = () => fileInput.value?.click()
const selectFiles = (event: Event) => {
  const selected = Array.from((event.target as HTMLInputElement).files ?? [])
  const remaining = maxFiles - files.value.length
  if (selected.length > remaining) fileError.value = `Можно добавить не более ${maxFiles} файлов в один ответ.`
  else fileError.value = ''
  if (remaining > 0) { const accepted = selected.slice(0, remaining); files.value.push(...accepted); userTitles.value.push(...accepted.map(file => file.name)) }
  ;(event.target as HTMLInputElement).value = ''
}
const removeFile = (index: number) => { files.value.splice(index, 1); userTitles.value.splice(index, 1); fileError.value = '' }
const fileKey = (file: File, index: number) => `${file.name}-${file.size}-${file.lastModified}-${index}`
const formatFileSize = (bytes: number) => bytes < 1024 ? `${bytes} Б` : bytes < 1024 ** 2 ? `${(bytes / 1024).toFixed(1)} КБ` : `${(bytes / 1024 ** 2).toFixed(1)} МБ`
const formData = (): Record<string, unknown> | undefined => {
  formError.value = ''
  if (!props.item.has_form) return undefined
  if (kind.value === 'main_counterparties') { if (counterparties.value.some(row => !row.name.trim() || !/^(\d{10}|\d{12})$/.test(row.inn))) { formError.value = 'Укажите название и ИНН из 10 или 12 цифр для каждого контрагента'; return } return { counterparties: counterparties.value.map(row => ({ name: row.name.trim(), inn: row.inn, ...(row.comment.trim() ? { comment: row.comment.trim() } : {}) })) } }
  if (kind.value === 'snils') { if (!/^\d{11}$/.test(snils.value)) { formError.value = 'СНИЛС должен содержать 11 цифр'; return } return { number: snils.value } }
  if (kind.value === 'open_bank_accounts') {
    if (bankFormVersion.value !== 1 && bankFormVersion.value !== 2) { formError.value = 'Неподдерживаемая версия формы расчётных счетов'; return }
    if (accounts.value.some(row => !row.bank.name.trim() || !/^\d{9}$/.test(row.bank.bik) || !/^\d{20}$/.test(row.acc_number))) { formError.value = 'Укажите наименование банка, БИК из 9 цифр и расчётный счёт из 20 цифр'; return }
    if (bankFormVersion.value === 1) return { accounts: accounts.value.map(row => ({ bank: { name: row.bank.name.trim(), bik: row.bank.bik }, acc_number: row.acc_number })) }
    if (accounts.value.some(row => !/^\d{20}$/.test(row.correspondent_account))) { formError.value = 'Корреспондентский счёт должен содержать 20 цифр'; return }
    return { accounts: accounts.value.map(row => ({ bank: row.bank.name.trim(), bik: row.bank.bik, acc_number: row.acc_number, correspondent_account: row.correspondent_account })) }
  }
  if (kind.value === 'beneficial_owner') { if (!beneficialOwner.value.trim()) { formError.value = 'Введите ФИО выгодоприобретателя'; return } return { fio: beneficialOwner.value.trim() } }
  formError.value = 'Неизвестная форма документа'
}
const submit = () => { const data = formData(); if (formError.value) return; if (!files.value.length && !filesOptional.value) { fileError.value = 'Выберите хотя бы один файл'; return }; if (userTitles.value.some(title => !title.trim())) { fileError.value = 'Укажите название каждого документа'; return }; emit('submit', files.value, data, userTitles.value.map(title => title.trim())) }
watch(() => [props.show, props.item.id] as const, () => { counterparties.value = initialRows(emptyCounterparty); snils.value = ''; accounts.value = initialRows(emptyAccount); beneficialOwner.value = ''; files.value = []; userTitles.value = []; fileError.value = ''; formError.value = '' }, { immediate: true })
</script>
