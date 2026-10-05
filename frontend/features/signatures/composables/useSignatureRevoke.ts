import type { Ref } from 'vue'
import type { UUID } from '~/types/ids'
import type {
  RevokeInitiateResponse,
  RevokeOptionsResponse,
  RevokeVerifyResponse,
} from '~/types/signature'

interface ApiError {
  data?: {
    error_code?: string
    message?: string
    detail?: Record<string, unknown>
  }
  message?: string
}

export const useSignatureRevoke = (signatureId: Ref<UUID | null>) => {
  const config = useRuntimeConfig()
  const toast = useToast()
  const logger = useLogger()

  const isLoading = ref(false)
  const isLoadingOptions = ref(false)
  const isVerifying = ref(false)
  const error = ref<string | null>(null)
  const phoneMasked = ref('')
  const codeTtl = ref(600)
  const resendTimer = ref(0)
  const revokeRequestedAt = ref<string | null>(null)
  const revokeOptions = ref<RevokeOptionsResponse | null>(null)
  const revokeResult = ref<RevokeVerifyResponse | null>(null)
  const lastLeasingCompanyIds = ref<UUID[]>([])

  const canResend = computed(() => resendTimer.value <= 0)
  let timerInterval: ReturnType<typeof setInterval> | null = null

  const startResendTimer = (seconds: number) => {
    resendTimer.value = seconds
    if (timerInterval) clearInterval(timerInterval)
    timerInterval = setInterval(() => {
      resendTimer.value = Math.max(0, resendTimer.value - 1)
      if (resendTimer.value <= 0 && timerInterval) {
        clearInterval(timerInterval)
        timerInterval = null
      }
    }, 1000)
  }

  const clearError = () => {
    error.value = null
  }

  const ensureSignatureId = () => {
    if (!signatureId.value) {
      throw new Error('Signature id is required')
    }
    return signatureId.value
  }

  const fetchRevokeOptions = async () => {
    const id = ensureSignatureId()
    isLoadingOptions.value = true
    error.value = null

    try {
      revokeOptions.value = await $fetch<RevokeOptionsResponse>(
        `/api/v1/signatures/${id}/revoke-options`,
        {
          method: 'GET',
          baseURL: config.public.apiBase,
          credentials: 'include',
        },
      )
      return revokeOptions.value
    } catch (err) {
      const apiError = err as ApiError
      error.value = apiError.data?.message || 'Не удалось загрузить список лизинговых компаний.'
      logger.error('Failed to load SOPD revoke options', err)
      throw err
    } finally {
      isLoadingOptions.value = false
    }
  }

  const initiateRevoke = async (leasingCompanyIds: UUID[]) => {
    const id = ensureSignatureId()
    if (leasingCompanyIds.length === 0) {
      error.value = 'Выберите хотя бы одну лизинговую компанию.'
      throw new Error(error.value)
    }
    isLoading.value = true
    error.value = null
    lastLeasingCompanyIds.value = [...leasingCompanyIds]

    try {
      const response = await $fetch<RevokeInitiateResponse>(
        `/api/v1/signatures/${id}/revoke`,
        {
          method: 'POST',
          body: { leasing_company_ids: leasingCompanyIds },
          baseURL: config.public.apiBase,
          credentials: 'include',
        },
      )

      phoneMasked.value = response.phone_masked
      codeTtl.value = response.code_ttl_seconds
      revokeRequestedAt.value = response.revoke_requested_at
      startResendTimer(response.resend_delay_seconds)
      logger.info('SOPD revoke initiated', {
        signatureId: id,
        leasingCompanyIds,
      })
      return response
    } catch (err) {
      const apiError = err as ApiError
      error.value = apiError.data?.message || 'Не удалось отправить код. Попробуйте позже.'
      logger.error('Failed to initiate SOPD revoke', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  const verifyCode = async (code: string) => {
    const id = ensureSignatureId()
    isVerifying.value = true
    error.value = null

    try {
      const response = await $fetch<RevokeVerifyResponse>(
        `/api/v1/signatures/${id}/revoke/verify`,
        {
          method: 'POST',
          body: { code },
          baseURL: config.public.apiBase,
          credentials: 'include',
        },
      )

      const requestedAt = response.revoke_requested_at || revokeRequestedAt.value
      const requestedDate = formatDate(requestedAt)
      revokeResult.value = response
      const revokedCount = response.revoked_leasing_companies.length + response.revoked_contractors.length
      const modeText = response.is_full_revoke ? 'Полный отзыв подтверждён' : 'Частичный отзыв подтверждён'
      toast.success(
        `${modeText}${requestedDate ? ` по заявке от ${requestedDate} г.` : ''} Отозвано операторов: ${revokedCount}.`,
        { title: 'Отзыв СОПД подтверждён', duration: 8000 },
      )
      logger.info('SOPD revoke confirmed', {
        signatureId: id,
        confirmedAt: response.confirmed_at,
      })
      return response
    } catch (err) {
      const apiError = err as ApiError
      switch (apiError.data?.error_code) {
        case 'INVALID_VERIFICATION_CODE':
          error.value = 'Неверный код. Попробуйте ещё раз.'
          break
        case 'CODE_EXPIRED':
          error.value = 'Код истёк. Нажмите "Отправить повторно".'
          break
        case 'TOO_MANY_FAILED_ATTEMPTS':
          error.value = 'Превышено число попыток. Запросите новый код.'
          break
        default:
          error.value = apiError.data?.message || 'Произошла ошибка. Попробуйте позже.'
      }
      logger.error('Failed to verify SOPD revoke code', err)
      throw err
    } finally {
      isVerifying.value = false
    }
  }

  const resendCode = async () => {
    if (!canResend.value) return
    await initiateRevoke(lastLeasingCompanyIds.value)
  }

  onUnmounted(() => {
    if (timerInterval) clearInterval(timerInterval)
  })

  return {
    isLoading,
    isLoadingOptions,
    isVerifying,
    error,
    phoneMasked,
    codeTtl,
    resendDelay: resendTimer,
    revokeRequestedAt,
    revokeOptions,
    revokeResult,
    canResend,
    fetchRevokeOptions,
    initiateRevoke,
    verifyCode,
    resendCode,
    clearError,
  }
}

const formatDate = (isoDate?: string | null): string => {
  if (!isoDate) return ''
  return new Date(isoDate).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}
