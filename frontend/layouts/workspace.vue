<template>
  <div class="relative h-screen flex bg-gray-50 overflow-hidden">
    <WorkspaceSidebar
      class="flex"
      :collapsed="collapsed"
      @toggle="collapsed = !collapsed"
    />

    <div class="relative flex-1 flex flex-col min-w-0">
      <WorkspaceTopbar />
      <main class="relative flex-1 overflow-y-auto p-6">
        <slot />
      </main>
    </div>

    <ToastNotifications />
  </div>
</template>

<script setup lang="ts">
import WorkspaceSidebar from '~/features/workspace/components/WorkspaceSidebar.vue'
import WorkspaceTopbar from '~/features/workspace/components/WorkspaceTopbar.vue'

useHead({
  htmlAttrs: { class: 'h-full overflow-hidden' },
  bodyAttrs: { class: 'h-full overflow-hidden' },
})

const collapsed = ref(false)
</script>
