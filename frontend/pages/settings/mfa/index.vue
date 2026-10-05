<template>
  <div data-storefront-block="client.auth" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8">
    <div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)]">
          Двухфакторная аутентификация
        </h1>
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">
          Дополнительный уровень защиты вашего аккаунта с помощью одноразовых кодов.
        </p>
      </div>

      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow overflow-hidden">
        <div v-if="loading" class="p-8 text-center">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
          <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем статус...</p>
        </div>

        <div v-else class="p-6">
          <div class="flex items-start justify-between gap-6 flex-wrap">
            <div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Статус MFA</div>
              <div class="mt-1 flex items-center gap-2">
                <span
                  class="inline-flex items-center rounded-full px-3 py-1 text-sm font-semibold"
                  :class="
                    status?.enabled
                      ? 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]'
                      : 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
                  "
                >
                  {{ status?.enabled ? 'Включена' : 'Отключена' }}
                </span>
              </div>
              <p
                v-if="status?.enabled && typeof status.backupCodesRemaining === 'number'"
                class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]"
              >
                Осталось backup-кодов: {{ status.backupCodesRemaining }}
              </p>
            </div>

            <div class="flex flex-col sm:flex-row gap-3">
              <template v-if="status?.enabled">
                <button
                  class="btn-secondary"
                  :disabled="regenerating"
                  @click="handleRegenerate"
                >
                  {{ regenerating ? 'Генерация...' : 'Перегенерировать backup codes' }}
                </button>
                <button
                  class="storefront-action-destructive btn-danger"
                  :disabled="disabling"
                  @click="handleDisable"
                >
                  {{ disabling ? 'Отключаем...' : 'Отключить' }}
                </button>
              </template>
              <template v-else>
                <NuxtLink to="/settings/mfa/setup" class="btn-primary">
                  Настроить MFA
                </NuxtLink>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Freshly regenerated backup codes — show once -->
      <div
        v-if="regeneratedCodes && regeneratedCodes.length > 0"
        class="mt-6 bg-[color:rgb(var(--storefront-warning-rgb,254_252_232)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fef08a)] rounded-lg p-6"
      >
        <h2 class="text-lg font-semibold text-[color:var(--storefront-warning-text,#713f12)]">
          Новые backup-коды
        </h2>
        <p class="mt-1 text-sm text-[color:var(--storefront-warning-text,#854d0e)]">
          Сохраните коды в надёжном месте — они показываются только один раз.
        </p>
        <div class="mt-4 grid grid-cols-2 gap-2 font-mono text-sm">
          <div
            v-for="code in regeneratedCodes"
            :key="code"
            class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fef08a)] rounded px-3 py-2 text-center"
          >
            {{ code }}
          </div>
        </div>
        <div class="mt-4 flex gap-3">
          <button class="btn-secondary" @click="downloadCodes(regeneratedCodes)">
            Скачать .txt
          </button>
          <button class="btn-primary" @click="regeneratedCodes = null">
            Я сохранил коды
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { createAuthApi, type MfaStatusResponse } from '~/features/auth/api/authApi'

definePageMeta({
  middleware: 'auth'
})

useHead({ title: 'Двухфакторная аутентификация — CarCraft Multileasing' })

const config = useRuntimeConfig()
const api = createAuthApi(config)
const toast = useToast()

const loading = ref(true)
const status = ref<MfaStatusResponse | null>(null)
const disabling = ref(false)
const regenerating = ref(false)
const regeneratedCodes = ref<string[] | null>(null)

const loadStatus = async () => {
  loading.value = true
  try {
    status.value = await api.getMfaStatus()
  } catch (err) {
    toast.apiError(err as any, 'Не удалось загрузить статус MFA')
  } finally {
    loading.value = false
  }
}

const handleDisable = async () => {
  if (!confirm('Отключить двухфакторную аутентификацию? Это снизит безопасность аккаунта.')) {
    return
  }
  const code = prompt('Введите текущий 6-значный код из приложения-аутентификатора, чтобы подтвердить отключение MFA.')?.trim()
  if (!code || !/^\d{6}$/.test(code)) {
    toast.apiError(null as any, 'Нужен действующий 6-значный код для подтверждения')
    return
  }
  disabling.value = true
  try {
    await api.disableMfa({ code })
    toast.success('MFA отключена')
    await loadStatus()
  } catch (err) {
    toast.apiError(err as any, 'Не удалось отключить MFA')
  } finally {
    disabling.value = false
  }
}

const handleRegenerate = async () => {
  if (!confirm('Перегенерировать backup-коды? Старые коды перестанут работать.')) {
    return
  }
  regenerating.value = true
  try {
    const res = await api.regenerateMfaBackupCodes()
    regeneratedCodes.value = res.backupCodes
    await loadStatus()
  } catch (err) {
    toast.apiError(err as any, 'Не удалось сгенерировать новые коды')
  } finally {
    regenerating.value = false
  }
}

const downloadCodes = (codes: string[]) => {
  if (!process.client) return
  const blob = new Blob([codes.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'carcraft-backup-codes.txt'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

onMounted(loadStatus)
</script>
