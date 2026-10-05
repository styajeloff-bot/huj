<template>
  <div data-storefront-block="client.auth" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-xl w-full space-y-8">
      <div class="text-center">
        <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)]">
          Требуется настройка MFA
        </h1>
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">
          Для вашей роли двухфакторная аутентификация обязательна.
          Настройте её сейчас, чтобы продолжить.
        </p>
      </div>

      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-6">
        <!-- Stage 1: QR + code -->
        <div v-if="stage === 'qr'">
          <div v-if="loading" class="text-center py-8">
            <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
            <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Готовим QR-код...</p>
          </div>

          <div v-else-if="setupData" class="space-y-6">
            <div class="flex justify-center">
              <img
                :src="`data:image/png;base64,${setupData.qrPngBase64}`"
                alt="MFA QR"
                class="w-56 h-56 border rounded-md p-2 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]"
              >
            </div>

            <div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] mb-1">
                Или введите секрет вручную:
              </div>
              <div class="font-mono text-sm bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] rounded px-3 py-2 break-all">
                {{ setupData.secret }}
              </div>
            </div>

            <form @submit.prevent="handleComplete" class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1" for="totp">
                  Код из приложения
                </label>
                <input
                  id="totp"
                  v-model="code"
                  inputmode="numeric"
                  maxlength="6"
                  required
                  placeholder="000000"
                  class="storefront-control input-field text-center text-lg tracking-widest font-mono"
                  @input="sanitize"
                >
              </div>

              <p v-if="error" class="text-sm text-[color:var(--storefront-error-text,#dc2626)]">{{ error }}</p>

              <button
                type="submit"
                :disabled="submitting || code.length !== 6"
                class="w-full btn-primary disabled:opacity-50"
              >
                {{ submitting ? 'Проверяем...' : 'Завершить настройку' }}
              </button>
            </form>
          </div>

          <div v-else class="text-center py-8 text-[color:var(--storefront-text-muted,#4b5563)]">
            Не удалось начать настройку. Возможно, сессия истекла.
            <button class="storefront-action-ghost ml-2 text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:underline" @click="$router.push(publicRoute('/auth'))">
              Войти заново
            </button>
          </div>
        </div>

        <!-- Stage 2: Backup codes -->
        <div v-else-if="stage === 'backup'" class="space-y-4">
          <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">
            Сохраните backup-коды
          </h2>
          <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Эти одноразовые коды позволят войти без приложения. Показываются только один раз.
          </p>
          <div class="grid grid-cols-2 gap-2 font-mono text-sm">
            <div
              v-for="bc in backupCodes"
              :key="bc"
              class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border rounded px-3 py-2 text-center"
            >
              {{ bc }}
            </div>
          </div>
          <div class="flex gap-3">
            <button class="btn-secondary" @click="downloadCodes">
              Скачать .txt
            </button>
            <button class="btn-primary flex-1" @click="finish">
              Я сохранил коды
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { useAuthStore } from '~/features/auth/store/auth'
import {
  createAuthApi,
  type MfaSetupResponse
} from '~/features/auth/api/authApi'

useHead({ title: 'Настройка MFA — CarCraft Multileasing' })

const config = useRuntimeConfig()
const route = useRoute()
const router = useRouter()
const { publicRoute } = useStorefront()
const authStore = useAuthStore()
const api = createAuthApi(config)

const stage = ref<'qr' | 'backup'>('qr')
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const setupData = ref<MfaSetupResponse | null>(null)
const code = ref('')
const backupCodes = ref<string[]>([])

const setupToken = computed<string | null>(() => {
  const pending = authStore.mfaPending?.setupToken
  if (pending) return pending
  const q = route.query.token
  return typeof q === 'string' && q.length > 0 ? q : null
})

const sanitize = () => {
  code.value = code.value.replace(/\D/g, '').slice(0, 6)
}

const initSetup = async () => {
  if (!setupToken.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    setupData.value = await api.setupMfa({ setupToken: setupToken.value })
  } catch (err: any) {
    error.value = err?.data?.error || 'Не удалось запустить настройку MFA'
  } finally {
    loading.value = false
  }
}

const handleComplete = async () => {
  if (!setupToken.value) {
    error.value = 'Сессия истекла. Войдите заново.'
    return
  }
  if (code.value.length !== 6) {
    error.value = 'Введите 6-значный код'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const res = await api.completeMfa({
      setupToken: setupToken.value,
      code: code.value
    })
    if (res.user) {
      authStore.setUser(res.user)
    }
    backupCodes.value = res.backupCodes
    stage.value = 'backup'
    authStore.clearMfaPending()
  } catch (err: any) {
    error.value = err?.data?.error || 'Неверный код. Попробуйте снова.'
  } finally {
    submitting.value = false
  }
}

const downloadCodes = () => {
  if (!process.client) return
  const blob = new Blob([backupCodes.value.join('\n') + '\n'], {
    type: 'text/plain;charset=utf-8'
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'carcraft-backup-codes.txt'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const finish = () => {
  router.push(authStore.isBusinessRole ? authStore.homeRoute : publicRoute(authStore.homeRoute))
}

onMounted(initSetup)
</script>
