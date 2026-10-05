<template>
  <div data-storefront-block="client.cabinet">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)] mb-2">
          Личный кабинет
        </h1>
      </div>

      <div v-if="authHydrationReady">
        <div
          class="border-b border-[color:var(--storefront-border,#e5e7eb)] mb-6 -mx-4 px-4 sm:mx-0 sm:px-0"
        >
          <nav class="flex space-x-4 sm:space-x-8 overflow-x-auto pb-px -mb-px custom-scrollbar">
            <template v-if="authStore.isClient">
              <button class="" @click="activeTab = 'applications'" :class="[
                'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                activeTab === 'applications'
                  ? 'border-[color:var(--storefront-selected-border,#3b82f6)] text-[color:var(--storefront-selected-foreground,#2563eb)]'
                  : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
              ]">
                Мои заявки
              </button>
              <button class="" @click="activeTab = 'my-cars'" :class="[
                'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                activeTab === 'my-cars'
                  ? 'border-[color:var(--storefront-selected-border,#22c55e)] text-[color:var(--storefront-selected-foreground,#16a34a)]'
                  : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
              ]">
                Мои заказы
              </button>
              <button class="" @click="activeTab = 'favorites'" :class="[
                'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                activeTab === 'favorites'
                  ? 'border-[color:var(--storefront-selected-border,#3b82f6)] text-[color:var(--storefront-selected-foreground,#2563eb)]'
                  : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
              ]">
                Избранное
              </button>
              <button class="" @click="activeTab = 'calculator'" :class="[
                'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                activeTab === 'calculator'
                  ? 'border-[color:var(--storefront-selected-border,#3b82f6)] text-[color:var(--storefront-selected-foreground,#2563eb)]'
                  : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
              ]">
                Калькулятор
              </button>
              <button class="" @click="activeTab = 'compensations'" :class="[
                'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                activeTab === 'compensations'
                  ? 'border-[color:var(--storefront-selected-border,#a855f7)] text-[color:var(--storefront-selected-foreground,#9333ea)]'
                  : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
              ]">
                Компенсации
              </button>
              <button class="" @click="activeTab = 'signatures'" :class="[
                'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                activeTab === 'signatures'
                  ? 'border-[color:var(--storefront-selected-border,#3b82f6)] text-[color:var(--storefront-selected-foreground,#2563eb)]'
                  : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
              ]">
                Документы на подпись
              </button>
              <button class="" @click="activeTab = 'profile'" :class="[
                'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                activeTab === 'profile'
                  ? 'border-[color:var(--storefront-selected-border,#3b82f6)] text-[color:var(--storefront-selected-foreground,#2563eb)]'
                  : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
              ]">
                Профиль
              </button>
              <button class=""
                v-if="canViewEmployeesTab"
                @click="activeTab = 'employees'"
                :class="[
                  'py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap flex-shrink-0',
                  activeTab === 'employees'
                    ? 'border-[color:var(--storefront-selected-border,#a855f7)] text-[color:var(--storefront-selected-foreground,#9333ea)]'
                    : 'border-transparent text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:text-[color:var(--storefront-secondary-hover-foreground,#374151)] hover:border-[color:var(--storefront-secondary-hover-border,#d1d5db)]'
                ]"
              >
                Сотрудники
              </button>
            </template>
          </nav>
        </div>

        <div v-if="activeTab === 'applications' && authStore.isClient">
          <div
            v-if="!authStore.canViewApplications"
            class="mb-6 p-4 bg-[color:rgb(var(--storefront-warning-rgb,254_252_232)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fef08a)] rounded-lg text-sm text-[color:var(--storefront-warning-text,#854d0e)]"
          >
            Доступ к заявкам ограничен. Обратитесь к администратору компании<template v-if="authStore.userCompany"> «{{ authStore.userCompany }}»</template> или в поддержку, написав в чат внизу экрана.
          </div>
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">
              Мои заявки
            </h2>
          </div>

          <div v-if="authStore.canViewApplications" class="mb-6">
            <label for="client-application-search" class="mb-1 block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Поиск</label>
            <input id="client-application-search" v-model="applicationSearch" type="search" class="storefront-control input-field max-w-lg" placeholder="Номер заявки" @input="debouncedApplicationSearch" @keydown.enter.prevent="applyApplicationSearch">
          </div>

          <div v-if="loading" class="text-center py-8">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
            <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем заявки...</p>
          </div>

          <div v-else-if="error" class="text-center py-8">
            <p class="text-[color:var(--storefront-error-text,#dc2626)] mb-4">{{ error }}</p>
            <button @click="fetchApplications" class="btn-primary">
              Попробовать снова
            </button>
          </div>

          <div v-else-if="authStore.canViewApplications && applications.length === 0" class="text-center py-12">
            <svg class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
              </path>
            </svg>
            <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-2">Пока нет заявок</h3>
            <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-4">Создайте первую заявку на автомобиль</p>
          </div>

          <div v-else class="space-y-6">
            <div v-if="applications.length > 0" class="space-y-6">
              <ApplicationCard
                v-for="application in applications"
                :key="application.id"
                :application="application"
              />
            </div>
          </div>
        </div>

        <div
          v-if="activeTab === 'compensations' && authStore.isClient"
        >
          <CompensationRegistryPanel />
        </div>

        <div v-if="activeTab === 'signatures'">
          <SignaturesPanel />
        </div>

        <div v-if="activeTab === 'my-cars' && authStore.isClient">
          <ClientMyCarsPanel :user-companies="userCompanies" />
        </div>

        <div v-if="activeTab === 'favorites' && authStore.isClient">
          <ClientFavoritesPanel />
          <SpecialEquipmentFavoritesSection v-if="isSpecialEquipmentCatalogVisible" />
        </div>

        <div v-if="activeTab === 'calculator' && authStore.isClient">
          <ClientCalculatorPanel />
        </div>

        <div v-if="activeTab === 'profile' && authStore.isClient">
          <ClientProfilePanel />
        </div>

        <div
          v-if="activeTab === 'employees' && canViewEmployeesTab"
        >
          <CompanyMembersPanel />
        </div>
      </div>
    </div>

    <ToastNotifications />
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import ApplicationCard from '~/features/applications/components/ApplicationCard.vue'
import {
  createApplicationsApi,
  type Application as CabinetApplication,
  type Pagination,
} from '~/features/applications/api/applicationsApi'
import { createCompanyApi } from '~/features/company/api/companyApi'
import type { UserCompany } from '~/features/company/api/companyApi'
import type { ApiError } from '@/types'
import { useStorefront } from '~/features/storefront'

