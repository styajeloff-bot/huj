interface CategoriesFailureInjectionContext {
  enabled: unknown
  isServer: boolean
  cookieHeader: string | undefined
}

const enabledExplicitly = (value: unknown): boolean => value === true || value === 'true'

export const shouldInjectSpecialEquipmentCategoriesFailure = ({
  enabled,
  isServer,
  cookieHeader,
}: CategoriesFailureInjectionContext): boolean => {
  if (!isServer || !enabledExplicitly(enabled) || !cookieHeader) return false

  return cookieHeader
    .split(';')
    .some(cookie => cookie.trim() === 'e2e_fault_categories=1')
}
