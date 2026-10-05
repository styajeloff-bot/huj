<template>
  <Modal 
    :show="true" 
    @close="$emit('close')"
    :title="user ? 'Редактировать пользователя' : 'Создать пользователя'"
    size="2xl"
    :show-footer="false"
  >
    <div data-storefront-block="client.auth" v-if="error" class="mb-4 p-3 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)] rounded">
      {{ error }}
    </div>

    <form data-storefront-block="client.auth" @submit.prevent="submitForm">
      <div class="space-y-4">
        <div>
          <label for="name" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            ФИО
          </label>
          <input
            id="name"
            v-model="form.name"
            type="text"
            class="storefront-control input-field"
            placeholder="Иванов Иван Иванович"
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
            placeholder="email@example.com"
          >
        </div>

        <div>
          <label for="phone" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Телефон <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
          </label>
          <input
            id="phone"
            v-model="form.phone"
            type="tel"
            required
            class="storefront-control input-field"
            placeholder="+7XXXXXXXXXX"
          >
        </div>

        <div>
          <label for="role" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Роль <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
          </label>
          <select
            id="role"
            v-model="form.role"
            required
            class="storefront-control select-field"
            @change="onRoleChange"
          >
            <option value="">Выберите роль</option>
            <option value="client">Клиент</option>
            <option value="dealer">Дилер</option>
            <option value="leasing_company">Лизинговая компания</option>
            <option value="distributor">Дистрибьютор</option>
            <option value="carcraft_employee">Сотрудник CarCraft</option>
          </select>
        </div>

        <div v-if="form.role === 'client'">
          <label for="client-company" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Основная компания
          </label>
          <CompanyAutocomplete
            id="client-company"
            v-model="clientCompanyName"
            placeholder="Введите название компании или ИНН"
            @select="setClientCompany"
          />
        </div>

        <div v-if="props.user && form.role === 'client'" class="space-y-3">
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">
            Компании
          </label>
          <p v-if="clientCompaniesLoading" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
            Загрузка компаний…
          </p>
          <template v-else>
            <div
              v-for="company in clientCompanies"
              :key="company.id"
              class="flex items-center gap-2"
            >
              <input
                :value="formatClientCompany(company)"
                disabled
                class="storefront-control input-field disabled:cursor-not-allowed disabled:opacity-70 flex-1"
              >
              <span
                v-if="form.company_id === company.id"
                class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-green-100 text-green-800 whitespace-nowrap"
              >
                Основная
              </span>
              <button
                v-else
                type="button"
                class="text-xs text-blue-600 hover:text-blue-800 whitespace-nowrap"
                @click="makePrimaryCompany(company)"
              >
                Сделать основной
              </button>
            </div>
            <p v-if="clientCompanies.length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
              Компании пока не привязаны
            </p>
          </template>

          <button
            v-if="!showAddClientCompany"
            type="button"
            class="btn-secondary"
            @click="showAddClientCompany = true"
          >
            + Добавить ещё компанию
          </button>

          <div v-if="showAddClientCompany" class="space-y-3 rounded border border-[color:var(--storefront-border,#d1d5db)] p-3">
            <CompanyAutocomplete
              id="additional-client-company"
              v-model="newClientCompanyName"
              placeholder="Введите название компании или ИНН"
              @select="setNewClientCompany"
            />
            <p v-if="addClientCompanyError" class="text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
              {{ addClientCompanyError }}
            </p>
            <div class="flex gap-3">
              <button type="button" class="btn-secondary" @click="cancelAddClientCompany">
                Отмена
              </button>
              <button
                type="button"
                class="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="!newClientCompany || addClientCompanyLoading"
                @click="addClientCompany"
              >
                {{ addClientCompanyLoading ? 'Добавление…' : 'Добавить компанию' }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="showCompanyFields">
          <label for="company" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Компания
          </label>
          <select
            id="company"
            v-model="form.company_id"
            class="storefront-control select-field"
          >
            <option value="">Выберите компанию</option>
            <option v-for="company in filteredCompanies" :key="company.id" :value="company.id">
              {{ company.name }} {{ company.inn ? `(${company.inn})` : '' }}
            </option>
          </select>
        </div>

        <div class="flex items-center">
          <input
            id="is_active"
            v-model="form.is_active"
            type="checkbox"
            class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
          >
          <label for="is_active" class="ml-2 text-sm text-[color:var(--storefront-label,#374151)]">
            Активный пользователь
          </label>
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
          {{ loading ? 'Сохранение...' : (user ? 'Сохранить' : 'Создать') }}
        </button>
      </div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import CompanyAutocomplete from '~/components/ui/CompanyAutocomplete.vue'
import type { CompanyInfo } from '~/types'
import type { UserFormCompany } from '~/types/features'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  user?: Record<string, unknown> | null
}>()

