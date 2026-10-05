<template>
  <Modal
    :show="true"
    title="Пригласить сотрудника"
    size="lg"
    :show-footer="false"
    @close="$emit('close')"
  >
    <div data-storefront-block="client.cabinet" v-if="success" class="p-3 bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-success-border,#bbf7d0)] rounded-lg text-sm text-[color:var(--storefront-success-text,#15803d)] mb-4">
      {{ success }}
    </div>

    <div data-storefront-block="client.cabinet" v-if="error" class="p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg text-sm text-[color:var(--storefront-error-text,#b91c1c)] mb-4">
      {{ error }}
    </div>

    <form data-storefront-block="client.cabinet" @submit.prevent="submitInvite">
      <div class="space-y-4">
        <!-- Company selector -->
        <div v-if="companies.length > 1">
          <label for="invite-company" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Компания
          </label>
          <select
            id="invite-company"
            v-model="selectedCompanyId"
            required
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
          >
            <option v-for="c in companies" :key="c.id" :value="c.id">
              {{ c.name }}
            </option>
          </select>
        </div>

        <div>
          <label for="invite-phone" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Телефон сотрудника
          </label>
          <input
            id="invite-phone"
            v-model="phone"
            type="tel"
            required
            placeholder="+7XXXXXXXXXX"
            class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
          >
          <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            Формат: +7XXXXXXXXXX
          </p>
        </div>
      </div>

      <div class="mt-6 flex justify-end gap-3">
        <button
          type="button"
          class="btn-secondary"
          :disabled="loading"
          @click="$emit('close')"
        >
          Отмена
        </button>
        <button
          type="submit"
          :disabled="loading || !isValidPhone"
          class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? 'Отправка...' : 'Отправить приглашение' }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import { createAuthApi } from '~/features/auth/api/authApi'
import type { UserCompany } from '~/features/company/api/companyApi'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  companies: UserCompany[]
  preselectedCompanyId?: UUID
}>()

const emit = defineEmits(['close', 'invited'])

const config = useRuntimeConfig()
const authApi = createAuthApi(config)

const phone = ref('')
const selectedCompanyId = ref<UUID>(props.preselectedCompanyId ? props.preselectedCompanyId : '')
const loading = ref(false)
const error = ref('')
const success = ref('')

const normalizePhone = (value: string): string => {
  const digits = value.replace(/\D+/g, '')
  if (digits.startsWith('8') && digits.length === 11) return `+7${digits.slice(1)}`
  if (digits.startsWith('7') && digits.length === 11) return `+${digits}`
  if (digits.length === 10) return `+7${digits}`
  return `+7${digits}`
}

const normalizedPhone = computed(() => normalizePhone(phone.value))
const isValidPhone = computed(() => /^\+7\d{10}$/.test(normalizedPhone.value))

const submitInvite = async () => {
  if (!isValidPhone.value) return
  if (!selectedCompanyId.value) {
    error.value = 'Выберите компанию для приглашения'
    return
  }

  loading.value = true
  error.value = ''
  success.value = ''

  try {
    const response = await authApi.inviteEmployee(selectedCompanyId.value, normalizedPhone.value)
    success.value = response.message || 'Приглашение отправлено'
    phone.value = ''
    setTimeout(() => {
      emit('invited')
    }, 1200)
  } catch (err: any) {
    error.value = err.data?.error || 'Ошибка при отправке приглашения'
  } finally {
    loading.value = false
  }
}
</script>
