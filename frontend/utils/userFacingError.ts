export const DEFAULT_USER_FACING_ERROR = 'Упс, что-то пошло не так. Пожалуйста, свяжитесь с техподдержкой'

const TECHNICAL_PATTERNS: RegExp[] = [
  /[a-z0-9]+_[a-z0-9]+/i, // snake_case identifier (e.g. leasing_purpose, line_id, item_id, status_code)
  /traceback/i,
  /pydantic/i,
  /validation_error/i,
  /internal\s+server\s+error/i,
  /status\s*(?:code\s*)?[45]\d{2}/i,
  /[45]\d{2}\s+(?:internal|bad|gateway|service|unprocessable|not\s+found)/i,
  /exception/i,
  /nullpointer/i,
  /syntaxerror/i,
  /typeerror/i,
  /referenceerror/i,
  /object\s+object/i,
  /at\s+(?:object|function|async|\/|[a-z0-9_]+\.)/i,
  /cannot\s+read\s+properties/i,
  /is\s+not\s+(?:a\s+function|defined)/i,
  /undefined/i,
  /failed\s+to\s+fetch/i,
  /fetcherror/i,
  /axioserror/i,
  /networkerror/i,
  /database\s+error/i,
  /sql(?:alchemy|error)?/i,
  /constraint/i,
  /integrityerror/i,
  /unhandledrejection/i,
  /request\s+failed/i,
  /\/api\/v\d+/i,
  /https?:\/\//i,
]

function isSerializedJson(str: string): boolean {
  const trimmed = str.trim()
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      JSON.parse(trimmed)
      return true
    } catch {
      return true
    }
  }
  return false
}

function isTechnicalMessage(message: string): boolean {
  if (isSerializedJson(message)) {
    return true
  }
  return TECHNICAL_PATTERNS.some(pattern => pattern.test(message))
}

export function getUserFacingErrorMessage(error: unknown, fallbackMessage?: string): string {
  const fallback = fallbackMessage || DEFAULT_USER_FACING_ERROR

  if (error == null) {
    return fallback
  }

  // If error is an array or raw technical structure
  if (Array.isArray(error)) {
    console.error('[API Error]', error)
    return fallback
  }

  let candidate: string | null = null
  let isExplicitlyTechnical = false

  if (typeof error === 'string') {
    candidate = error
  } else if (typeof error === 'object') {
    const errObj = error as Record<string, unknown>

    if (typeof errObj.name === 'string' && /^(TypeError|SyntaxError|ReferenceError|RangeError)$/i.test(errObj.name)) {
      isExplicitlyTechnical = true
    }

    const data = errObj.data as Record<string, unknown> | undefined

    if (data && typeof data === 'object') {
      if (Array.isArray(data.detail)) {
        isExplicitlyTechnical = true
      } else if (typeof data.detail === 'string') {
        candidate = data.detail
      } else if (data.detail && typeof data.detail === 'object') {
        const detailObj = data.detail as Record<string, unknown>
        if (typeof detailObj.message === 'string') {
          candidate = detailObj.message
        } else {
          isExplicitlyTechnical = true
        }
      } else if (typeof data.message === 'string') {
        candidate = data.message
      } else if (typeof data.error === 'string') {
        candidate = data.error
      }
    }

    if (!candidate && !isExplicitlyTechnical) {
      if (typeof errObj.message === 'string') {
        candidate = errObj.message
      }
    }
  }

  if (isExplicitlyTechnical) {
    console.error('[API Error]', error)
    return fallback
  }

  if (!candidate || !candidate.trim()) {
    console.error('[API Error]', error)
    return fallback
  }

  const trimmedCandidate = candidate.trim()

  if (isTechnicalMessage(trimmedCandidate)) {
    console.error('[API Error]', error)
    return fallback
  }

  // Must be a human-readable Russian business message (contains Cyrillic letters)
  if (!/[а-яё]/i.test(trimmedCandidate)) {
    console.error('[API Error]', error)
    return fallback
  }

  return trimmedCandidate
}
