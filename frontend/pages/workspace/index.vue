<template>
  <div class="flex items-center justify-center py-20 text-gray-500">
    <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import {
  isBusinessRoleName,
} from '~/features/workspace/config/menu'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { getFirstAvailableWorkspaceRoute } from '~/features/workspace/utils/menuVisibility'
import {
  resolveWorkspaceVisibilityScope,
  useWorkspaceVisibilityTarget,
} from '~/features/workspace/visibilityTarget'

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })

const authStore = useAuthStore()
const visibilityStore = useSectionVisibilityStore()
const visibilityScope = computed(() => resolveWorkspaceVisibilityScope(authStore.userRole))
const visibilityTarget = useWorkspaceVisibilityTarget(visibilityScope)

onMounted(async () => {
  const role = authStore.userRole
  if (isBusinessRoleName(role)) {
    const target = visibilityTarget.value
    if (target) await visibilityStore.load(target)
    const visibility = target ? visibilityStore.visibilityFor(target) : {}
    await navigateTo(getFirstAvailableWorkspaceRoute(role, authStore, visibility))
  } else {
    await navigateTo('/cabinet')
  }
})
</script>
