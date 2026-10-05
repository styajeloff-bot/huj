<template>
  <div data-storefront-block="client.auth" class="min-h-screen flex items-center justify-center bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4">
    <div class="max-w-md w-full bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#e5e7eb)] rounded-xl shadow-sm p-6 sm:p-8 text-center">
      <!-- Loading -->
      <template v-if="status === 'loading'">
        <div class="inline-flex items-center justify-center w-12 h-12 rounded-full bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text-muted,#2563eb)] mb-4">
          <svg class="text-[color:var(--storefront-icon,inherit)] w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
          </svg>
        </div>
        <h1 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Активируем ваш вход…</h1>
        <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] mt-2">Это займёт пару секунд.</p>
      </template>

      <!-- Success (brief — user gets redirected right after) -->
      <template v-else-if="status === 'success'">
        <div class="inline-flex items-center justify-center w-12 h-12 rounded-full bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#059669)] mb-4">
          <svg class="text-[color:var(--storefront-icon,inherit)] w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h1 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Добро пожаловать{{ greetingSuffix }}!</h1>
        <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] mt-2">Переходим в личный кабинет…</p>
      </template>

      <!-- Error -->
      <template v-else>
        <div class="inline-flex items-center justify-center w-12 h-12 rounded-full bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#dc2626)] mb-4">
          <svg class="text-[color:var(--storefront-icon,inherit)] w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M4.93 19h14.14a2 2 0 001.73-3l-7.07-12a2 2 0 00-3.46 0L3.2 16a2 2 0 001.73 3z" />
          </svg>
        </div>
        <h1 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">{{ errorTitle }}</h1>
        <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] mt-2">{{ errorMessage }}</p>
        <NuxtLink to="/" class="storefront-action-primary mt-6 inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] rounded-md hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]">
          На главную
        </NuxtLink>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { createAuthApi } from '~/features/auth/api/authApi'

// Magic links are a public landing — skip whatever middleware the rest of
// the app uses (e.g. `auth`).
definePageMeta({ middleware: [] })

type Stage = 'loading' | 'success' | 'expired' | 'error'

const route = useRoute()
const config = useRuntimeConfig()
const api = createAuthApi(config)
const authStore = useAuthStore()

const status = ref<Stage>('loading')
const errorTitle = ref('Ссылка недействительна')
const errorMessage = ref('Попросите отправителя прислать её заново.')
const userName = ref('')

const greetingSuffix = computed(() => (userName.value ? `, ${userName.value}` : ''))

const consume = async () => {
  const token = String(route.params.token || '')
  if (!token) {
    status.value = 'error'
    return
  }

  try {
    const resp = await api.consumeMagicLink(token)
    userName.value = resp.user?.name || ''
    // Populate auth store from the freshly-set cookie so the next page
    // doesn't bounce to the login screen.
    await authStore.checkAuth(true)
    status.value = 'success'
    // Short pause so the user sees the confirmation, then redirect.
    setTimeout(() => {
      navigateTo('/cabinet?tab=signatures')
    }, 900)
  } catch (err: unknown) {
    const e = err as { status?: number; statusCode?: number; data?: { detail?: string } }
    const code = e.status || e.statusCode
    if (code === 410) {
      status.value = 'expired'
      errorTitle.value = 'Ссылка больше не действительна'
      errorMessage.value =
        e.data?.detail || 'Срок действия истёк или ссылка уже была использована. Попросите отправить её заново.'
    } else {
      status.value = 'error'
      errorMessage.value = e.data?.detail || 'Попробуйте открыть ссылку ещё раз или обратитесь в поддержку.'
    }
  }
}

onMounted(() => {
  consume()
})
</script>
