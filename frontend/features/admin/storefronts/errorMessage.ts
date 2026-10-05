interface ValidationIssue {
  msg?: unknown
}

export const storefrontAdminErrorMessage = (error: unknown, fallback: string): string => {
  const response = error as {
    data?: { detail?: unknown; error?: unknown }
    message?: unknown
  }
  const detail = response.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue: ValidationIssue) => issue?.msg)
      .filter((message): message is string => typeof message === 'string' && Boolean(message))
    if (messages.length > 0) return messages.join('. ')
  }
  if (typeof response.data?.error === 'string' && response.data.error) return response.data.error
  if (typeof response.message === 'string' && response.message) return response.message
  return fallback
}
