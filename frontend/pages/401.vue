<template>
  <div data-storefront-block="public.error" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] flex items-center justify-center px-4">
    <div class="max-w-md w-full">
      <div class="text-center">
        <!-- Иконка замка -->
        <div class="mx-auto flex items-center justify-center w-24 h-24 bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] rounded-full mb-6">
          <svg class="w-12 h-12 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        
        <h1 class="text-4xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">401</h1>
        <h2 class="text-2xl font-semibold text-[color:var(--storefront-title,#374151)] mb-4">Доступ запрещен</h2>
        <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-8">
          {{ authStore.isAuthenticated 
            ? 'У вас недостаточно прав для доступа к этой странице. Обратитесь к администратору системы.' 
            : 'Для доступа к этой странице необходимо авторизоваться в системе.'
          }}
        </p>
        
        <div class="space-y-4">
          <button 
            v-if="!authStore.isAuthenticated"
            @click="goToLogin"
            class="btn-primary w-full sm:w-auto px-6"
          >
            Войти в систему
          </button>
          <NuxtLink 
            v-else
            to="/cabinet"
            class="btn-primary w-full sm:w-auto px-6 inline-block text-center"
          >
            Перейти в личный кабинет
          </NuxtLink>
          <br>
          <NuxtLink 
            to="/"
            class="text-[color:var(--storefront-link,#2563eb)] hover:text-[color:var(--storefront-link-hover,#1d4ed8)] font-medium inline-block"
          >
            Вернуться на главную
          </NuxtLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
const authStore = useAuthStore()

useHead({
  title: '401 - Доступ запрещен | CarCraft Multileasing'
})

const goToLogin = () => {
  navigateTo('/auth')
}
</script>
