<template>
  <div>
    <div class="mb-6 border-b border-gray-200">
      <nav
        class="flex space-x-6"
        aria-label="Программы стимулирования"
        role="tablist"
      >
        <button
          ref="supportTab"
          id="organization-support-programs-tab"
          type="button"
          role="tab"
          aria-controls="organization-support-programs-panel"
          :aria-selected="activeTab === 'support'"
          :tabindex="activeTab === 'support' ? 0 : -1"
          class="border-b-2 px-1 py-2 text-sm font-medium"
          :class="activeTab === 'support'
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'"
          @click="selectTab('support')"
          @keydown="handleTabKeydown($event, 'support')"
        >
          Программы поддержки
        </button>
        <button
          ref="compensationsTab"
          id="organization-compensations-tab"
          type="button"
          role="tab"
          aria-controls="organization-compensations-panel"
          :aria-selected="activeTab === 'compensations'"
          :tabindex="activeTab === 'compensations' ? 0 : -1"
          class="border-b-2 px-1 py-2 text-sm font-medium"
          :class="activeTab === 'compensations'
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'"
          @click="selectTab('compensations')"
          @keydown="handleTabKeydown($event, 'compensations')"
        >
          Компенсации
        </button>
      </nav>
    </div>

    <component
      :is="supportPanel"
      v-show="activeTab === 'support'"
      id="organization-support-programs-panel"
      role="tabpanel"
      aria-labelledby="organization-support-programs-tab"
      tabindex="0"
    />
    <component
      :is="compensationPanel"
      v-show="activeTab === 'compensations'"
      id="organization-compensations-panel"
      role="tabpanel"
      aria-labelledby="organization-compensations-tab"
      tabindex="0"
    />
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

type SupportWorkspaceTab = 'support' | 'compensations'

defineProps<{
  supportPanel: Component
  compensationPanel: Component
}>()

const route = useRoute()
const router = useRouter()
const activeTab = ref<SupportWorkspaceTab>(
  route.query.tab === 'compensations' ? 'compensations' : 'support',
)
const supportTab = ref<HTMLButtonElement | null>(null)
const compensationsTab = ref<HTMLButtonElement | null>(null)

watch(
  () => route.query.tab,
  tab => {
    activeTab.value = tab === 'compensations' ? 'compensations' : 'support'
  },
)

const selectTab = (tab: SupportWorkspaceTab, focus = false) => {
  activeTab.value = tab

  const query = { ...route.query }
  if (tab === 'compensations') query.tab = 'compensations'
  else delete query.tab
  void router.replace({ query })

  if (focus) {
    nextTick(() => {
      const target = tab === 'support' ? supportTab.value : compensationsTab.value
      target?.focus()
    })
  }
}

const handleTabKeydown = (event: KeyboardEvent, currentTab: SupportWorkspaceTab) => {
  let nextTab: SupportWorkspaceTab | null = null

  switch (event.key) {
    case 'ArrowLeft':
    case 'ArrowRight':
      nextTab = currentTab === 'support' ? 'compensations' : 'support'
      break
    case 'Home':
      nextTab = 'support'
      break
    case 'End':
      nextTab = 'compensations'
      break
  }

  if (nextTab) {
    event.preventDefault()
    selectTab(nextTab, true)
  }
}
</script>
