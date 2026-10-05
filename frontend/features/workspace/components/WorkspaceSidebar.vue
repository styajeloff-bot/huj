<template>
  <aside
    :class="[
      'flex flex-col bg-white border-r border-gray-200 transition-all duration-200 shrink-0',
      collapsed ? 'w-16' : 'w-64',
    ]"
  >
    <div class="h-16 flex items-center px-4 border-b border-gray-200">
      <NuxtLink :to="siteRoute" class="flex items-center gap-2 overflow-hidden">
        <img src="/images/logo.png" alt="CarCraft Multileasing" class="h-10 w-auto">
      </NuxtLink>
    </div>

    <nav class="flex-1 overflow-y-auto py-4 space-y-1 custom-scrollbar" aria-label="Навигация рабочего кабинета">
      <NuxtLink
        v-for="item in items"
        :key="item.key"
        :to="workspaceLocation(item.to)"
        :title="collapsed ? item.label : undefined"
        :class="[
          'flex items-center gap-3 mx-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
          isActive(item.to)
            ? 'bg-blue-50 text-blue-700'
            : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
        ]"
      >
        <component :is="item.icon" class="h-5 w-5 shrink-0" aria-hidden="true" />
        <span v-if="!collapsed" class="whitespace-nowrap">{{ item.label }}</span>
      </NuxtLink>
    </nav>

    <button
      type="button"
      class="h-12 flex items-center justify-center border-t border-gray-200 text-gray-500 hover:bg-gray-100"
      :aria-label="collapsed ? 'Развернуть меню' : 'Свернуть меню'"
      @click="$emit('toggle')"
    >
      <ChevronDoubleLeftIcon v-if="!collapsed" class="h-5 w-5" aria-hidden="true" />
      <ChevronDoubleRightIcon v-else class="h-5 w-5" aria-hidden="true" />
    </button>
  </aside>
</template>

<script setup lang="ts">
import { ChevronDoubleLeftIcon, ChevronDoubleRightIcon } from '@heroicons/vue/24/outline'
import { useHydrationReady } from '~/composables/useHydrationReady'
import { useAuthStore } from '~/features/auth/store/auth'
import {
  isBusinessRoleName,
  type WorkspaceAuthLike,
  type WorkspaceMenuItem,
} from '~/features/workspace/config/menu'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { getAvailableWorkspaceMenu } from '~/features/workspace/utils/menuVisibility'
import {
  buildWorkspaceLocation,
  buildWorkspaceSiteRoute,
  readWorkspaceReturnStorefront,
  WORKSPACE_RETURN_STOREFRONT_QUERY,
} from '~/features/workspace/returnContext'
import {
  resolveWorkspaceVisibilityScope,
  useWorkspaceVisibilityTarget,
} from '~/features/workspace/visibilityTarget'

defineProps<{ collapsed: boolean }>()
defineEmits<{ toggle: [] }>()

const authStore = useAuthStore()
const visibilityStore = useSectionVisibilityStore()
const route = useRoute()
const authHydrationReady = useHydrationReady()
const visibilityScope = computed(() => resolveWorkspaceVisibilityScope(authStore.userRole))
const visibilityTarget = useWorkspaceVisibilityTarget(visibilityScope)
const returnStorefront = computed(() => readWorkspaceReturnStorefront(
  route.query[WORKSPACE_RETURN_STOREFRONT_QUERY],
))
const siteRoute = computed(() => buildWorkspaceSiteRoute(returnStorefront.value))
const workspaceLocation = (path: string) => buildWorkspaceLocation(
  path,
  returnStorefront.value,
)
const authContext = computed<WorkspaceAuthLike>(() => ({
  isCarCraftEmployee: authStore.isCarCraftEmployee,
  isCompanyAdmin: authStore.isCompanyAdmin,
  isCompanyManager: authStore.isCompanyManager,
  canViewApplications: authStore.canViewApplications,
  sectionAccess: authStore.sectionAccess,
}))

const items = computed<WorkspaceMenuItem[]>(() => {
  if (!authHydrationReady.value) return []
  const role = authStore.userRole
  if (!isBusinessRoleName(role)) return []
  const target = visibilityTarget.value
  const visibility = target ? visibilityStore.visibilityFor(target) : {}
  return getAvailableWorkspaceMenu(
    role,
    authContext.value,
    visibility,
  )
})

const isActive = (to: string) => route.path === to || route.path.startsWith(to + '/')
</script>

<style scoped>
.custom-scrollbar { scrollbar-width: thin; scrollbar-color: #d1d5db #f3f4f6; }
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 0; }
</style>
