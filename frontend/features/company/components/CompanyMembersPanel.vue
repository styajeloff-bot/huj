<template>
  <div data-storefront-block="client.cabinet">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">
        Сотрудники компании
      </h2>
      <button
        v-if="canManageSelectedCompany"
        class="btn-primary text-sm"
        @click="showInviteModal = true"
      >
        Пригласить сотрудника
      </button>
    </div>

    <!-- Company selector -->
    <div v-if="!fixedCompanyId && companies.length > 1" class="mb-4 max-w-md">
      <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">
        Компания
      </label>
      <select
        v-model="selectedCompanyId"
        class="storefront-control block w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-md shadow-sm focus:outline-none focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] sm:text-sm"
      >
        <option
          v-for="c in companies"
          :key="c.id"
          :value="c.id"
        >
          {{ c.name }}
        </option>
      </select>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем сотрудников...</p>
    </div>

    <!-- Error -->
    <div
      v-else-if="error"
      class="p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg text-sm text-[color:var(--storefront-error-text,#b91c1c)] mb-4"
    >
      {{ error }}
    </div>

    <!-- Table -->
    <div v-else class="overflow-x-auto">
      <table class="min-w-full divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
        <thead class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
          <tr>
            <th
              scope="col"
              class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider"
            >
              Имя
            </th>
            <th
              scope="col"
              class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider"
            >
              Телефон
            </th>
            <th
              scope="col"
              class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider"
            >
              Роль
            </th>
            <th
              scope="col"
              class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider"
            >
              Просмотр заявок
            </th>
            <th
              scope="col"
              class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider"
            >
              Создание заявок
            </th>
            <th
              scope="col"
              class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase tracking-wider"
            >
              Действия
            </th>
          </tr>
        </thead>
        <tbody class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
          <tr v-for="member in members" :key="member.user_id">
            <td class="px-4 py-3 whitespace-nowrap text-sm text-[color:var(--storefront-text,#111827)]">
              {{ member.name || '—' }}
            </td>
            <td class="px-4 py-3 whitespace-nowrap text-sm text-[color:var(--storefront-text,#111827)]">
              {{ member.phone || '—' }}
            </td>
            <td class="px-4 py-3 whitespace-nowrap text-sm text-[color:var(--storefront-text,#111827)]">
              <span
                class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                :class="roleBadgeClass(member.sub_role)"
              >
                {{ roleLabel(member.sub_role) }}
              </span>
              <select
                v-if="canChangeSelectedCompanyRoles && member.user_id !== authStore.user?.id"
                v-model="member.sub_role"
                class="storefront-control ml-2 text-xs border-[color:var(--storefront-border,#d1d5db)] rounded focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)]"
                @change="updateRole(member)"
              >
                <option value="administrator">Администратор</option>
                <option value="manager">Менеджер</option>
                <option value="employee">Сотрудник</option>
              </select>
            </td>
            <td class="px-4 py-3 whitespace-nowrap text-sm text-[color:var(--storefront-text,#111827)]">
              <input
                type="checkbox"
                :checked="member.can_view_applications"
                class="storefront-control rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                :disabled="!canManageSelectedCompany || updatingMember === member.user_id || member.user_id === authStore.user?.id"
                @change="togglePermission(member, 'can_view_applications', ($event.target as HTMLInputElement).checked)"
              />
            </td>
            <td class="px-4 py-3 whitespace-nowrap text-sm text-[color:var(--storefront-text,#111827)]">
              <input
                type="checkbox"
                :checked="member.can_create_applications"
                class="storefront-control rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                :disabled="!canManageSelectedCompany || updatingMember === member.user_id || member.user_id === authStore.user?.id"
                @change="togglePermission(member, 'can_create_applications', ($event.target as HTMLInputElement).checked)"
              />
            </td>
            <td class="px-4 py-3 whitespace-nowrap text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
              <button
                v-if="canDeleteSelectedCompanyMembers"
                type="button"
                class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)] disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="updatingMember === member.user_id || member.user_id === authStore.user?.id"
                @click="removeMember(member)"
              >
                Удалить
              </button>
            </td>
          </tr>
          <tr v-if="members.length === 0">
            <td
              colspan="6"
              class="px-4 py-8 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]"
            >
              Сотрудники не найдены
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <InviteEmployeeModal
      v-if="showInviteModal"
      :companies="inviteAllowedCompanies"
      :preselected-company-id="selectedCompanyId"
      @close="showInviteModal = false"
      @invited="onInvited"
    />
  </div>
