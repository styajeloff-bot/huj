<template>
  <Modal
    :show="show"
    :title="title"
    size="lg"
    :closable="!loading && !isCodeSubmitBusy"
    :close-on-overlay="false"
    :show-footer="false"
    @close="emit('close')"
  >
    <div data-storefront-block="client.auth" class="space-y-5">
      <div v-if="step !== 'success'" class="space-y-4">
        <p class="text-sm text-[color:var(--storefront-text,#374151)]">
          {{ introText }}
        </p>

        <div class="grid grid-cols-1 gap-3 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4 sm:grid-cols-2">
          <div>
            <div class="text-xs font-medium uppercase text-[color:var(--storefront-text-muted,#6b7280)]">Телефон</div>
            <div class="mt-1 text-sm font-medium text-[color:var(--storefront-text,#111827)]">
              {{ displayPhone }}
            </div>
          </div>
          <div>
            <div class="text-xs font-medium uppercase text-[color:var(--storefront-text-muted,#6b7280)]">Дата рождения</div>
            <div class="mt-1 text-sm font-medium text-[color:var(--storefront-text,#111827)]">
              {{ displayBirthDate }}
            </div>
          </div>
        </div>

        <div class="rounded-lg border border-[color:var(--storefront-border,#dbeafe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4">
          <div class="text-sm font-medium text-[color:var(--storefront-text,#1e3a8a)]">
            Как это работает
          </div>
          <ol class="mt-2 space-y-1 text-sm text-[color:var(--storefront-text,#1e40af)]">
            <li>1. Мы отправим запрос оператору Mobile ID.</li>
            <li>2. На ваш номер придёт SMS с 4-значным кодом.</li>
            <li>3. После ввода кода профиль получит статус верификации.</li>
          </ol>
        </div>
      </div>

      <div v-if="step === 'intro'" class="space-y-4">
        <p v-if="userError" class="rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] p-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
          {{ userError }}
        </p>

        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading"
            @click="emit('close')"
          >
            Отмена
          </button>
          <button
            type="button"
            class="btn-primary inline-flex items-center justify-center"
            :disabled="loading"
            @click="onStart"
          >
            <span v-if="loading" class="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-b-2 border-[color:var(--storefront-primary-border,#ffffff)]"></span>
            {{ loading ? 'Запускаем…' : primaryText }}
          </button>
        </div>
      </div>

      <div v-else-if="step === 'code'" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#111827)]">
            Код из SMS
          </label>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Введите 4 цифры, отправленные на {{ displayPhone }}.
          </p>
        </div>

        <div class="flex justify-center gap-3">
          <input
            v-for="(_, index) in codeDigits"
            :key="index"
            :ref="(el) => setCodeInputRef(el, index)"
            v-model="codeDigits[index]"
            type="text"
            inputmode="numeric"
            maxlength="1"
            :disabled="isCodeSubmitBusy"
            class="storefront-control h-12 w-12 rounded-lg border-2 border-[color:var(--storefront-border,#d1d5db)] text-center text-xl font-semibold transition-all focus:border-[color:var(--storefront-border,#3b82f6)] focus:ring-2 focus:ring-[color:var(--storefront-focus,#bfdbfe)] sm:h-14 sm:w-14 sm:text-2xl"
            @input="onCodeInput(index)"
            @keydown.backspace="onCodeBackspace(index)"
            @keydown.enter.prevent="onSubmitCode"
            @paste="onCodePaste"
          >
        </div>

        <p v-if="userError" class="text-center text-sm text-[color:var(--storefront-error-text,#dc2626)]">
          {{ userError }}
        </p>

        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
          <button
            type="button"
            class="btn-secondary"
            :disabled="loading || isCodeSubmitBusy"
            @click="onRestart"
          >
            {{ loading ? 'Отправляем…' : 'Отправить код заново' }}
          </button>
          <button
            type="button"
            class="btn-primary inline-flex items-center justify-center"
            :disabled="!isCodeComplete || isCodeSubmitBusy"
            @click="onSubmitCode"
          >
            <span v-if="isCodeSubmitBusy" class="mr-2 inline-block h-4 w-4 animate-spin rounded-full border-b-2 border-[color:var(--storefront-primary-border,#ffffff)]"></span>
            {{ isCodeSubmitBusy ? 'Проверяем…' : 'Подтвердить' }}
          </button>
        </div>
      </div>

      <div v-else class="space-y-5 text-center">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#15803d)]">
          <svg class="text-[color:var(--storefront-icon,inherit)] h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <div>
          <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">Верификация пройдена</h4>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Теперь можно продолжить работу с профилем и подписанием документов.
          </p>
        </div>
        <button type="button" class="btn-primary" @click="emit('close')">
          Готово
        </button>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import type { ComponentPublicInstance } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useIdentityVerification } from '~/features/identity-verification/composables/useIdentityVerification'

const props = withDefaults(defineProps<{
  show: boolean
  phone?: string | null
  birthDate?: string | null
  title?: string
  introText?: string
  primaryText?: string
}>(), {
  phone: null,
  birthDate: null,
  title: 'Верификация через Mobile ID',
  introText: 'Мы подтвердим ваши данные через Mobile ID. Это займёт пару минут и поможет безопасно подписывать документы.',
  primaryText: 'Начать верификацию',
})

