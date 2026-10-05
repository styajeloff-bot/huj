<template>
  <Modal 
    :show="true" 
    @close="$emit('close')"
    size="lg"
    :show-footer="false"
    :show-header="false"
  >
    <div data-storefront-block="client.auth" class="flex items-center justify-between pb-4">
      <div class="flex items-center gap-2">
        <button
          v-if="activeStep !== 'login' && !activeStep.startsWith('mfa-setup-')"
          type="button"
          @click="goBack"
          class="text-[color:var(--storefront-ghost-foreground,#6b7280)] hover:text-[color:var(--storefront-ghost-hover-foreground,#374151)] transition-colors"
          aria-label="Назад"
        >
          <svg class="text-[color:var(--storefront-icon,inherit)] h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M12.707 15.707a1 1 0 01-1.414 0l-5-5a1 1 0 010-1.414l5-5a1 1 0 111.414 1.414L8.414 10l4.293 4.293a1 1 0 010 1.414z" clip-rule="evenodd" />
          </svg>
        </button>
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
          {{ modalTitle }}
        </h3>
      </div>
      <button
        type="button"
        @click="$emit('close')"
        class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] transition-colors"
        aria-label="Закрыть"
      >
        <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <div
      data-storefront-block="client.auth"
      v-if="isPhoneAlreadyRegistered"
      class="mb-4 p-3 rounded text-sm border bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)]"
    >
      <div>Введеный номер уже зарегистрирован на платформе</div>
      <button
        type="button"
        @click="openLoginForRegisteredPhone"
        class="mt-2.5 btn-primary text-xs !py-1.5 !px-3 shadow-sm inline-flex items-center"
      >
        Войти
      </button>
    </div>

    <div data-storefront-block="client.auth"
      v-else-if="error"
      :class="[
        'mb-4 p-3 rounded text-sm border',
        isVerificationCodeSentMessage
          ? 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-success-border,#4ade80)] text-[color:var(--storefront-success-text,#15803d)] text-center'
          : 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)]'
      ]"
    >
      {{ error }}
    </div>

    <Transition name="slide" mode="out-in">
      <div data-storefront-block="client.auth" v-if="activeStep === 'mfa-setup-qr'" :key="activeStep" class="space-y-4">
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Для вашей роли двухфакторная аутентификация обязательна.
          Отсканируйте QR-код в приложении-аутентификаторе и введите 6-значный код, чтобы завершить настройку.
        </p>

        <div v-if="mfaSetupLoading" class="text-center py-8">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
          <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Готовим QR-код...</p>
        </div>

        <div v-else-if="mfaSetupData" class="space-y-4">
          <div class="flex justify-center">
            <img
              :src="`data:image/png;base64,${mfaSetupData.qrPngBase64}`"
              alt="MFA QR"
              class="w-56 h-56 border rounded-md p-2 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]"
            >
          </div>
          <div>
            <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] mb-1">
              Или введите секрет вручную:
            </div>
            <div class="font-mono text-sm bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] rounded px-3 py-2 break-all">
              {{ mfaSetupData.secret }}
            </div>
          </div>
          <form class="space-y-3" @submit.prevent="completeMfaSetup">
            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1" for="mfaSetupCode">
                Код из приложения
              </label>
              <input
                id="mfaSetupCode"
                v-model="mfaSetupCode"
                inputmode="numeric"
                maxlength="6"
                required
                placeholder="000000"
                class="storefront-control input-field text-center text-lg tracking-widest font-mono"
                @input="sanitizeMfaCode"
              >
            </div>
            <p v-if="mfaSetupError" class="text-sm text-[color:var(--storefront-error-text,#dc2626)]">
              {{ mfaSetupError }}
            </p>
            <button
              type="submit"
              :disabled="mfaSetupSubmitting || mfaSetupCode.length !== 6"
              class="w-full btn-primary disabled:opacity-50"
            >
              {{ mfaSetupSubmitting ? 'Проверяем...' : 'Завершить настройку' }}
            </button>
          </form>
        </div>

        <div v-else class="text-center py-8 text-[color:var(--storefront-text-muted,#4b5563)]">
          {{ mfaSetupError || 'Не удалось начать настройку. Возможно, сессия истекла.' }}
        </div>
      </div>

      <div data-storefront-block="client.auth" v-else-if="activeStep === 'mfa-setup-backup'" :key="activeStep" class="space-y-4">
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Эти одноразовые коды позволят войти без приложения. Показываются только один раз — сохраните их.
        </p>
        <div class="grid grid-cols-2 gap-2 font-mono text-sm">
          <div
            v-for="bc in mfaBackupCodes"
            :key="bc"
            class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border rounded px-3 py-2 text-center"
          >
            {{ bc }}
          </div>
        </div>
        <div class="flex gap-3">
          <button class="btn-secondary" @click="downloadBackupCodes">
            Скачать .txt
          </button>
          <button class="btn-primary flex-1" @click="finishMfaSetup">
            Я сохранил коды
          </button>
        </div>
      </div>

      <form data-storefront-block="client.auth" v-else :key="activeStep" @submit.prevent="handleSubmit">
        <div class="space-y-4">
          <div v-if="activeStep === 'verify-phone'" class="text-center">
            <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] mb-4">
              <svg class="h-6 w-6 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"></path>
              </svg>
            </div>
            <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-2">
              Мы отправили код подтверждения на номер
            </p>
            <p class="text-sm font-medium text-[color:var(--storefront-text,#111827)] mb-4">
              {{ pendingVerificationPhone }}
            </p>
            <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              Введите 4-значный код из SMS
            </p>
          </div>

          <div v-if="activeStep === 'verify-phone' && verificationError" class="mb-4 p-3 bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#f87171)] text-[color:var(--storefront-error-text,#b91c1c)] rounded text-sm">
            {{ verificationError }}
          </div>

          <div v-if="activeStep === 'verify-phone' && verificationSuccess" class="mb-4 p-3 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-success-border,#4ade80)] text-[color:var(--storefront-success-text,#15803d)] rounded text-sm">
            {{ verificationSuccess }}
          </div>

          <div v-if="activeStep === 'login' || activeStep === 'register'">
            <label for="phone" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Номер телефона <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span></label>
            <input
              id="phone"
              v-model="form.phone"
              type="tel"
              required
              class="storefront-control input-field mt-1"
              placeholder="+7 (___) ___-__-__"
              @input="formatPhone"
              @keydown.backspace="handlePhoneBackspace"
              maxlength="18"
            >
          </div>

          <div v-if="activeStep === 'register-code'" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Номер телефона: <span class="font-medium text-[color:var(--storefront-text,#111827)]">{{ registrationPhone }}</span>
          </div>

          <div v-if="activeStep === 'verify-phone'">
            <label for="verificationCode" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
              Код подтверждения
            </label>
            <input
              id="verificationCode"
              v-model="verificationCode"
              type="text"
              maxlength="4"
              required
              class="storefront-control input-field text-center text-lg tracking-widest font-mono"
              placeholder="0000"
              @input="formatVerificationCode"
              @keypress="onlyNumbers"
            >
            <div class="mt-3 text-sm text-[color:var(--storefront-text-muted,#4b5563)] flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span v-if="verificationCountdown > 0">Повтор через {{ verificationCountdown }}с</span>
                <button
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)]"
                  :disabled="verificationResendLoading || verificationCountdown > 0"
                  @click="handleResendVerificationCode"
                >
                  {{ verificationResendLoading ? 'Отправка...' : 'Отправить код снова' }}
                </button>
              </div>
              <div
                role="button"
                tabindex="0"
                class="cursor-pointer storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
                @click="startRegisterCompanyForExistingUser"
                @keydown.enter="startRegisterCompanyForExistingUser"
              >
                Зарегистрировать новую компанию
              </div>
            </div>
          </div>

          <template v-if="activeStep === 'register' || activeStep === 'register-code'">
            <div v-if="activeStep === 'register-code'">
              <label for="registrationCode" class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">
                Код из SMS <span class="text-[color:var(--storefront-error-text,#ef4444)]">*</span>
              </label>
              <input
                id="registrationCode"
                v-model="form.code"
                type="text"
                required
                class="storefront-control input-field mt-1"
                placeholder="Введите код из SMS"
                maxlength="4"
                @input="formatCode"
                @keypress="onlyNumbers"
              >
              <div class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)] flex items-center justify-between">
                <span v-if="resendCountdown > 0">Повтор через {{ resendCountdown }}с</span>
                <button
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)]"
                  :disabled="resendLoading || resendCountdown > 0"
                  @click="handleResendRegistrationCode"
                >
                  {{ resendLoading ? 'Отправка...' : 'Отправить код снова' }}
                </button>
              </div>
            </div>
            <div class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-3">
              <div class="flex items-center gap-2 mb-2">
                <svg class="w-4 h-4 text-[color:var(--storefront-icon,#9ca3af)] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-2 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                <span class="text-sm font-medium text-[color:var(--storefront-text,#374151)]">Компания</span>
                <span class="ml-auto text-xs font-medium text-[color:var(--storefront-text,#1d4ed8)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)] rounded px-1.5 py-0.5">Только для юрлиц</span>
              </div>
              <div
                v-for="(entry, index) in form.companies"
                :key="index"
                class="flex gap-2 items-start"
                :class="{ 'mb-2': index < form.companies.length - 1 }"
              >
                <div class="flex-1 min-w-0">
                  <CompanyAutocomplete
                    v-model="form.companies[index]"
                    placeholder="Название компании или ИНН"
                    @validation="(valid: unknown) => onCompanyValidation(index, valid)"
                    @select="(obj: unknown) => onCompanySelect(index, obj)"
                  />
                </div>
                <button
                  v-if="form.companies.length > 1"
                  type="button"
                  aria-label="Удалить компанию"
                  class="storefront-action-ghost p-2 text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#ef4444)] shrink-0"
                  @click="removeCompany(index)"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <button
                type="button"
                class="storefront-action-ghost mt-2 text-xs text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
                @click="addCompany"
              >
                + Добавить ещё компанию
              </button>
            </div>

            <div class="space-y-2">
              <label class="flex items-start gap-2 text-sm text-[color:var(--storefront-label,#374151)]">
                <input
                  v-model="form.agreePrivacy"
                  type="checkbox"
                  class="storefront-control mt-0.5 h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
                <span>
                  Я соглашаюсь с
                  <nuxt-link to="/pdp-policy/" target="_blank" rel="noopener noreferrer" class="text-[color:var(--storefront-text-muted,#2563eb)] hover:text-[color:var(--storefront-text,#1e40af)]">
                    Политикой конфиденциальности
                  </nuxt-link>
                </span>
              </label>
              <label class="flex items-start gap-2 text-sm text-[color:var(--storefront-label,#374151)]">
                <input
                  v-model="form.agreeTerms"
                  type="checkbox"
                  class="storefront-control mt-0.5 h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
                <span>
                  Я соглашаюсь с
                  <nuxt-link to="/terms-of-service" target="_blank" rel="noopener noreferrer" class="text-[color:var(--storefront-text-muted,#2563eb)] hover:text-[color:var(--storefront-text,#1e40af)]">
                    Пользовательским соглашением
                  </nuxt-link>
                </span>
              </label>
            </div>
          </template>
        </div>

        <div class="mt-6 flex items-center justify-end">
          <button
            v-if="activeStep === 'login'"
            type="button"
            @click="startManualRegistration"
            class="text-sm text-[color:var(--storefront-selected-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
          >
            Нет аккаунта? Зарегистрироваться
          </button>
          <button
            v-else-if="activeStep === 'register' || activeStep === 'register-code'"
            type="button"
            @click="switchToLogin"
            class="text-sm text-[color:var(--storefront-selected-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
          >
            Уже есть аккаунт? Войти
          </button>
        </div>

        <div class="mt-4">
          <button
            type="submit"
            :disabled="loading"
            class="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ loading ? 'Загрузка...' : actionLabel }}
          </button>
        </div>
      </form>
    </Transition>

  </Modal>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { useAuthStore } from '~/features/auth/store/auth'
import { createAuthApi, type MfaSetupResponse } from '~/features/auth/api/authApi'
import { deletePreviousPhoneDigit, formatRussianPhone } from '~/features/auth/phoneMask'
import CompanyAutocomplete from '~/components/ui/CompanyAutocomplete.vue'

const props = withDefaults(defineProps<{
  initialStep?: 'login' | 'register'
  redirectToAccount?: boolean
}>(), {
  initialStep: 'login',
  redirectToAccount: false,
})

type AuthStep = 'login' | 'register' | 'register-code' | 'verify-phone' | 'mfa-setup-qr' | 'mfa-setup-backup'

const emit = defineEmits(['close', 'authenticated'])
const authStore = useAuthStore()
const config = useRuntimeConfig()
const authApi = createAuthApi(config)
const { publicRoute } = useStorefront()

let disposed = false
let authenticationTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => {
  disposed = true
  if (authenticationTimer) clearTimeout(authenticationTimer)
})

const continueWithMfa = () => {
  const destination = props.redirectToAccount
    ? { path: publicRoute('/auth/mfa-verify'), query: { account: '1' } }
    : publicRoute('/auth/mfa-verify')
  emit('close')
  navigateTo(destination)
}

const loading = ref(false)
const error = ref('')
const isPhoneAlreadyRegistered = ref(false)
const companyValidities = ref<Record<number, boolean>>({})
const pendingVerificationPhone = ref('')
const verificationCodeAlreadySent = ref(false)
const activeStep = ref<AuthStep>(props.initialStep)

// --- MFA setup state (lifted in from /auth/mfa-setup-required so the
// flow stays inside the same modal instead of bouncing the user to a
// dedicated page after login).
const mfaSetupLoading = ref(false)
const mfaSetupSubmitting = ref(false)
const mfaSetupError = ref('')
const mfaSetupData = ref<MfaSetupResponse | null>(null)
const mfaSetupCode = ref('')
const mfaBackupCodes = ref<string[]>([])
const registrationPhone = ref('')
const registrationCodeAlreadySent = ref(false)
const resendLoading = ref(false)
const resendCountdown = ref(0)
const verificationCode = ref('')
const verificationLoading = ref(false)
const verificationResendLoading = ref(false)
const verificationError = ref('')
const verificationSuccess = ref('')
const verificationCountdown = ref(0)
const previousStep = ref<AuthStep>('login')

const isVerificationCodeSentMessage = computed(
  () => error.value === 'Код подтверждения отправлен на ваш телефон'
)

const form = ref({
  phone: '',
  companies: [''],
  code: '',
  agreePrivacy: false,
  agreeTerms: false
})

const companiesValid = computed(() => form.value.companies.every((value: string, index: number) => {
  if (!value.trim()) return true
  return companyValidities.value[index] === true
}))

const setCompanyValid = (index: number, valid: unknown) => {
  companyValidities.value = { ...companyValidities.value, [index]: Boolean(valid) }
}

const onCompanyValidation = (index: number, valid: unknown) => setCompanyValid(index, valid)

interface CompanyObject {
  name: string
  inn: string
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  actual_address?: string | null
  phone?: string | null
  email?: string | null
  manager_name?: string | null
  entity_type?: string | null
  [key: string]: unknown
}

const companyObjects = ref<Record<number, CompanyObject>>({})
const setCompanyObject = (index: number, obj: unknown) => {
  companyObjects.value = { ...companyObjects.value, [index]: obj as CompanyObject }
}

const onCompanySelect = (index: number, obj: unknown) => setCompanyObject(index, obj)

const addCompany = () => {
  form.value.companies.push('')
}

const removeCompany = (index: number) => {
  form.value.companies.splice(index, 1)
  const shiftMap = <T>(m: Record<number, T>): Record<number, T> => {
    const next: Record<number, T> = {}
    Object.entries(m).forEach(([k, v]) => {
      const ki = parseInt(k, 10)
      if (ki < index) next[ki] = v
      else if (ki > index) next[ki - 1] = v
    })
    return next
  }
  companyValidities.value = shiftMap(companyValidities.value)
  companyObjects.value = shiftMap(companyObjects.value)
}

const formatPhone = (event: Event) => {
  form.value.phone = formatRussianPhone((event.target as HTMLInputElement).value)
  error.value = ''
  isPhoneAlreadyRegistered.value = false
}

const handlePhoneBackspace = async (event: KeyboardEvent) => {
  const input = event.currentTarget as HTMLInputElement
  const cursor = input.selectionStart

  if (cursor === null || input.selectionStart !== input.selectionEnd) return

  event.preventDefault()
  const nextPhone = deletePreviousPhoneDigit({ value: form.value.phone, cursor })
  form.value.phone = nextPhone.value
  error.value = ''
  isPhoneAlreadyRegistered.value = false

  await nextTick()
  input.setSelectionRange(nextPhone.cursor, nextPhone.cursor)
}

const validatePhone = () => {
  const phoneDigits = form.value.phone.replace(/\D/g, '')
  return phoneDigits.length === 11 && phoneDigits.startsWith('7')
}

const formatCode = () => {
  form.value.code = form.value.code.replace(/\D/g, '').slice(0, 4)
}

const onlyNumbers = (event: KeyboardEvent) => {
  if (!/[0-9]/.test(event.key)) {
    event.preventDefault()
  }
}

const formatVerificationCode = () => {
  verificationCode.value = verificationCode.value.replace(/\D/g, '').slice(0, 4)
}

const resetForm = (step: 'login' | 'register' = props.initialStep) => {
  error.value = ''
  isPhoneAlreadyRegistered.value = false
  activeStep.value = step
  registrationPhone.value = ''
  registrationCodeAlreadySent.value = false
  resendLoading.value = false
  resendCountdown.value = 0
  verificationCode.value = ''
  verificationLoading.value = false
  verificationResendLoading.value = false
  verificationError.value = ''
  verificationSuccess.value = ''
  verificationCountdown.value = 0
  verificationCodeAlreadySent.value = false
  pendingVerificationPhone.value = ''
  previousStep.value = 'login'
  form.value = {
    phone: '',
    companies: [''],
    code: '',
    agreePrivacy: false,
    agreeTerms: false
  }
  companyValidities.value = {}
  companyObjects.value = {}
}

const startManualRegistration = () => {
  error.value = ''
  isPhoneAlreadyRegistered.value = false
  activeStep.value = 'register'
}

const switchToLogin = () => {
  resetForm('login')
}

const openLoginForRegisteredPhone = () => {
  const currentPhone = form.value.phone
  resetForm('login')
  form.value.phone = currentPhone
}

const startRegisterCompanyForExistingUser = () => {
  registrationPhone.value = pendingVerificationPhone.value
  form.value.code = verificationCode.value
  resendCountdown.value = verificationCountdown.value
  if (resendCountdown.value > 0) {
    startResendCountdown(verificationCountdown.value)
  }
  previousStep.value = 'verify-phone'
  activeStep.value = 'register-code'
  error.value = ''
}

const goBack = () => {
  error.value = ''
  isPhoneAlreadyRegistered.value = false
  if (activeStep.value === 'verify-phone') {
    activeStep.value = previousStep.value || 'login'
    return
  }
  if (activeStep.value === 'register-code') {
    if (previousStep.value === 'verify-phone') {
      verificationCode.value = form.value.code
      activeStep.value = 'verify-phone'
      previousStep.value = 'login'
      return
    }
    activeStep.value = 'register'
    return
  }
  activeStep.value = 'login'
}

const startResendCountdown = (seconds = 60) => {
  resendCountdown.value = seconds
  const timer = setInterval(() => {
    resendCountdown.value--
    if (resendCountdown.value <= 0) {
      clearInterval(timer)
    }
  }, 1000)
}

const startVerificationCountdown = () => {
  verificationCountdown.value = 60
  const timer = setInterval(() => {
    verificationCountdown.value--
    if (verificationCountdown.value <= 0) {
      clearInterval(timer)
    }
  }, 1000)
}

const handleResendRegistrationCode = async () => {
  if (!registrationPhone.value) return
  resendLoading.value = true
  error.value = ''
  try {
    const result = await authStore.resendCode(registrationPhone.value)
    if (result.success) {
      startResendCountdown()
      form.value.code = ''
    } else {
      error.value = result.error
    }
  } catch (err) {
    error.value = 'Произошла ошибка. Попробуйте снова.'
  } finally {
    resendLoading.value = false
  }
}

const handleResendVerificationCode = async () => {
  if (!pendingVerificationPhone.value) return
  verificationResendLoading.value = true
  verificationError.value = ''
  try {
    const result = await authStore.resendCode(pendingVerificationPhone.value)
    if (result.success) {
      startVerificationCountdown()
      verificationCode.value = ''
    } else {
      verificationError.value = result.error
    }
  } catch (err) {
    verificationError.value = 'Произошла ошибка. Попробуйте снова.'
  } finally {
    verificationResendLoading.value = false
  }
}

const handleVerificationSubmit = async () => {
  if (verificationCode.value.length !== 4) {
    verificationError.value = 'Введите 4-значный код'
    return
  }

  verificationLoading.value = true
  verificationError.value = ''
  verificationSuccess.value = ''

  try {
    const result = await authStore.verifyPhone(pendingVerificationPhone.value, verificationCode.value)
    if (disposed) return
    if (result.success) {
      verificationSuccess.value = 'Телефон успешно подтвержден!'
      authenticationTimer = setTimeout(() => {
        if (disposed) return
        emit('authenticated')
        emit('close')
      }, 1200)
    } else if ((result as any).mfaRequired) {
      continueWithMfa()
    } else if ((result as any).mfaSetupRequired) {
      await beginMfaSetup()
    } else {
      verificationError.value = result.error
    }
  } catch (err) {
    verificationError.value = 'Произошла ошибка. Попробуйте снова.'
  } finally {
    verificationLoading.value = false
  }
}

const handleSubmit = async () => {
  loading.value = true
  error.value = ''
  isPhoneAlreadyRegistered.value = false

  if (activeStep.value === 'verify-phone') {
    loading.value = false
    await handleVerificationSubmit()
    return
  }

  if ((activeStep.value === 'login' || activeStep.value === 'register') && !validatePhone()) {
    error.value = 'Введите корректный номер телефона в формате +7 (___) ___-__-__'
    loading.value = false
    return
  }

  if ((activeStep.value === 'register' || activeStep.value === 'register-code') && !companiesValid.value) {
    error.value = 'Выберите компанию из списка или очистите поле'
    loading.value = false
    return
  }

  if ((activeStep.value === 'register' || activeStep.value === 'register-code') && (!form.value.agreePrivacy || !form.value.agreeTerms)) {
    error.value = 'Необходимо принять Политику конфиденциальности и Пользовательское соглашение'
    loading.value = false
    return
  }

  if (activeStep.value === 'register-code' && form.value.code.length !== 4) {
    error.value = 'Введите 4-значный код из SMS'
    loading.value = false
    return
  }

  const phoneDigits = form.value.phone.replace(/\D/g, '')
  const phoneFormatted = '+' + phoneDigits

  if (activeStep.value === 'register-code' && !registrationPhone.value) {
    error.value = 'Номер телефона не найден. Попробуйте снова.'
    loading.value = false
    return
  }

  try {
    const companiesPayload = (form.value.companies || [])
      .map((_: string, idx: number) => companyObjects.value[idx])
      .filter((c): c is CompanyObject => Boolean(c && c.inn))

    if (activeStep.value === 'register-code' && previousStep.value === 'verify-phone') {
      if (companiesPayload.length === 0) {
        error.value = 'Выберите хотя бы одну компанию'
        loading.value = false
        return
      }
    }
    const result: Record<string, unknown> = activeStep.value === 'login'
      ? await authStore.login({ phone: phoneFormatted }, { redirectAfterLogin: !props.redirectToAccount })
      : await authStore.register({
          phone: activeStep.value === 'register-code' ? registrationPhone.value : phoneFormatted,
          companies: companiesPayload.length > 0 ? companiesPayload : undefined,
          code: activeStep.value === 'register-code' ? form.value.code : undefined
        })

    if (disposed) return
    if (result.success) {
      emit('authenticated')
      emit('close')
    } else if (result.mfaRequired) {
      continueWithMfa()
    } else if (result.mfaSetupRequired) {
      await beginMfaSetup()
    } else if (result.requiresVerification) {
      pendingVerificationPhone.value = (result.phone as string) || phoneFormatted
      verificationCodeAlreadySent.value = (result.codeAlreadySent as boolean) || false
      previousStep.value = activeStep.value
      activeStep.value = 'verify-phone'
      verificationCode.value = ''
      if (verificationCodeAlreadySent.value) {
        startVerificationCountdown()
      }
      error.value = (result.message as string) || ''
    } else if (result.requiresRegistration) {
      registrationPhone.value = (result.phone as string) || phoneFormatted
      form.value.code = ''
      activeStep.value = 'register-code'
      if (result.codeAlreadySent) {
        startResendCountdown()
      }
    } else if (
      result.isAlreadyRegistered ||
      (typeof result.error === 'string' &&
        (result.error.includes('уже зарегистрирован') || result.error.includes('уже существует')))
    ) {
      isPhoneAlreadyRegistered.value = true
      error.value = 'Введеный номер уже зарегистрирован на платформе'
    } else {
      error.value = result.error as string
    }
  } catch (err) {
    error.value = 'Произошла ошибка. Попробуйте снова.'
    isPhoneAlreadyRegistered.value = false
  } finally {
    loading.value = false
  }
}

const modalTitle = computed(() => {
  if (activeStep.value === 'mfa-setup-qr') return 'Настройка двухфакторной аутентификации'
  if (activeStep.value === 'mfa-setup-backup') return 'Сохраните backup-коды'
  if (activeStep.value === 'login' || activeStep.value === 'verify-phone') return 'Вход в личный кабинет'
  return 'Регистрация'
})

const actionLabel = computed(() => {
  if (activeStep.value === 'login') return 'Получить код'
  if (activeStep.value === 'verify-phone') return 'Подтвердить'
  if (activeStep.value === 'register-code') return 'Зарегистрироваться'
  return 'Зарегистрироваться'
})

// --- MFA setup flow (in-modal replacement for /auth/mfa-setup-required).

const beginMfaSetup = async () => {
  const setupToken = authStore.mfaPending?.setupToken
  if (!setupToken) {
    error.value = 'Сессия истекла. Войдите заново.'
    return
  }
  activeStep.value = 'mfa-setup-qr'
  mfaSetupLoading.value = true
  mfaSetupError.value = ''
  mfaSetupCode.value = ''
  mfaSetupData.value = null
  try {
    mfaSetupData.value = await authApi.setupMfa({ setupToken })
  } catch (err: unknown) {
    mfaSetupError.value =
      (err as { data?: { error?: string } }).data?.error
      || 'Не удалось запустить настройку MFA'
  } finally {
    mfaSetupLoading.value = false
  }
}

const sanitizeMfaCode = () => {
  mfaSetupCode.value = mfaSetupCode.value.replace(/\D/g, '').slice(0, 6)
}

const completeMfaSetup = async () => {
  const setupToken = authStore.mfaPending?.setupToken
  if (!setupToken) {
    mfaSetupError.value = 'Сессия истекла. Войдите заново.'
    return
  }
  if (mfaSetupCode.value.length !== 6) {
    mfaSetupError.value = 'Введите 6-значный код'
    return
  }
  mfaSetupSubmitting.value = true
  mfaSetupError.value = ''
  try {
    const res = await authApi.completeMfa({
      setupToken,
      code: mfaSetupCode.value,
    })
    if (disposed) return
    if (res.user) authStore.setUser(res.user)
    mfaBackupCodes.value = res.backupCodes
    activeStep.value = 'mfa-setup-backup'
    authStore.clearMfaPending()
  } catch (err: unknown) {
    mfaSetupError.value =
      (err as { data?: { error?: string } }).data?.error
      || 'Неверный код. Попробуйте снова.'
  } finally {
    mfaSetupSubmitting.value = false
  }
}

const downloadBackupCodes = () => {
  if (!process.client) return
  const blob = new Blob([mfaBackupCodes.value.join('\n') + '\n'], {
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

const finishMfaSetup = () => {
  emit('authenticated')
  emit('close')
}
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: all 0.25s ease;
}
.slide-enter-from {
  opacity: 0;
  transform: translateX(20px);
}
.slide-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}
</style>
