import { ref } from 'vue'
import {
  createIdentityVerificationApi,
  type IdentityVerificationApi,
} from '~/features/identity-verification/api/identityVerificationApi'
import {
  mapIdentityVerificationError,
  MOBILE_ID_REQUIRED_MESSAGE,
} from '~/features/identity-verification/errorMapping'
import type {
  IdentityVerificationState,
  StartIdentityVerificationRequest,
} from '~/features/identity-verification/types'

export const useIdentityVerification = (
  api: IdentityVerificationApi = createIdentityVerificationApi(useRuntimeConfig()),
) => {

  const loading = ref(false)
  const submittingCode = ref(false)
  const currentStatus = ref<IdentityVerificationState | null>(null)
  const verificationId = ref<string | null>(null)
  const userError = ref('')

  const setStatus = (status: IdentityVerificationState | null) => {
    currentStatus.value = status
    verificationId.value = status?.verification_id || verificationId.value
  }

  const clearError = () => {
    userError.value = ''
  }

  const refreshStatus = async () => {
    loading.value = true
    clearError()

    try {
      const response = await api.getStatus()
      setStatus(response)
      return response
    } catch (err) {
      userError.value = mapIdentityVerificationError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  const startVerification = async (body: StartIdentityVerificationRequest = {}) => {
    loading.value = true
    clearError()

    try {
      const response = await api.start(body)
      verificationId.value = response.verification_id
      setStatus({
        verified: response.status === 'verified',
        verification_id: response.verification_id,
        status: response.status,
        provider: 'mobile_id',
        phone_masked: response.phone_masked,
        expires_at: response.expires_at,
        failure_message: response.failure_message,
      })
      return response
    } catch (err) {
      userError.value = mapIdentityVerificationError(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  const submitSmsCode = async (code: string) => {
    if (!verificationId.value) {
      userError.value = 'Сначала запустите верификацию.'
      throw new Error('Identity verification id is required')
    }

    submittingCode.value = true
    clearError()

    try {
      const response = await api.submitSmsCode(verificationId.value, { code })
      setStatus(response)
      if (response.verified || response.status === 'verified') {
        currentStatus.value = {
          ...response,
          verified: true,
          status: response.status || 'verified',
          provider: response.provider || 'mobile_id',
        }
      }
      return response
    } catch (err) {
      userError.value = mapIdentityVerificationError(err)
      throw err
    } finally {
      submittingCode.value = false
    }
  }

  return {
    loading,
    submittingCode,
    currentStatus,
    verificationId,
    userError,
    clearError,
    refreshStatus,
    startVerification,
    submitSmsCode,
    mapError: mapIdentityVerificationError,
    mobileIdRequiredMessage: MOBILE_ID_REQUIRED_MESSAGE,
  }
}
