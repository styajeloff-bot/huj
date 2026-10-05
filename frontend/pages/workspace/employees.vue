<template>
  <div class="space-y-6">
    <!-- Tab navigation -->
    <div v-if="authStore.isCarCraftEmployee" class="border-b border-[color:var(--storefront-border,#e5e7eb)]">
      <nav class="-mb-px flex space-x-8" aria-label="Вкладки раздела сотрудников">
        <button
          type="button"
          class="whitespace-nowrap pb-3 px-1 border-b-2 font-medium text-sm transition-colors"
          :class="activeTab === 'employees'
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'employees'"
        >
          Сотрудники компании
        </button>
        <button
          type="button"
          class="whitespace-nowrap pb-3 px-1 border-b-2 font-medium text-sm transition-colors"
          :class="activeTab === 'positions'
            ? 'border-blue-500 text-blue-600'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'positions'"
        >
          Справочник должностей
        </button>
      </nav>
    </div>

    <!-- Tab 1: Сотрудники компании -->
    <div v-show="activeTab === 'employees'">
      <EmployeesTab />
    </div>

    <!-- Tab 2: Справочник должностей (visible only to carcraft_employee) -->
    <div v-if="authStore.isCarCraftEmployee" v-show="activeTab === 'positions'">
      <PositionsTab />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import EmployeesTab from '~/features/employees/components/EmployeesTab.vue'
import PositionsTab from '~/features/employees/components/PositionsTab.vue'

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'] })

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeTab = ref<'employees' | 'positions'>('employees')

watch(
  () => route.query.tab,
  (tab) => {
    if (tab === 'positions' && authStore.isCarCraftEmployee) {
      activeTab.value = 'positions'
    } else {
      activeTab.value = 'employees'
    }
  },
  { immediate: true },
)

watch(activeTab, (tab) => {
  if (route.query.tab !== tab) {
    router.replace({
      query: {
        ...route.query,
        tab: tab === 'employees' ? undefined : tab,
      },
    })
  }
})
</script>
