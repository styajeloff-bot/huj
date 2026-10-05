<template>
  <div data-storefront-block="client.order" class="sbp-payment">
    <!-- Name input (if missing) -->
    <div v-if="showNameForm" class="name-form">
      <p class="name-form-title">Для оплаты через СБП укажите ФИО</p>
      <input v-model="nameInput" type="text" placeholder="Иванов Иван Иванович"
        class="storefront-control name-input" @keyup.enter="saveName" />
      <p class="name-hint">Для формирования платежных документов</p>
      <button type="button" class="storefront-action-ghost name-save-btn" :disabled="!nameInput.trim() || savingName" @click="saveName">
        <span v-if="savingName" class="spinner-sm" />
        <span v-else>Продолжить</span>
      </button>
      <p v-if="nameError" class="name-error">{{ nameError }}</p>
    </div>

    <!-- Waiting / QR + Link -->
    <div v-else-if="paymentStatus === 'waiting'" class="sbp-waiting">
      <div class="qr-block">
        <img v-if="qrDataUrl" :src="qrDataUrl" alt="QR for SBP payment" class="qr-image" />
        <div v-else class="qr-placeholder">
          <div class="spinner" />
        </div>
      </div>

      <div class="sbp-info">
        <p class="amount">{{ formatPrice(sbpData.amount) }} &#8381;</p>
        <p class="hint">
          Отсканируйте QR-код в приложении банка<br />или нажмите кнопку ниже
        </p>
      </div>

      <a :href="sbpData.sbpLink" class="sbp-open-btn" target="_blank" rel="noopener">
        Открыть в приложении банка
      </a>

      <button type="button" class="storefront-action-ghost sbp-check-btn" @click="startPolling">
        Я оплатил
      </button>

      <p class="expires" v-if="sbpData.expiresAt">
        Оплатите в течение {{ remainingMinutes }} мин
      </p>
    </div>

    <!-- Polling -->
    <div v-else-if="paymentStatus === 'polling'" class="polling-status">
      <div class="spinner" />
      <p>Проверяем статус оплаты...</p>
    </div>

    <!-- Success -->
    <div v-else-if="paymentStatus === 'completed'" class="success-status">
      <span class="icon">&#10003;</span>
      <p>Оплата прошла успешно!</p>
    </div>

    <!-- Failed -->
    <div v-else-if="paymentStatus === 'failed'" class="error-status">
      <span class="icon">&#10007;</span>
      <p>Оплата не прошла</p>
      <p class="error-message" v-if="errorMessage">{{ errorMessage }}</p>
      <button class="storefront-action-ghost retry-btn" @click="$emit('retry')">Попробовать снова</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import type { UUID } from '~/types/ids'
const props = defineProps<{
  sbpData: {
    sbpLink: string
    amount: number
    expiresAt?: string
  }
  paymentId: UUID
}>()

const emit = defineEmits<{
  completed: []
  failed: []
  retry: []
}>()

const purchasesStore = usePurchasesStore()
const authStore = useAuthStore()
const config = useRuntimeConfig()

const paymentStatus = ref<'waiting' | 'polling' | 'completed' | 'failed'>('waiting')
const errorMessage = ref('')
const qrDataUrl = ref('')
const remainingMinutes = ref(30)

// Name form
const nameInput = ref('')
const savingName = ref(false)
const nameError = ref('')
const nameSaved = ref(false)

const showNameForm = computed(() =>
  !authStore.user?.name && !nameSaved.value && paymentStatus.value === 'waiting'
)

async function saveName() {
  if (!nameInput.value.trim()) return
  savingName.value = true
  nameError.value = ''
  try {
    await $fetch('/api/v1/users/me', {
      method: 'PATCH',
      body: { name: nameInput.value.trim() },
      baseURL: config.public.apiBase,
      credentials: 'include',
    })
    await authStore.checkAuth()
    nameSaved.value = true
  } catch {
    nameError.value = 'Не удалось сохранить ФИО'
  } finally {
    savingName.value = false
  }
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value)
}

function updateRemainingTime() {
  if (!props.sbpData.expiresAt) return
  const diff = new Date(props.sbpData.expiresAt).getTime() - Date.now()
  remainingMinutes.value = Math.max(0, Math.ceil(diff / 60000))
  if (remainingMinutes.value <= 0) {
    paymentStatus.value = 'failed'
    errorMessage.value = 'Время на оплату истекло'
    emit('failed')
  }
}

