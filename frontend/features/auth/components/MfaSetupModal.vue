<template>
  <Modal :show="true" :show-footer="false" :show-header="false" size="md" @close="onClose">
    <div data-storefront-block="client.auth" class="flex items-center justify-between pb-4">
      <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
        {{ stage === 'backup' ? 'Сохраните backup-коды' : 'Настройка двухфакторной аутентификации' }}
      </h3>
      <button
        type="button"
        class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] transition-colors"
        aria-label="Закрыть"
        @click="onClose"
      >
        <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <div data-storefront-block="client.auth" v-if="stage === 'qr'" class="space-y-4">
      <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
        Отсканируйте QR-код в приложении-аутентификаторе и введите 6-значный код.
      </p>

      <div v-if="loading" class="text-center py-8">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">
          Готовим QR-код...
        </p>
      </div>

      <div v-else-if="setupData" class="space-y-4">
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
        <form class="space-y-3" @submit.prevent="complete">
          <input
            v-model="code"
            inputmode="numeric"
            maxlength="6"
            required
            placeholder="000000"
            class="storefront-control input-field text-center text-lg tracking-widest font-mono"
            @input="sanitize"
          >
          <p v-if="error" class="text-sm text-[color:var(--storefront-error-text,#dc2626)]">
            {{ error }}
          </p>
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
        {{ error || 'Не удалось начать настройку.' }}
      </div>
    </div>

    <div data-storefront-block="client.auth" v-else-if="stage === 'backup'" class="space-y-4">
      <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
        Эти одноразовые коды позволят войти без приложения. Показываются только один раз — сохраните их.
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
  </Modal>
</template>

<script setup lang="ts">
import { createAuthApi, type MfaSetupResponse } from '~/features/auth/api/authApi'

const props = defineProps<{
  /** Optional setup token issued during login (mfaSetupRequired branch).
   * When omitted the user must be authenticated — backend uses session
   * cookie to identify them. */
  setupToken?: string | null
}>()

const emit = defineEmits<{
  (e: 'completed'): void
  (e: 'close'): void
}>()

const config = useRuntimeConfig()
const api = createAuthApi(config)

const stage = ref<'qr' | 'backup'>('qr')
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const setupData = ref<MfaSetupResponse | null>(null)
const code = ref('')
const backupCodes = ref<string[]>([])

const sanitize = () => {
  code.value = code.value.replace(/\D/g, '').slice(0, 6)
}

const init = async () => {
  loading.value = true
  error.value = ''
  try {
    setupData.value = await api.setupMfa(
      props.setupToken ? { setupToken: props.setupToken } : {},
    )
  } catch (err: unknown) {
    error.value =
      (err as { data?: { error?: string } }).data?.error
      || 'Не удалось запустить настройку MFA'
  } finally {
    loading.value = false
  }
}

const complete = async () => {
  if (code.value.length !== 6) {
    error.value = 'Введите 6-значный код'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const res = await api.completeMfa(
      props.setupToken
        ? { setupToken: props.setupToken, code: code.value }
        : { code: code.value },
    )
    backupCodes.value = res.backupCodes
    stage.value = 'backup'
  } catch (err: unknown) {
    error.value =
      (err as { data?: { error?: string } }).data?.error
      || 'Неверный код. Попробуйте снова.'
  } finally {
    submitting.value = false
  }
}

const downloadCodes = () => {
  if (!process.client) return
  const blob = new Blob([backupCodes.value.join('\n') + '\n'], {
    type: 'text/plain;charset=utf-8',
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
  emit('completed')
  emit('close')
}

const onClose = () => {
  // On the QR stage cancelling means setup was never completed — just
  // close. On backup stage closing without saving codes is the user's
  // problem (they were warned); we still emit completed so the parent
  // refreshes profile.two_factor_enabled.
  if (stage.value === 'backup') emit('completed')
  emit('close')
}

onMounted(init)
</script>
