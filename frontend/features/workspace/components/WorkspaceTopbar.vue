<template>
  <header class="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
    <div class="flex items-center gap-3 min-w-0">
      <h1 class="text-lg font-semibold text-gray-900 truncate">{{ title }}</h1>
    </div>
    <div class="flex items-center gap-4">
      <CompanySwitcher />
      <NotificationBell />
      <UserDropdown />
    </div>
  </header>
</template>

<script setup lang="ts">
import { useHydrationReady } from '~/composables/useHydrationReady'
import CompanySwitcher from '~/features/layout/components/CompanySwitcher.vue'
import UserDropdown from '~/features/auth/components/UserDropdown.vue'
import NotificationBell from '~/components/ui/NotificationBell.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import {
  isBusinessRoleName,
} from '~/features/workspace/config/menu'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import {
  findWorkspaceMenuItemForPath,
  getAvailableWorkspaceMenu,
} from '~/features/workspace/utils/menuVisibility'
import {
  resolveWorkspaceVisibilityScope,
  useWorkspaceVisibilityTarget,
} from '~/features/workspace/visibilityTarget'

const authStore = useAuthStore()
const visibilityStore = useSectionVisibilityStore()
const route = useRoute()
const authHydrationReady = useHydrationReady()
const visibilityScope = computed(() => resolveWorkspaceVisibilityScope(authStore.userRole))
const visibilityTarget = useWorkspaceVisibilityTarget(visibilityScope)

const title = computed(() => {
  if (!authHydrationReady.value) return 'Рабочий кабинет'
  const role = authStore.userRole
  if (isBusinessRoleName(role)) {
    const target = visibilityTarget.value
    const visibility = target ? visibilityStore.visibilityFor(target) : {}
    const item = findWorkspaceMenuItemForPath(
      getAvailableWorkspaceMenu(role, authStore, visibility),
      route.path,
    )
    if (item) return item.label
  }
  return 'Рабочий кабинет'
})
</script>