// --- Per-tab panels: lazy-loaded via dynamic imports so only the tab the
// user actually visits pulls its chunk. Keeps the cabinet shell tiny and
// first-paint fast.
const ClientProfilePanel = defineAsyncComponent(() => import('~/features/client/components/ClientProfilePanel.vue'))
const SignaturesPanel = defineAsyncComponent(() => import('~/features/signatures/components/SignaturesPanel.vue'))
const ClientFavoritesPanel = defineAsyncComponent(() => import('~/features/favorites/components/ClientFavoritesPanel.vue'))
const SpecialEquipmentFavoritesSection = defineAsyncComponent(() => import('~/features/specialEquipment/components/SpecialEquipmentFavoritesSection.vue'))
const ClientMyCarsPanel = defineAsyncComponent(() => import('~/features/client/components/ClientMyCarsPanel.vue'))
const ClientCalculatorPanel = defineAsyncComponent(() => import('~/features/calculator/components/ClientCalculatorPanel.vue'))
const CompensationRegistryPanel = defineAsyncComponent(() => import('~/features/compensations/components/CompensationRegistryPanel.vue'))
const CompanyMembersPanel = defineAsyncComponent(() => import('~/features/company/components/CompanyMembersPanel.vue'))

const visibilityStore = useSectionVisibilityStore()
const isSpecialEquipmentCatalogVisible = computed(() =>
  visibilityStore.isSectionVisible('public', 'special_equipment_catalog'),
)

