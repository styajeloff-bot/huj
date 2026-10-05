<template>
  <div data-storefront-block="client.auth" class="min-h-screen flex items-center justify-center bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-md w-full space-y-8">
      <div>
        <div class="mx-auto h-12 w-auto flex justify-center">
          <nuxt-link :to="publicRoute('/')" class="flex items-center">
            <img :src="logo_url" :alt="storefrontLabel" class="h-8 w-auto">
            <span class="ml-2 text-xl font-bold text-[color:var(--storefront-text,#111827)]">{{ storefrontLabel }}</span>
          </nuxt-link>
        </div>
        <h2 class="mt-6 text-center text-3xl font-bold text-[color:var(--storefront-title,#111827)]">
          Подтвердите вход
        </h2>
        <p class="mt-2 text-center text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Введите 6-значный код из приложения-аутентификатора или резервный код.
        </p>
      </div>

      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-6">
        <form @submit.prevent="handleSubmit" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1" for="mfa-code">
              Код подтверждения
            </label>
            <input
              id="mfa-code"
              v-model="code"
              inputmode="text"
              maxlength="20"
              required
              autocomplete="one-time-code"
              placeholder="000000"
              class="storefront-control input-field text-center text-lg tracking-widest font-mono uppercase"
              @input="sanitize"
            >
            <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              Принимаются TOTP-коды (6 цифр) и backup-коды (до 20 символов).
            </p>
          </div>

          <p v-if="error" class="text-sm text-[color:var(--storefront-error-text,#dc2626)]">{{ error }}</p>

          <button
            type="submit"
            :disabled="submitting || code.length < 6"
            class="w-full btn-primary disabled:opacity-50"
          >
            {{ submitting ? 'Проверяем...' : 'Войти' }}
          </button>

          <button
            type="button"
            class="storefront-action-ghost w-full text-sm text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:text-[color:var(--storefront-ghost-hover-foreground,#374151)]"
            @click="cancel"
          >
            Отменить и вернуться ко входу
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { useAuthStore } from '~/features/auth/store/auth'
import { buildWorkspaceLocation } from '~/features/workspace/returnContext'
import { createAuthApi } from '~/features/auth/api/authApi'

useHead({ title: 'MFA — CarCraft Multileasing' })

definePageMeta({
  layout: 'default'
})

const config = useRuntimeConfig()
const route = useRoute()
const router = useRouter()
const { logo_url, publicRoute, slug } = useStorefront()
const storefrontLabel = computed(() => slug.value ? `Витрина ${slug.value}` : 'CarCraft')
const authStore = useAuthStore()
const api = createAuthApi(config)

const code = ref('')
const submitting = ref(false)
const error = ref('')

/**
 * `mfaToken` is preferred from the Pinia store (set during login/verify-phone),
 * but we also accept it via `?token=` as a hard fallback — some flows land
 * here after a page reload which drops in-memory state.
 */
const mfaToken = computed<string | null>(() => {
  const pending = authStore.mfaPending?.mfaToken
  if (pending) return pending
  const q = route.query.token
  return typeof q === 'string' && q.length > 0 ? q : null
})

const sanitize = () => {
  // Allow alphanum + dashes (TOTP is digits, backup codes may be any).
  code.value = code.value.replace(/[^0-9a-zA-Z-]/g, '').slice(0, 20)
}

const handleSubmit = async () => {
  if (!mfaToken.value) {
    error.value = 'Сессия MFA истекла. Войдите заново.'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const res = await api.verifyMfa({
      mfaToken: mfaToken.value,
      code: code.value
    })
    if (res.user) {
      authStore.setUser(res.user)
    }
    authStore.clearMfaPending()
    const fromHeader = route.query.account === '1'
    if (fromHeader) sessionStorage.removeItem('redirectAfterLogin')
    const redirect = fromHeader
      ? authStore.homeRoute.startsWith('/workspace')
        ? buildWorkspaceLocation(authStore.homeRoute, slug.value)
        : publicRoute(authStore.homeRoute)
      : typeof route.query.redirect === 'string'
      ? route.query.redirect
      : authStore.isBusinessRole ? authStore.homeRoute : publicRoute(authStore.homeRoute)
    await navigateTo(redirect)
  } catch (err: any) {
    error.value = err?.data?.error || 'Неверный код. Попробуйте снова.'
  } finally {
    submitting.value = false
  }
}

const cancel = () => {
  authStore.clearMfaPending()
  router.push(publicRoute('/auth'))
}
</script>
