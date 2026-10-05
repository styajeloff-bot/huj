<template>
  <div data-storefront-block="public.error" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] flex items-center justify-center px-4">
    <div class="max-w-md w-full">
      <div class="text-center">
        <!-- Иконка поиска -->
        <div class="mx-auto flex items-center justify-center w-24 h-24 bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] rounded-full mb-6">
          <svg class="w-12 h-12 text-[color:var(--storefront-warning-icon,#ca8a04)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        
        <h1 class="text-6xl font-bold text-[color:var(--storefront-title,#111827)] mb-4">404</h1>
        <h2 class="text-2xl font-semibold text-[color:var(--storefront-title,#374151)] mb-4">Страница не найдена</h2>
        <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-8">
          Извините, запрашиваемая страница не существует или была перемещена.
        </p>
        
        <div class="space-y-4">
          <button 
            @click="goBack"
            class="btn-secondary w-full sm:w-auto px-6"
          >
            Назад
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
  title: '404 - Страница не найдена | CarCraft Multileasing'
})

const goBack = () => {
  if (process.client) {
    window.history.back()
  }
}
</script>