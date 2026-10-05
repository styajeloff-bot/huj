import type { IdentityVerificationApiError } from './types'

export const MOBILE_ID_REQUIRED_MESSAGE = 'Для подписания СОПД необходимо пройти верификацию через Mobile ID.'

const getErrorCode = (error: IdentityVerificationApiError): string => {
  const detail = error.data?.detail
  if (typeof detail === 'object' && detail?.code) return String(detail.code)
  return String(error.data?.error_code || error.data?.code || '')
}

const getErrorMessage = (error: IdentityVerificationApiError): string => {
  const detail = error.data?.detail
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object' && detail?.message) return String(detail.message)
  if (typeof detail === 'object' && detail?.error) return String(detail.error)
  return error.data?.message || error.data?.error || error.message || ''
}

export const mapIdentityVerificationError = (error: unknown): string => {
  const apiError = error as IdentityVerificationApiError
  const code = getErrorCode(apiError).toUpperCase()
  const message = getErrorMessage(apiError)
  const lowerMessage = message.toLowerCase()
  const status = apiError.status || apiError.statusCode || apiError.response?.status

  if (message === MOBILE_ID_REQUIRED_MESSAGE) return message

  if (
    code.includes('WRONG')
    || code.includes('INVALID_SMS')
    || code.includes('INVALID_VERIFICATION_CODE')
    || lowerMessage.includes('невер')
    || lowerMessage.includes('wrong code')
  ) {
    return 'Неверный код. Проверьте SMS и попробуйте ещё раз.'
  }

  if (
    code.includes('EXPIRED')
    || lowerMessage.includes('ист')
    || lowerMessage.includes('expired')
  ) {
    return 'Срок действия проверки истёк. Запустите верификацию заново.'
  }

  if (
    code.includes('PROVIDER_UNAVAILABLE')
    || status === 503
    || lowerMessage.includes('недоступ')
    || lowerMessage.includes('unavailable')
  ) {
    return 'Сервис Mobile ID сейчас недоступен. Попробуйте позже.'
  }

  return message || 'Не удалось выполнить верификацию. Попробуйте ещё раз.'
}