</template>

<script setup lang="ts">
import { createAuthApi } from '~/features/auth/api/authApi'
import { createCompanyApi } from '~/features/company/api/companyApi'
import { useAuthStore } from '~/features/auth/store/auth'
import type { UserCompany } from '~/features/company/api/companyApi'
import type { UUID } from '~/types/ids'
import InviteEmployeeModal from './InviteEmployeeModal.vue'

const props = defineProps<{
  fixedCompanyId?: UUID
  fixedCompanyName?: string
}>()

interface Member {
  user_id: UUID
  name?: string | null
  phone?: string | null
  sub_role?: string | null
  can_view_applications: boolean
  can_create_applications: boolean
}

const authStore = useAuthStore()
const config = useRuntimeConfig()
const authApi = createAuthApi(config)
const companyApi = createCompanyApi(config)

const loading = ref(true)
const error = ref('')
const members = ref<Member[]>([])
const companies = ref<UserCompany[]>([])
const fixedCompanyId = computed<UUID>(() => props.fixedCompanyId ? props.fixedCompanyId : '')
const selectedCompanyId = ref<UUID>(fixedCompanyId.value)
const showInviteModal = ref(false)
const updatingMember = ref<UUID | null>(null)

const selectedCompany = computed(() =>
  companies.value.find((company) => company.id === selectedCompanyId.value) || null,
)
const selectedSubRole = computed(() => selectedCompany.value?.sub_role || null)
const canManageSelectedCompany = computed(() =>
  authStore.isCarCraftEmployee || selectedSubRole.value === 'administrator' || selectedSubRole.value === 'manager',
)
const canChangeSelectedCompanyRoles = computed(() =>
  authStore.isCarCraftEmployee || selectedSubRole.value === 'administrator',
)
const canDeleteSelectedCompanyMembers = computed(() =>
  authStore.isCarCraftEmployee || selectedSubRole.value === 'administrator',
)
const inviteAllowedCompanies = computed(() =>
  authStore.isCarCraftEmployee
    ? companies.value
    : companies.value.filter((company) =>
      company.sub_role === 'administrator' || company.sub_role === 'manager',
    ),
)

const roleLabel = (role?: string | null) => {
  switch (role) {
    case 'administrator': return 'Администратор'
    case 'manager': return 'Менеджер'
    case 'employee': return 'Сотрудник'
    default: return '—'
  }
}

const roleBadgeClass = (role?: string | null) => {
  switch (role) {
    case 'administrator': return 'bg-[color:rgb(var(--storefront-info-rgb,243_232_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-info-text,#6b21a8)]'
    case 'manager': return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]'
    case 'employee': return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
    default: return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
  }
}

