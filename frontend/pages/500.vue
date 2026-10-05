<template>
  <div data-storefront-block="public.error" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] flex items-center justify-center px-4">
    <div class="max-w-md w-full">
      <div class="text-center">
        <!-- Иконка ошибки -->
        <div class="mx-auto flex items-center justify-center w-24 h-24 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] rounded-full mb-6">
          <svg class="w-12 h-12 text-[color:var(--storefront-error-icon,#dc2626)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        </div>
        
        <h1 class="text-4xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">500</h1>
        <h2 class="text-2xl font-semibold text-[color:var(--storefront-title,#374151)] mb-4">Внутренняя ошибка сервера</h2>
        <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-8">
          Произошла ошибка на сервере. Мы уже работаем над её устранением. Попробуйте обновить страницу позже.
        </p>
        
        <div class="space-y-4">
          <button 
            @click="reloadPage"
            class="btn-primary w-full sm:w-auto px-6"
          >
            Обновить страницу
          </button>
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
useHead({
  title: '500 - Внутренняя ошибка сервера | CarCraft Multileasing'
})

const reloadPage = () => {
  if (process.client) {
    window.location.reload()
  }
}
</script>