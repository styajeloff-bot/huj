<template>
  <NuxtPage v-if="isNestedAuthRoute" />
  <div data-storefront-block="client.auth" v-else class="min-h-screen flex items-center justify-center bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-md w-full space-y-8">
      <div>
        <div class="mx-auto h-12 w-auto flex justify-center">
          <nuxt-link :to="publicRoute('/')" class="flex items-center">
            <img :src="logo_url" :alt="storefrontLabel" class="h-8 w-auto">
            <span class="ml-2 text-xl font-bold text-[color:var(--storefront-text,#111827)]">{{ storefrontLabel }}</span>
          </nuxt-link>
        </div>
        <h2 class="mt-6 text-center text-3xl font-bold text-[color:var(--storefront-title,#111827)]">
          Вход в личный кабинет
        </h2>
        <p class="mt-2 text-center text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Войдите в систему для доступа к функциям лизинга
        </p>
      </div>

      <AuthModal @close="handleAuthClose" @authenticated="handleAuthenticated" />
    </div>
  </div>
</template>

<script setup lang="ts">
import AuthModal from '~/features/auth/components/AuthModal.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { useStorefront } from '~/features/storefront'
useHead({
  title: 'Авторизация - CarCraft Multileasing',
  meta: [
    { name: 'description', content: 'Вход в личный кабинет CarCraft Multileasing. Управление заявками, расчет лизинга, работа с автопарком.' }
  ]
})

const route = useRoute()
const authStore = useAuthStore()
const favoritesStore = useFavoritesStore()
const { logo_url, publicRoute, slug } = useStorefront()
const storefrontLabel = computed(() => slug.value ? `Витрина ${slug.value}` : 'CarCraft')
const isNestedAuthRoute = computed(() => route.path !== publicRoute('/auth'))
const accountRoute = computed(() => authStore.isBusinessRole ? authStore.homeRoute : publicRoute(authStore.homeRoute))

if (route.path === publicRoute('/auth') && authStore.isAuthenticated) {
  const redirectTo = typeof route.query.redirect === 'string' ? route.query.redirect : accountRoute.value
  await navigateTo(redirectTo)
}

const handleAuthenticated = async () => {
  // Fire-and-forget: merge guest favorites in background, don't block navigation
  favoritesStore.mergeGuestFavorites()
  const redirectTo = typeof route.query.redirect === 'string' ? route.query.redirect : accountRoute.value
  navigateTo(redirectTo)
}

const handleAuthClose = () => {
  // Don't navigate away if user just authenticated — handleAuthenticated already navigates
  if (!authStore.isAuthenticated) {
    navigateTo(publicRoute('/'))
  }
}
</script>
