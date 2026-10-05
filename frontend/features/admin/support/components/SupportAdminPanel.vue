<template>
  <div>
    <div class="border-b border-gray-200 mb-6">
      <nav
        class="flex space-x-6"
        aria-label="Программы стимулирования"
        role="tablist"
      >
        <button
          ref="supportTab"
          id="support-programs-tab"
          type="button"
          role="tab"
          aria-controls="support-programs-panel"
          :aria-selected="activeTab === 'support'"
          :tabindex="activeTab === 'support' ? 0 : -1"
          class="py-2 px-1 border-b-2 font-medium text-sm"
          :class="activeTab === 'support' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'support'"
          @keydown="handleTabKeydown($event, 'support')"
        >
          Программы поддержки
        </button>
        <button
          ref="compensationsTab"
          id="compensations-tab"
          type="button"
          role="tab"
          aria-controls="compensations-panel"
          :aria-selected="activeTab === 'compensations'"
          :tabindex="activeTab === 'compensations' ? 0 : -1"
          class="py-2 px-1 border-b-2 font-medium text-sm"
          :class="activeTab === 'compensations' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'compensations'"
          @keydown="handleTabKeydown($event, 'compensations')"
        >
          Компенсации
        </button>
      </nav>
    </div>

    <SupportPanel
      v-show="activeTab === 'support'"
      id="support-programs-panel"
      role="tabpanel"
      aria-labelledby="support-programs-tab"
      tabindex="0"
      :readonly="false"
      :deep-link-target="deepLinkTarget"
      title="Программы стимулирования продаж"
      create-button-label="Создать программу"
      loading-text="Загружаем программы стимулирования продаж..."
      empty-text="Программы стимулирования продаж не найдены"
    />
    <CompensationRegistryPanel
      v-show="activeTab === 'compensations'"
      id="compensations-panel"
      role="tabpanel"
      aria-labelledby="compensations-tab"
      tabindex="0"
    />
  </div>
</template>

<script setup lang="ts">
import SupportPanel from '~/features/support/components/SupportPanel.vue'
import CompensationRegistryPanel from '~/features/compensations/components/CompensationRegistryPanel.vue'
import { readSupportDeepLinkTarget } from '~/utils/supportDeepLink'

type AdminSupportTab = 'support' | 'compensations'

const activeTab = ref<AdminSupportTab>('support')
const route = useRoute()
const deepLinkTarget = computed(() => readSupportDeepLinkTarget(route.query))
const supportTab = ref<HTMLButtonElement | null>(null)
const compensationsTab = ref<HTMLButtonElement | null>(null)

const selectTab = (tab: AdminSupportTab) => {
  activeTab.value = tab
  nextTick(() => {
    const target = tab === 'support' ? supportTab.value : compensationsTab.value
    target?.focus()
  })
}

const handleTabKeydown = (event: KeyboardEvent, currentTab: AdminSupportTab) => {
  let nextTab: AdminSupportTab | null = null

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
    selectTab(nextTab)
  }
}
</script>
