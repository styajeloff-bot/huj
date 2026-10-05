<template>
  <Modal 
    :show="true" 
    @close="$emit('close')"
    title="Создать компанию"
    size="2xl"
    :show-footer="false"
  >
    <div data-storefront-block="client.cabinet" v-if="error" class="mb-4 p-3 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)] rounded">
      {{ error }}
    </div>

    <form data-storefront-block="client.cabinet" @submit.prevent="submitForm">
      <div class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label for="name" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
              Название компании <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
            </label>
            <input
              id="name"
              v-model="form.name"
              type="text"
              required
              class="storefront-control input-field"
              placeholder="ООО Рога и Копыта"
            >
          </div>

          <div>
            <label for="company_type" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
              Тип компании <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
            </label>
            <select
              id="company_type"
              v-model="form.company_type"
              required
              class="storefront-control select-field"
            >
              <option value="">Выберите тип</option>
              <option value="dealer">Дилер</option>
              <option value="leasing_company">Лизинговая компания</option>
              <option value="distributor">Дистрибьютор</option>
              <option value="other">Другое</option>
            </select>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label for="inn" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
              ИНН <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
            </label>
            <input
              id="inn"
              v-model="form.inn"
              type="text"
              required
              pattern="[0-9]{10}|[0-9]{12}"
              class="storefront-control input-field"
              placeholder="1234567890"
              maxlength="12"
            >
          </div>

          <div>
            <label for="kpp" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
              КПП
            </label>
            <input
              id="kpp"
              v-model="form.kpp"
              type="text"
              pattern="[0-9]{9}"
              class="storefront-control input-field"
              placeholder="123456789"
              maxlength="9"
            >
          </div>

          <div>
            <label for="ogrn" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
              ОГРН
            </label>
            <input
              id="ogrn"
              v-model="form.ogrn"
              type="text"
              pattern="[0-9]{13}|[0-9]{15}"
              class="storefront-control input-field"
              placeholder="1234567890123"
              maxlength="15"
            >
          </div>
        </div>

        <div>
          <label for="legal_address" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Юридический адрес
          </label>
          <textarea
            id="legal_address"
            v-model="form.legal_address"
            rows="2"
            class="storefront-control input-field"
            placeholder="г. Москва, ул. Примерная, д. 1"
          ></textarea>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label for="phone" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
              Телефон
            </label>
            <input
              id="phone"
              v-model="form.phone"
              type="tel"
              class="storefront-control input-field"
              placeholder="+7 (495) 123-45-67"
            >
          </div>

          <div>
            <label for="email" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
              Email
            </label>
            <input
              id="email"
              v-model="form.email"
              type="email"
              class="storefront-control input-field"
              placeholder="info@company.ru"
            >
          </div>
        </div>
      </div>

      <div class="mt-6 flex justify-end space-x-3">
        <button
          type="button"
          @click="$emit('close')"
          class="btn-secondary"
        >
          Отмена
        </button>
        <button
          type="submit"
          :disabled="loading"
          class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? 'Создание...' : 'Создать компанию' }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import type { CompanyCreateForm } from '../types'

const emit = defineEmits(['close', 'success'])
const config = useRuntimeConfig()

const form = ref<CompanyCreateForm>({
  name: '',
  inn: '',
  kpp: '',
  ogrn: '',
  company_type: '',
  legal_address: '',
  phone: '',
  email: ''
})

const loading = ref(false)
const error = ref('')

const submitForm = async () => {
  loading.value = true
  error.value = ''

  try {
    const body: Partial<CompanyCreateForm> = { ...form.value }

    ;(Object.keys(body) as Array<keyof CompanyCreateForm>).forEach(key => {
      if (!body[key]) delete body[key]
    })

    await $fetch('/api/v1/admin/companies', {
      method: 'POST',
      body,
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    emit('success')
  } catch (err: unknown) {
    const fetchErr = err as { data?: { error?: string } }
    error.value = fetchErr.data?.error || 'Ошибка при создании компании'
  } finally {
    loading.value = false
  }
}
</script>