const emit = defineEmits<{
  close: []
  verified: []
}>()

const {
  loading,
  submittingCode,
  currentStatus,
  userError,
  clearError,
  refreshStatus,
  startVerification,
  submitSmsCode,
} = useIdentityVerification()

const step = ref<'intro' | 'code' | 'success'>('intro')
const codeDigits = ref(['', '', '', ''])
const codeInputs = ref<HTMLInputElement[]>([])
const codeSubmitLocked = ref(false)

const displayPhone = computed(() =>
  currentStatus.value?.phone_masked || props.phone || 'Не указан',
)

const displayBirthDate = computed(() => formatDate(props.birthDate))

const isCodeComplete = computed(() => codeDigits.value.every((digit) => /^\d$/.test(digit)))
const isCodeSubmitBusy = computed(() => submittingCode.value || codeSubmitLocked.value)

const resetCode = () => {
  codeDigits.value = ['', '', '', '']
}

const reset = () => {
  step.value = 'intro'
  codeSubmitLocked.value = false
  resetCode()
  clearError()
}

const focusFirstInput = async () => {
  await nextTick()
  codeInputs.value[0]?.focus()
}

const showFinalStatusError = (status?: {
  status?: string | null
  failure_message?: string | null
}) => {
  const message = status?.failure_message?.trim()
  if (message) {
    userError.value = message
    return
  }
  if (status?.status === 'expired') {
    userError.value = 'Срок действия проверки истёк. Запустите верификацию заново.'
    return
  }
  if (status?.status === 'failed') {
    userError.value = 'Верификация не пройдена. Попробуйте пройти её заново.'
    return
  }
  userError.value = 'Не удалось получить итоговый статус Mobile ID. Попробуйте ещё раз.'
}

const showRestartError = () => {
  userError.value = 'Не удалось отправить новый SMS-код через Mobile ID. Если SMS уже пришла, введите уже полученный код или попробуйте отправить новый код позже.'
}

const waitForVerificationResult = async () => {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await new Promise(resolve => setTimeout(resolve, 1500))
    const status = await refreshStatus()
    if (status.verified || status.status === 'verified') {
      step.value = 'success'
      emit('verified')
      return true
    }
    if (status.status === 'failed' || status.status === 'expired') {
      showFinalStatusError(status)
      return false
    }
  }
  showFinalStatusError()
  return false
}

const onStart = async () => {
  try {
    const response = await startVerification({
      birth_date: props.birthDate || undefined,
    })

    if (response.status === 'verified') {
      step.value = 'success'
      emit('verified')
      return
    }

    step.value = 'code'
    resetCode()
    await focusFirstInput()
  } catch {
    // User-facing error is owned by the composable.
  }
}

const onRestart = async () => {
  if (loading.value || isCodeSubmitBusy.value) return

  try {
    const response = await startVerification({
      birth_date: props.birthDate || undefined,
    })

    if (response.status === 'verified') {
      step.value = 'success'
      emit('verified')
      return
    }

    step.value = 'code'
    resetCode()
    await focusFirstInput()
  } catch {
    step.value = 'code'
    showRestartError()
    await focusFirstInput()
  }
}

const onSubmitCode = async () => {
  if (!isCodeComplete.value || submittingCode.value || codeSubmitLocked.value) return
  codeSubmitLocked.value = true

  try {
    const response = await submitSmsCode(codeDigits.value.join(''))
    if (response.verified || response.status === 'verified') {
      step.value = 'success'
      emit('verified')
      return
    }

    if (await waitForVerificationResult()) {
      return
    }

    codeSubmitLocked.value = false
    resetCode()
    await focusFirstInput()

    if (response.status === 'expired') {
      return
    }
  } catch {
    codeSubmitLocked.value = false
    resetCode()
    await focusFirstInput()
  } finally {
    if (step.value !== 'success') {
      codeSubmitLocked.value = false
    }
  }
}

const setCodeInputRef = (
  el: Element | ComponentPublicInstance | null,
  index: number,
) => {
  if (el instanceof HTMLInputElement) {
    codeInputs.value[index] = el
  }
}

const onCodeInput = async (index: number) => {
  const digit = codeDigits.value[index]
  if (!/^\d?$/.test(digit)) {
    codeDigits.value[index] = ''
    return
  }

  clearError()
  if (digit && index < 3) {
    await nextTick()
    codeInputs.value[index + 1]?.focus()
  }
}

const onCodeBackspace = async (index: number) => {
  if (!codeDigits.value[index] && index > 0) {
    codeDigits.value[index - 1] = ''
    await nextTick()
    codeInputs.value[index - 1]?.focus()
  }
}

const onCodePaste = async (event: ClipboardEvent) => {
  event.preventDefault()
  const digits = (event.clipboardData?.getData('text') || '')
    .replace(/\D/g, '')
    .slice(0, 4)

  digits.split('').forEach((digit, index) => {
    codeDigits.value[index] = digit
  })

  await nextTick()
  codeInputs.value[Math.min(digits.length, 3)]?.focus()
}

const formatDate = (value?: string | null) => {
  if (!value) return 'Не указана'
  try {
    return new Date(value).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    })
  } catch {
    return value
  }
}

watch(() => props.show, (isShown) => {
  if (isShown) {
    reset()
  }
})
</script>