const fetchCompanies = async () => {
  try {
    if (fixedCompanyId.value) {
      companies.value = [{
        id: fixedCompanyId.value,
        name: props.fixedCompanyName || 'Компания',
        sub_role: 'administrator',
        can_view_applications: true,
        can_create_applications: true,
      }]
      selectedCompanyId.value = fixedCompanyId.value
      return
    }
    const response = authStore.isCarCraftEmployee
      ? await companyApi.listCompanies()
      : await companyApi.getMyCompanies()
    const list: UserCompany[] = (response.companies || []).flatMap((c) => {
      const company = c as Record<string, unknown>
      if (typeof company.id !== 'string') return []
      const subRole = company.sub_role
      const option: UserCompany = {
        id: company.id,
        name: typeof company.name === 'string' && company.name ? company.name : 'Без названия',
        inn: typeof company.inn === 'string' ? company.inn : null,
        sub_role: authStore.isCarCraftEmployee
          ? 'administrator'
          : (typeof subRole === 'string' && subRole ? (subRole as UserCompany['sub_role']) : 'employee'),
        can_view_applications: authStore.isCarCraftEmployee
          ? true
          : Boolean(company.can_view_applications),
        can_create_applications: authStore.isCarCraftEmployee
          ? true
          : Boolean(company.can_create_applications),
      }
      return [option]
    })
    companies.value = list
    const preferredCompanyId = typeof authStore.user?.company_id === 'string'
      ? authStore.user.company_id
      : ''
    if (preferredCompanyId && list.some((company) => company.id === preferredCompanyId)) {
      selectedCompanyId.value = preferredCompanyId
    } else if (list.length === 1) {
      selectedCompanyId.value = list[0].id
    } else if (list.length > 1 && !selectedCompanyId.value) {
      selectedCompanyId.value = list[0].id
    }
  } catch (err: any) {
    console.error('Error fetching companies:', err)
  }
}

const fetchMembers = async () => {
  if (!selectedCompanyId.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await authApi.listCompanyMembers(selectedCompanyId.value)
    members.value = response.members || []
  } catch (err: any) {
    error.value = err.data?.error || 'Ошибка при загрузке сотрудников'
    members.value = []
  } finally {
    loading.value = false
  }
}

const syncSelectedCompany = async () => {
  if (!selectedCompanyId.value) return
  if (fixedCompanyId.value || authStore.isCarCraftEmployee) return
  try {
    await companyApi.setCompanySelectHistory(selectedCompanyId.value)
    await authStore.checkAuth(true)
  } catch (err) {
    console.error('Error syncing selected company:', err)
  }
}

const togglePermission = async (
  member: Member,
  field: 'can_view_applications' | 'can_create_applications',
  value: boolean,
) => {
  updatingMember.value = member.user_id
  try {
    await authApi.updateMemberPermissions(selectedCompanyId.value, member.user_id, {
      [field === 'can_view_applications' ? 'canViewApplications' : 'canCreateApplications']: value,
    })
    member[field] = value
  } catch (err: any) {
    error.value = err.data?.error || 'Ошибка при обновлении прав'
    // Revert optimistic update on error
    setTimeout(() => { error.value = '' }, 3000)
  } finally {
    updatingMember.value = null
  }
}

const updateRole = async (member: Member) => {
  if (!member.sub_role) return
  updatingMember.value = member.user_id
  try {
    await authApi.updateMemberRole(selectedCompanyId.value, member.user_id, member.sub_role)
  } catch (err: any) {
    error.value = err.data?.error || 'Ошибка при обновлении роли'
    setTimeout(() => { error.value = '' }, 3000)
  } finally {
    updatingMember.value = null
  }
}

const removeMember = async (member: Member) => {
  if (!selectedCompanyId.value || !canDeleteSelectedCompanyMembers.value) return
  if (!confirm('Удалить сотрудника из компании?')) return
  updatingMember.value = member.user_id
  try {
    await authApi.removeCompanyMember(selectedCompanyId.value, member.user_id)
    members.value = members.value.filter((item) => item.user_id !== member.user_id)
  } catch (err: any) {
    error.value = err.data?.error || 'Ошибка при удалении сотрудника'
    setTimeout(() => { error.value = '' }, 3000)
  } finally {
    updatingMember.value = null
  }
}

const onInvited = () => {
  showInviteModal.value = false
  fetchMembers()
}

watch(selectedCompanyId, () => {
  syncSelectedCompany()
  fetchMembers()
})

onMounted(() => {
  fetchCompanies().then(() => {
    if (selectedCompanyId.value) {
      fetchMembers()
    } else {
      loading.value = false
    }
  })
})
</script>