const emit = defineEmits(['close', 'success'])
const config = useRuntimeConfig()

const form = ref({
  name: '',
  email: '',
  phone: '',
  role: '',
  company_id: null as UUID | null,
  is_active: true
})

const companies = ref<UserFormCompany[]>([])
type ClientCompany = {
  id: UUID
  name: string
  inn: string | null
}
const clientCompanies = ref<ClientCompany[]>([])
const clientCompaniesLoading = ref(false)
const showAddClientCompany = ref(false)
const newClientCompanyName = ref('')
const newClientCompany = ref<CompanyInfo | null>(null)
const addClientCompanyLoading = ref(false)
const addClientCompanyError = ref('')
const clientCompanyName = ref('')
const clientCompany = ref<CompanyInfo | null>(null)
const loading = ref(false)
const error = ref('')

const showCompanyFields = computed(() => {
  return ['dealer', 'leasing_company', 'distributor'].includes(form.value.role)
})

const filteredCompanies = computed(() => {
  if (!form.value.role) return []
  
  const typeMap: Record<string, string> = {
    dealer: 'dealer',
    leasing_company: 'leasing_company',
    distributor: 'distributor'
  }

  const targetType = typeMap[form.value.role]
  return companies.value.filter(c => c.company_type === targetType)
})

const fetchCompanies = async (companyType?: string) => {
  try {
    const params = new URLSearchParams()
    params.append('limit', '1000')
    if (companyType) {
      params.append('company_type', companyType)
    }
    const response = await $fetch<{ companies: UserFormCompany[] }>(`/api/v1/companies?${params.toString()}`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    companies.value = response.companies
  } catch (err) {
    console.error('Ошибка загрузки компаний:', err)
  }
}

const fetchClientCompanies = async () => {
  if (!props.user || form.value.role !== 'client') return
  clientCompaniesLoading.value = true
  try {
    const response = await $fetch<{ companies: ClientCompany[] }>(`/api/v1/users/${props.user.id}/companies`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    clientCompanies.value = response.companies
  } catch (err) {
    error.value = (err as { data?: { detail?: string } }).data?.detail || 'Не удалось загрузить компании клиента'
  } finally {
    clientCompaniesLoading.value = false
  }
}

const formatClientCompany = (company: ClientCompany): string => {
  return company.inn ? `${company.name} (ИНН: ${company.inn})` : company.name
}

const setNewClientCompany = (company: CompanyInfo | null) => {
  newClientCompany.value = company
}

const cancelAddClientCompany = () => {
  showAddClientCompany.value = false
  newClientCompanyName.value = ''
  newClientCompany.value = null
  addClientCompanyError.value = ''
}

const addClientCompany = async () => {
  if (!props.user || !newClientCompany.value) return
  addClientCompanyLoading.value = true
  addClientCompanyError.value = ''
  try {
    await $fetch(`/api/v1/users/${props.user.id}/companies`, {
      method: 'POST',
      body: { company: newClientCompany.value },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    await fetchClientCompanies()
    cancelAddClientCompany()
  } catch (err) {
    addClientCompanyError.value = (err as { data?: { detail?: string } }).data?.detail || 'Не удалось добавить компанию'
  } finally {
    addClientCompanyLoading.value = false
  }
}

const onRoleChange = () => {
  form.value.company_id = null
  clientCompanyName.value = ''
  clientCompany.value = null
  if (form.value.role !== 'client') {
    clientCompanies.value = []
    cancelAddClientCompany()
  } else if (props.user) {
    fetchClientCompanies()
  }
  const typeMap: Record<string, string> = {
    dealer: 'dealer',
    leasing_company: 'leasing_company',
    distributor: 'distributor'
  }
  const targetType = typeMap[form.value.role]
  if (targetType) {
    fetchCompanies(targetType)
  } else {
    companies.value = []
  }
}

const setClientCompany = (company: CompanyInfo | null) => {
  clientCompany.value = company
}

const makePrimaryCompany = (company: ClientCompany) => {
  form.value.company_id = company.id
  clientCompanyName.value = formatClientCompany(company)
  clientCompany.value = null
}

const normalizePhone = (raw: string): string => {
  let t = (raw || '').replace(/[\s\-()]/g, '')
  if (t.startsWith('8') && t.length === 11) t = '+7' + t.slice(1)
  else if (t.startsWith('7') && t.length === 11) t = '+' + t
  return t
}

const submitForm = async () => {
  loading.value = true
  error.value = ''

  try {
    const url = props.user
      ? `/api/v1/users/${props.user.id}`
      : '/api/v1/users'

    const method = props.user ? 'PATCH' : 'POST'
    
    const { company_id, ...rest } = form.value
    const body: Record<string, unknown> = { ...rest }
    if (form.value.role === 'client') {
      // If a new company was selected via autocomplete, send company object
      if (clientCompany.value) {
        body.company = clientCompany.value
      } else if (company_id) {
        // Otherwise send company_id (e.g. switching primary from linked list)
        body.company_id = company_id
      }
    } else if (company_id) {
      body.company_id = company_id
    }

    // Не отправляем пустые строки для опциональных полей — PATCH должен
    // либо обновить значение, либо оставить его без изменений.
    if (body.name === '') body.name = null
    if (body.email === '') body.email = null
    if (body.phone === '') {
      body.phone = null
    } else {
      body.phone = normalizePhone(String(body.phone))
    }

    await $fetch(url, {
      method,
      body,
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    emit('success')
  } catch (err: unknown) {
    error.value =
      (err as { data?: { detail?: string } }).data?.detail ||
      (err as { data?: { error?: string } }).data?.error ||
      'Ошибка при сохранении пользователя'
  } finally {
    loading.value = false
  }
}

watch(() => props.user, (newUser) => {
  if (newUser) {
    form.value = {
      name: String(newUser.name || ''),
      email: String(newUser.email || ''),
      phone: normalizePhone(String(newUser.phone || '')),
      role: String(newUser.role || ''),
      company_id: typeof newUser.company_id === 'string' ? newUser.company_id : null,
      is_active: (newUser.is_active as boolean) ?? true
    }
    if (form.value.role === 'client') {
      fetchClientCompanies()
      // Prefill autocomplete with current primary company display
      const companyName = String(newUser.company_name || '')
      const companyInn = String(newUser.company_inn || '')
      if (companyName) {
        clientCompanyName.value = companyInn ? `${companyName} (ИНН: ${companyInn})` : companyName
      }
    } else {
      clientCompanies.value = []
      cancelAddClientCompany()
    }
    const typeMap: Record<string, string> = {
      dealer: 'dealer',
      leasing_company: 'leasing_company',
      distributor: 'distributor'
    }
    const targetType = typeMap[form.value.role]
    if (targetType) {
      fetchCompanies(targetType)
    }
  }
}, { immediate: true })
</script>