async function generateQr() {
  if (!import.meta.client) return
  try {
    const QRCode = (await import('qrcode')).default
    qrDataUrl.value = await QRCode.toDataURL(props.sbpData.sbpLink, {
      width: 220,
      margin: 2,
      errorCorrectionLevel: 'M',
    })
  } catch (e) {
    console.error('QR generation error:', e)
  }
}

async function startPolling() {
  paymentStatus.value = 'polling'
  const result = await purchasesStore.pollPaymentStatus(props.paymentId)
  if (result.status === 'completed') {
    paymentStatus.value = 'completed'
    emit('completed')
  } else {
    paymentStatus.value = 'failed'
    errorMessage.value = result.status === 'timeout' ? 'Время ожидания истекло' : 'Оплата не прошла'
    emit('failed')
  }
}

// Auto-start polling when user returns from banking app
function handleVisibilityChange() {
  if (!document.hidden && paymentStatus.value === 'waiting') {
    setTimeout(() => {
      if (paymentStatus.value === 'waiting') {
        startPolling()
      }
    }, 2000)
  }
}

onMounted(() => {
  generateQr()
  updateRemainingTime()
  const timer = setInterval(updateRemainingTime, 30000)
  document.addEventListener('visibilitychange', handleVisibilityChange)

  onUnmounted(() => {
    clearInterval(timer)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  })
})

defineExpose({ startPolling })
</script>

<style scoped>
.sbp-payment {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 20px;
}

.name-form {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: 100%;
  max-width: 360px;
}

.name-form-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--storefront-title,#1a1a1a);
  text-align: center;
}

.name-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid var(--storefront-border,#d1d5db);
  border-radius: 12px;
  font-size: 15px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.name-input:focus {
  border-color: var(--storefront-primary,#3b82f6);
  box-shadow: 0 0 0 3px rgb(var(--storefront-shadow-rgb,59 130 246) / 0.15);
}

.name-hint {
  font-size: 12px;
  color: var(--storefront-text-muted,#888);
}

.name-save-btn {
  width: 100%;
  padding: 12px 24px;
  background: linear-gradient(135deg, var(--storefront-gradient-from,#22c55e), var(--storefront-gradient-to,#3b82f6));
  color: var(--storefront-text,#fff);
  border: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.name-save-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.name-error {
  color: var(--storefront-error-text,#ef4444);
  font-size: 13px;
}

.sbp-waiting {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.qr-block {
  width: 220px;
  height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--storefront-border,#e5e7eb);
  border-radius: 16px;
  overflow: hidden;
  background: var(--storefront-surface,#fff);
}

.qr-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.qr-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.sbp-info {
  text-align: center;
}

.sbp-info .amount {
  font-size: 24px;
  font-weight: 700;
  color: var(--storefront-price,#1a1a1a);
}

.sbp-info .hint {
  font-size: 13px;
  color: var(--storefront-text-muted,#888);
  margin-top: 4px;
  line-height: 1.5;
}

.sbp-open-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  max-width: 320px;
  padding: 12px 24px;
  background: linear-gradient(135deg, var(--storefront-gradient-from,#22c55e), var(--storefront-gradient-to,#3b82f6));
  color: var(--storefront-text,#fff);
  border: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  text-decoration: none;
  cursor: pointer;
  transition: opacity 0.2s;
}

.sbp-open-btn:hover {
  opacity: 0.9;
}

.sbp-check-btn {
  padding: 10px 24px;
  background: transparent;
  color: var(--storefront-link,#4971d0);
  border: 1px solid var(--storefront-primary,#4971d0);
  border-radius: 10px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.2s;
}

.sbp-check-btn:hover {
  background: var(--storefront-surface,#f0f4ff);
}

.expires {
  font-size: 13px;
  color: var(--storefront-text,#888);
}

.polling-status,
.success-status,
.error-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px 20px;
  text-align: center;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid var(--storefront-spinner,#e0e0e0);
  border-top-color: var(--storefront-spinner,#4971d0);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner-sm {
  width: 18px;
  height: 18px;
  border: 2px solid rgb(var(--storefront-spinner-rgb,255 255 255) / 0.4);
  border-top-color: var(--storefront-spinner,#fff);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.success-status .icon {
  font-size: 48px;
  color: var(--storefront-success-text,#22c55e);
}

.error-status .icon {
  font-size: 48px;
  color: var(--storefront-error-text,#ef4444);
}

.error-message {
  color: var(--storefront-text,#666);
  font-size: 14px;
}

.retry-btn {
  padding: 10px 24px;
  background: var(--storefront-primary,#4971d0);
  color: var(--storefront-text,#fff);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
}

.retry-btn:hover {
  background: var(--storefront-primary-hover,#3a5cb8);
}
</style>
