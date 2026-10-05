<template>
  <div data-storefront-block="client.auth" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
    <div class="px-6 py-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#e5e7eb)]">
      <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">
        Безопасность
      </h3>
    </div>

    <div class="p-6 space-y-4">
      <div class="flex items-center justify-between gap-4">
        <div>
          <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">
            Двухфакторная аутентификация
          </div>
          <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
            Дополнительная защита аккаунта одноразовыми кодами
          </div>
          <div
            v-if="status?.enabled && typeof status.backupCodesRemaining === 'number'"
            class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]"
          >
            Осталось backup-кодов: {{ status.backupCodesRemaining }}
          </div>
        </div>
        <button
          :class="status?.enabled ? 'btn-secondary text-[color:var(--storefront-primary-foreground,#dc2626)]' : 'btn-primary'"
          :disabled="busy || loading"
          @click="toggle2fa"
        >
          {{ status?.enabled ? 'Отключить 2FA' : 'Включить 2FA' }}
        </button>
      </div>
    </div>

    <MfaSetupModal
      v-if="showSetupModal"
      @completed="onCompleted"
      @close="showSetupModal = false"
    />
  </div>
</template>

<script setup lang="ts">
import { createAuthApi, type MfaStatusResponse } from '~/features/auth/api/authApi'
import MfaSetupModal from '~/features/auth/components/MfaSetupModal.vue'

const config = useRuntimeConfig()
const api = createAuthApi(config)
const { showToast } = useToast()

const status = ref<MfaStatusResponse | null>(null)
const loading = ref(true)
const busy = ref(false)
const showSetupModal = ref(false)

const loadStatus = async () => {
  loading.value = true
  try {
    status.value = await api.getMfaStatus()
  } catch {
    status.value = null
  } finally {
    loading.value = false
  }
}

const toggle2fa = async () => {
  if (busy.value) return
  if (status.value?.enabled) {
    if (!confirm('Отключить двухфакторную аутентификацию? Это снизит безопасность аккаунта.')) {
      return
    }
    const code = prompt('Введите текущий 6-значный код из приложения-аутентификатора:')?.trim()
    if (!code || !/^\d{6}$/.test(code)) {
      showToast.error('Нужен действующий 6-значный код')
      return
    }
    busy.value = true
    try {
      await api.disableMfa({ code })
      showToast.success('Двухфакторная аутентификация отключена')
      await loadStatus()
    } catch (err: unknown) {
      const msg = (err as { data?: { error?: string } }).data?.error
      showToast.error(msg || 'Не удалось отключить 2FA')
    } finally {
      busy.value = false
    }
  } else {
    showSetupModal.value = true
  }
}

const onCompleted = async () => {
  showToast.success('Двухфакторная аутентификация включена')
  await loadStatus()
}

onMounted(loadStatus)
</script>
