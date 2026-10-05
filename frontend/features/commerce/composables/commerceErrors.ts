import type { CommerceProblemDetails } from '../types'
import { getUserFacingErrorMessage } from '~/utils/userFacingError'

interface FetchFailure {
  status?: number
  statusCode?: number
  response?: { status?: number }
  data?: CommerceProblemDetails
  message?: string
}

export const commerceFailureStatus = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined
  const failure = error as FetchFailure
  return failure.statusCode ?? failure.status ?? failure.response?.status
}

export const commerceFailureMessage = (error: unknown, fallback: string): string => {
  return getUserFacingErrorMessage(error, fallback)
}
