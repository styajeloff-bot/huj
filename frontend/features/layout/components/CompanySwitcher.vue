<template>
  <div
    v-if="activeCompanies.length > 1"
    ref="dropdownRef"
    class="relative"
    @keydown.escape="isOpen = false"
  >
    <button
      type="button"
      @click="toggleDropdown"
      :disabled="isLoading"
      class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 shadow-sm transition-colors max-w-xs cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
      :class="{ 'ring-2 ring-blue-500 border-blue-500': isOpen }"
      :title="buttonLabel"
      aria-haspopup="listbox"
      :aria-expanded="isOpen"
    >
      <svg
        class="w-4 h-4 text-gray-500 shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-4m-5 0H3m2 0h3M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
        />
      </svg>
      <span class="truncate">{{ buttonLabel }}</span>
      <svg
        v-if="isLoading"
        class="w-4 h-4 text-blue-600 animate-spin shrink-0 ml-auto"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
        <path
          class="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      <svg
        v-else
        class="w-4 h-4 text-gray-400 shrink-0 transition-transform duration-200 ml-auto"
        :class="{ 'rotate-180': isOpen }"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
      </svg>
    </button>

    <transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="transform opacity-0 scale-95"
      enter-to-class="transform opacity-100 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="transform opacity-100 scale-100"
      leave-to-class="transform opacity-0 scale-95"
    >
      <div
        v-if="isOpen"
        class="absolute right-0 mt-2 w-72 md:w-80 bg-white rounded-xl shadow-xl border border-gray-200 py-1.5 z-50 max-h-80 overflow-y-auto"
        role="listbox"
        aria-label="Выбор компании"
      >
        <div class="px-3.5 py-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-100">
          Активная компания
        </div>
        <div class="py-1">
          <button
            v-for="company in activeCompanies"
            :key="company.id"
            type="button"
            role="option"
            :aria-selected="isActiveCompany(company.id)"
            :disabled="isLoading"
            @click="handleSelectCompany(company)"
            class="w-full text-left px-3.5 py-2.5 text-sm flex items-center justify-between hover:bg-gray-50 transition-colors cursor-pointer group disabled:opacity-50 disabled:cursor-not-allowed"
            :class="isActiveCompany(company.id) ? 'bg-blue-50/70 text-blue-700 font-medium' : 'text-gray-700'"
          >
            <span class="truncate pr-2">
              {{ company.name }} — {{ localizeRole(company.role) }}
            </span>
            <svg
              v-if="isActiveCompany(company.id)"
              class="w-4 h-4 text-blue-600 shrink-0"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore, type AvailableCompany } from '~/features/auth/store/auth'
import { useCheckoutStore } from '~/features/checkout/store/checkout'

const authStore = useAuthStore()
const checkoutStore = useCheckoutStore()
const config = useRuntimeConfig()
const toast = useToast()

const isOpen = ref(false)
const isLoading = ref(false)
const dropdownRef = ref<HTMLDivElement | null>(null)

const availableCompanies = computed<AvailableCompany[]>(() =>
  (authStore.user?.available_companies || authStore.user?.availableCompanies || []) as AvailableCompany[],
)

const activeCompanies = computed<AvailableCompany[]>(() =>
  availableCompanies.value.filter((c) => c.is_active !== false && c.isActive !== false),
)

const activeCompanyId = computed<string | null>(() =>
  authStore.user?.active_company_id || authStore.user?.activeCompanyId || authStore.user?.company_id || null,
)

const activeCompany = computed<AvailableCompany | null>(() => {
  if (activeCompanyId.value) {
    const found = activeCompanies.value.find((c) => String(c.id) === String(activeCompanyId.value))
    if (found) return found
  }
  return null
})

const activeCompanyName = computed<string>(() => {
  return (
    activeCompany.value?.name ||
    authStore.user?.active_company_name ||
    authStore.user?.activeCompanyName ||
    authStore.user?.company_name ||
    ''
  )
})

const activeRoleName = computed<string>(() => {
  return (
    activeCompany.value?.role ||
    authStore.user?.active_role ||
    authStore.user?.activeRole ||
    authStore.user?.role ||
    ''
  )
})

const localizeRole = (role?: string | null): string => {
  if (!role) return ''
  switch (role) {
    case 'client':
      return 'Клиент'
    case 'dealer':
      return 'Дилер'
    case 'distributor':
      return 'Дистрибьютор'
    case 'leasing_company':
      return 'Лизинговая компания'
    default:
      return role
  }
}

const localizedActiveRole = computed<string>(() => localizeRole(activeRoleName.value))

const buttonLabel = computed<string>(() => {
  if (activeCompanyName.value && localizedActiveRole.value) {
    return `${activeCompanyName.value} — ${localizedActiveRole.value}`
  }
  return activeCompanyName.value || localizedActiveRole.value || 'Выбор компании'
})

const isActiveCompany = (companyId: string): boolean => {
  const currentId = activeCompanyId.value
  return Boolean(currentId && String(companyId) === String(currentId))
}

const toggleDropdown = () => {
  if (!isLoading.value) {
    isOpen.value = !isOpen.value
  }
}

const handleSelectCompany = async (company: AvailableCompany) => {
  if (isActiveCompany(company.id)) {
    isOpen.value = false
    return
  }

  isLoading.value = true
  try {
    await $fetch('/api/v1/users/me/company-select-history', {
      method: 'PUT',
      baseURL: config.public.apiBase,
      credentials: 'include',
      body: { company_id: company.id },
    })
    checkoutStore.setSelectedCompanyId(company.id)
    await authStore.checkAuth(true)
    isOpen.value = false
  } catch (err: any) {
    const message = err?.data?.error || err?.data?.detail || 'Не удалось переключить компанию'
    toast.error(message)
  } finally {
    isLoading.value = false
  }
}

const handleClickOutside = (event: MouseEvent) => {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    isOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>
