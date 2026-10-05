<template>
  <div data-storefront-block="shared.form" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-6 rounded-lg shadow-sm border">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Мои компании</h3>
      <button
        type="button"
        class="btn-primary"
        @click="openAddCompanyModal"
      >
        Добавить компанию
      </button>
    </div>

    <!-- Загрузка -->
    <div v-if="loading" class="text-center py-6">
      <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем компании...</p>
    </div>

    <!-- Список компаний -->
    <div v-else-if="companies.length" class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
      <div
        v-for="company in companies"
        :key="String(company.id)"
        class="py-3 flex items-start justify-between gap-3"
      >
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="font-medium text-[color:var(--storefront-text,#111827)] truncate">{{ company.name || 'Без названия' }}</span>
            <span
              v-if="company.sub_role"
              class="px-2 py-0.5 text-xs font-medium bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)] rounded-full whitespace-nowrap"
            >
              {{ subRoleLabel(company.sub_role) }}
            </span>
          </div>
          <div v-if="company.inn" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] mt-0.5">ИНН: {{ company.inn }}</div>
        </div>
      </div>
    </div>

    <!-- Пусто -->
    <div v-else class="text-center py-6 text-[color:var(--storefront-text-muted,#6b7280)] text-sm">
      Компании не привязаны. Добавьте первую компанию.
    </div>

    <!-- Модальное окно добавления компании (визуально идентично регистрации) -->
    <Modal
      :show="showAddCompanyModal"
      title="Добавить компанию"
      size="lg"
      :show-footer="false"
      @close="closeAddCompanyModal"
    >
      <div class="space-y-4">
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Введите название компании или ИНН.
        </p>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
            Компании
          </label>
          <div
            v-for="(entry, index) in newCompanies"
            :key="index"
            class="flex gap-2 items-start mb-3"
          >
            <div class="flex-1 min-w-0">
              <CompanyAutocomplete
                v-model="newCompanies[index]"
                placeholder="Введите название компании или ИНН"
                :required="index === 0"
                @validation="(valid) => setNewCompanyValid(index, valid)"
                @select="(obj) => setNewCompanyObject(index, obj)"
              />
            </div>
            <button
              v-if="newCompanies.length > 1"
              type="button"
              aria-label="Удалить компанию"
              class="storefront-action-ghost mt-2 p-2 text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#dc2626)] shrink-0"
              @click="removeNewCompany(index)"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
          <button
            type="button"
            class="storefront-action-ghost text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] mt-1"
            @click="addNewCompanyField"
          >
            + Добавить ещё компанию
          </button>
        </div>

        <div v-if="addCompanyError" class="p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
          {{ addCompanyError }}
        </div>
        <div v-if="addCompanySuccess" class="p-3 bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-success-border,#bbf7d0)] rounded-lg text-sm text-[color:var(--storefront-success-text,#15803d)]">
          {{ addCompanySuccess }}
        </div>

        <div class="flex justify-end gap-3 pt-2">
          <button
            type="button"
            class="btn-secondary"
            @click="closeAddCompanyModal"
          >
            Отмена
          </button>
          <button
            type="button"
            :disabled="addCompanyLoading || !hasValidNewCompany"
            class="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
            @click="submitNewCompanies"
          >
            {{ addCompanyLoading ? 'Сохранение...' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import CompanyAutocomplete from '~/components/ui/CompanyAutocomplete.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import type { CompanyInfo, ApiError } from '@/types'

const config = useRuntimeConfig()
const authStore = useAuthStore()

type CompanySubRole = 'administrator' | 'manager' | 'employee'

interface UserCompany {
  id: string
  name: string
  inn?: string | null
  sub_role?: CompanySubRole | null
  can_view_applications?: boolean
  can_create_applications?: boolean
  canViewApplications?: boolean
  canCreateApplications?: boolean
}

interface UserCompaniesResponse {
  companies: UserCompany[]
}

const request = <T>(url: string, options: Record<string, unknown> = {}) =>
  $fetch<T>(url, {
    baseURL: config.public.apiBase,
    credentials: 'include',
    ...options,
  })

const companies = ref<UserCompany[]>([])
const loading = ref(false)

const showAddCompanyModal = ref(false)
const newCompanies = ref<string[]>([''])
const newCompanyValidities = ref<Record<number, boolean>>({})
const newCompanyObjects = ref<Record<number, CompanyInfo>>({})
const addCompanyLoading = ref(false)
const addCompanyError = ref('')
const addCompanySuccess = ref('')

const hasValidNewCompany = computed(() =>
  newCompanies.value.some((v: string, idx: number) => Boolean(v) && newCompanyValidities.value[idx] === true),
)

const subRoleLabel = (role: string) => {
  const map: Record<string, string> = {
    administrator: 'Администратор',
    manager: 'Менеджер',
    employee: 'Сотрудник',
  }
  return map[role] || role
}

const setNewCompanyValid = (index: number, valid: boolean) => {
  newCompanyValidities.value = { ...newCompanyValidities.value, [index]: valid }
}

const setNewCompanyObject = (index: number, obj: CompanyInfo) => {
  newCompanyObjects.value = { ...newCompanyObjects.value, [index]: obj }
}

const addNewCompanyField = () => {
  newCompanies.value.push('')
}

const removeNewCompany = (index: number) => {
  newCompanies.value.splice(index, 1)
  const shiftMap = <T,>(m: Record<number, T>): Record<number, T> => {
    const next: Record<number, T> = {}
    Object.entries(m).forEach(([k, v]) => {
      const ki = parseInt(k, 10)
      if (ki < index) next[ki] = v
      else if (ki > index) next[ki - 1] = v
    })
    return next
  }
  newCompanyValidities.value = shiftMap(newCompanyValidities.value)
  newCompanyObjects.value = shiftMap(newCompanyObjects.value)
}

const openAddCompanyModal = () => {
  newCompanies.value = ['']
  newCompanyValidities.value = {}
  newCompanyObjects.value = {}
  addCompanyError.value = ''
  addCompanySuccess.value = ''
  showAddCompanyModal.value = true
}

const closeAddCompanyModal = () => {
  showAddCompanyModal.value = false
  newCompanies.value = ['']
  newCompanyValidities.value = {}
  newCompanyObjects.value = {}
  addCompanyError.value = ''
  addCompanySuccess.value = ''
}

const fetchCompanies = async () => {
  try {
    loading.value = true
    const response = await request<UserCompaniesResponse>('/api/v1/users/me/companies')
    companies.value = response.companies || []
  } catch (err) {
    console.error('Error fetching user companies:', err)
  } finally {
    loading.value = false
  }
}

const submitNewCompanies = async () => {
  const companiesToAdd = newCompanies.value
    .map((_, idx) => (newCompanyValidities.value[idx] === true ? newCompanyObjects.value[idx] : null))
    .filter((c): c is CompanyInfo => Boolean(c && c.inn))
  if (companiesToAdd.length === 0) return

  addCompanyLoading.value = true
  addCompanyError.value = ''
  addCompanySuccess.value = ''

  let successCount = 0
  let lastError = ''

  for (const company of companiesToAdd) {
    try {
      await request('/api/v1/users/me/companies', {
        method: 'POST',
        body: { company },
      })
      successCount++
    } catch (err) {
      lastError = (err as ApiError).data?.error || 'Ошибка при добавлении компании'
    }
  }

  addCompanyLoading.value = false

  if (successCount > 0) {
    addCompanySuccess.value = successCount === 1
      ? 'Компания успешно добавлена'
      : `Добавлено компаний: ${successCount}`
    await fetchCompanies()
    await authStore.checkAuth(true)
    setTimeout(() => {
      closeAddCompanyModal()
    }, 1500)
  }

  if (lastError && successCount < companiesToAdd.length) {
    addCompanyError.value = lastError
  }
}

onMounted(fetchCompanies)
</script>
