<template>
  <Modal
    :show="true"
    :title="title"
    :subtitle="subtitle"
    size="lg"
    :show-footer="false"
    :closable="!submitting"
    :close-on-overlay="!submitting"
    @close="close"
  >
    <form data-testid="fast-deal-create-form" novalidate class="space-y-5" @submit.prevent="submit">
      <div
        v-if="formError"
        role="alert"
        data-testid="fast-deal-create-error"
        class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
      >
        {{ formError }}
      </div>

      <div role="group" :aria-labelledby="companyLabelId" data-testid="fast-deal-create-company">
        <span :id="companyLabelId" class="mb-1 block text-sm font-medium text-gray-700">
          Компания клиента <span class="text-red-500" aria-hidden="true">*</span>
        </span>
        <CompanyAutocomplete
          v-model="companySearch"
          placeholder="Введите ИНН или название компании клиента"
          @select="onCompanySelect"
        />
        <p v-if="errors.company" role="alert" class="mt-1 text-xs text-red-600">{{ errors.company }}</p>
        <p v-else class="mt-1 text-xs text-gray-500">
          Клиент не получает доступ к платформе, SMS и уведомления. После создания сделки клиента изменить нельзя.
        </p>
      </div>

      <div>
        <label :for="phoneId" class="mb-1 block text-sm font-medium text-gray-700">
          Телефон клиента <span class="text-red-500" aria-hidden="true">*</span>
        </label>
        <input
          :id="phoneId"
          :value="phone"
          type="tel"
          inputmode="tel"
          autocomplete="off"
          placeholder="+7XXXXXXXXXX"
          required
          :aria-invalid="Boolean(errors.client_phone)"
          :aria-describedby="phoneHintId"
          class="storefront-control input-field"
          data-testid="fast-deal-create-phone"
          @focus="onPhoneFocus"
          @blur="onPhoneBlur"
          @input="onPhoneInput"
        >
        <p
          :id="phoneHintId"
          class="mt-1 text-xs"
          :class="errors.client_phone ? 'text-red-600' : 'text-gray-500'"
          :role="errors.client_phone ? 'alert' : undefined"
        >
          {{ errors.client_phone || 'Формат: +7XXXXXXXXXX' }}
        </p>
      </div>

      <div class="flex justify-end gap-3 pt-2">
        <button type="button" class="btn-secondary" :disabled="submitting" @click="close">
          Отмена
        </button>
        <button
          type="submit"
          class="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="submitting"
          data-testid="fast-deal-create-submit"
        >
          {{ submitting ? 'Создаём…' : 'Создать сделку' }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import CompanyAutocomplete from '~/components/ui/CompanyAutocomplete.vue'
import Modal from '~/components/ui/Modal.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { createFastDealsApi, parseFastDealError } from '~/features/fast-deals/api/fastDealsApi'
import { isValidClientPhone, maskClientPhone } from '~/features/fast-deals/phone'
import type { FastDealCard, SelectedCompany } from '~/features/fast-deals/types'

/**
 * Creates a draft deal. The client is the company selected in `CompanyAutocomplete` (the object of
 * `@select` goes to the backend unchanged — the backend creates the company, never a user or SMS)
 * plus a mandatory phone `+7XXXXXXXXXX`. The direction follows the caller's role.
 */
const props = defineProps<{
  /** Company of a notification link the list was opened with; the deal is created for that company. */
  companyContext?: string
}>()
const emit = defineEmits<{
  close: []
  created: [deal: FastDealCard]
}>()

const authStore = useAuthStore()
const api = createFastDealsApi(useRuntimeConfig(), () => props.companyContext)

const uid = useId()
const companyLabelId = `${uid}-company`
const phoneId = `${uid}-phone`
const phoneHintId = `${uid}-phone-hint`

const companySearch = ref('')
const selectedCompany = ref<SelectedCompany | null>(null)
const phone = ref('')
const submitting = ref(false)
const formError = ref('')
const errors = reactive({ company: '', client_phone: '' })

const fromLeasing = computed(() => authStore.isLeasingCompany)
const title = computed(() => {
  if (authStore.isDealer) return 'Регистрация сделки: от дилера к ЛК'
  if (fromLeasing.value) return 'Регистрация сделки: от ЛК к дилеру'
  return 'Регистрация сделки'
})
const subtitle = computed(() => fromLeasing.value
  ? 'Сделка согласована вне платформы. Вы подготовите технику и условия и отправите её дилерам.'
  : 'Сделка согласована вне платформы. Вы подготовите технику и условия и отправите их лизинговым компаниям.')

// `null` arrives when the user edits the text after picking a suggestion: the choice is void then.
const onCompanySelect = (company: SelectedCompany | null) => {
  selectedCompany.value = company
  errors.company = ''
}

// The prefix is shown as soon as the field is focused and removed again if nothing was typed.
const onPhoneFocus = () => {
  if (!phone.value) phone.value = '+7'
}
const onPhoneBlur = () => {
  if (phone.value === '+7') phone.value = ''
}
const onPhoneInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  phone.value = maskClientPhone(input.value)
  input.value = phone.value
  errors.client_phone = ''
}

const validate = (): boolean => {
  errors.company = ''
  errors.client_phone = ''
  const company = selectedCompany.value
  if (!company) {
    errors.company = 'Выберите компанию клиента из списка'
  } else if (!/^\d{10,12}$/.test(String(company.inn ?? '').trim())) {
    errors.company = 'У выбранной компании не указан ИНН. Выберите другую компанию.'
  }
  if (!isValidClientPhone(phone.value)) {
    errors.client_phone = 'Введите телефон клиента в формате +7XXXXXXXXXX'
  }
  return !errors.company && !errors.client_phone
}

const close = () => {
  if (!submitting.value) emit('close')
}

const submit = async () => {
  formError.value = ''
  if (submitting.value || !validate()) return
  const company = selectedCompany.value
  if (!company) return
  submitting.value = true
  try {
    const response = await api.create({ company, client_phone: phone.value })
    emit('created', response.deal)
  } catch (cause) {
    const failure = parseFastDealError(cause)
    const field = failure.field ?? ''
    if (/phone/i.test(field)) errors.client_phone = failure.detail
    else if (/company|inn/i.test(field)) errors.company = failure.detail
    else formError.value = failure.detail
  } finally {
    submitting.value = false
  }
}
</script>