definePageMeta({
  middleware: ['auth', 'redirect-business'],
  // Keep user's scroll position when they come back to /cabinet from a
  // child route — avoids the jarring "whole page reloaded" feel.
  scrollToTop: false,
})

useHead({
  title: 'Личный кабинет - CarCraft Multileasing',
  meta: [
    { name: 'description', content: 'Личный кабинет. Управление заявками на лизинг автомобилей.' }
  ]
})

const authStore = useAuthStore()
const authHydrationReady = useHydrationReady()
const config = useRuntimeConfig()
const applicationsApi = createApplicationsApi(config)
const api = createCompanyApi(config)

const applications = ref<CabinetApplication[]>([])
const loading = ref(true)
const error = ref('')

const applicationSearch = ref('')
const appPage = ref(1)
const appLimit = ref(20)
const appPagination = ref<Pagination | null>(null)

const userCompanies = ref<UserCompany[]>([])
const canViewEmployeesTab = computed(() =>
  userCompanies.value.length > 0 ||
  authStore.isCarCraftEmployee ||
  Boolean(authStore.user?.company_id) ||
  Boolean(authStore.user?.active_company_id),
)
const canManageAnyCompany = computed(() =>
  userCompanies.value.some((company) =>
    company.sub_role === 'administrator' || company.sub_role === 'manager',
  ) || authStore.isCompanyAdmin || authStore.isCompanyManager,
)

const fetchUserCompanies = async () => {
  try {
    const typedResponse = await api.getMyCompanies()
    userCompanies.value = typedResponse.companies || []
  } catch (err) {
    console.error('Error fetching user companies:', err)
  }
}

const getDefaultTab = () => 'applications'

const route = useRoute()
const activeTab = ref<string>((route.query.tab as string) || 'applications')
watch(() => route.query.tab, (tab) => {
  if (tab) activeTab.value = tab as string
})

const fetchApplications = async () => {
  if (!authStore.canViewApplications) {
    applications.value = []
    appPagination.value = null
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    const applicationsResponse = await applicationsApi.listApplications(appPage.value, appLimit.value, '', { search: applicationSearch.value })
    applications.value = applicationsResponse.applications || []
    appPagination.value = applicationsResponse.pagination || null
  } catch (err) {
    const apiErr = err as ApiError
    if (apiErr.status === 401) {
      await authStore.checkAuth()
    } else {
      error.value = apiErr.data?.error || 'Ошибка при загрузке заявок'
    }
  } finally {
    loading.value = false
  }
}

const applyApplicationSearch = () => {
  appPage.value = 1
  fetchApplications()
}
const { debounce } = useLodash()
const debouncedApplicationSearch = debounce(applyApplicationSearch, 300)
onBeforeUnmount(() => debouncedApplicationSearch.cancel())

onActivated(() => { fetchApplications() })

onMounted(() => {
  activeTab.value = (route.query.tab as string) || getDefaultTab()
  fetchApplications()
  fetchUserCompanies()
})
</script>

<style scoped>
.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}

/* Кастомная плоская серая полоска прокрутки */
.custom-scrollbar {
  scrollbar-width: thin;
  scrollbar-color: var(--storefront-surface-muted,#d1d5db) var(--storefront-surface-muted,#f3f4f6);
}

.custom-scrollbar::-webkit-scrollbar {
  height: 4px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: var(--storefront-surface-muted,#f3f4f6);
  border-radius: 0;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--storefront-border,#d1d5db);
  border-radius: 0;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--storefront-border,#d1d5db);
}

</style>
