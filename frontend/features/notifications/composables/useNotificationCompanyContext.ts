import { hasInjectionContext, inject, provide, type InjectionKey } from 'vue'
import { isUuid } from '~/types/ids'
import { withNotificationCompanyContext } from '~/utils/apiCompanyContext'

type CompanyGetter = () => string | undefined
const key: InjectionKey<CompanyGetter> = Symbol('notification-target-company')

/** Scope descendants to this target screen, never mutate auth/active-company state. */
export const provideNotificationCompanyContext = (source: () => unknown): CompanyGetter => {
  const company = () => { const value = source(); return isUuid(value) ? value : undefined }
  provide(key, company)
  return company
}

export const useNotificationCompanyContext = (): CompanyGetter =>
  hasInjectionContext() ? inject(key, () => undefined) : () => undefined

export const useNotificationCompanyRequest = (company = useNotificationCompanyContext()) => {
  const config = useRuntimeConfig()
  const url = (path: string) => withNotificationCompanyContext(path, company(), String(config.public.apiBase || ''))
  const request = <T>(path: string, options: Record<string, unknown> = {}) => $fetch<T>(url(path), options)
  return { company, url, request }
}
