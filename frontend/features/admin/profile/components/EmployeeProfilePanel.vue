<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">Мой профиль</h2>
    </div>

    <div class="space-y-6">
      <!-- Основная информация -->
      <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div class="px-6 py-4 bg-gray-50 border-b border-gray-200">
          <h3 class="text-lg font-medium text-gray-900">Основная информация</h3>
        </div>
        <div class="p-6 space-y-4">
          <div class="flex justify-between">
            <span class="text-gray-600">Имя:</span>
            <span class="font-medium text-gray-900">{{ user?.name || '—' }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-gray-600">Роль:</span>
            <span class="font-medium text-gray-900">Сотрудник CarCraft</span>
          </div>
          <div v-if="user?.company_name" class="flex justify-between">
            <span class="text-gray-600">Компания:</span>
            <span class="font-medium text-gray-900">{{ user.company_name }}</span>
          </div>
        </div>
      </div>

      <!-- Мои компании -->
      <UserCompaniesSection />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'
import UserCompaniesSection from '~/components/ui/UserCompaniesSection.vue'

const authStore = useAuthStore()
const user = computed(() => authStore.user)
</script>
