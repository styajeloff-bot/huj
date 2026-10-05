import { useAuthStore } from '~/features/auth/store/auth'
import { buildWorkspaceLocation, readWorkspaceReturnStorefront } from '~/features/workspace/returnContext'
import { isUuid } from '~/types/ids'

/** Leasing companies read their filtered questionnaire in the workspace; authors keep the editor. */
export default defineNuxtRouteMiddleware((to) => {
  if (import.meta.server) return
  const authStore = useAuthStore()
  if (!authStore.isLeasingCompany) return

  const applicationId = typeof to.params.id === 'string' ? to.params.id : ''
  const query: Record<string, string> = {
    source: 'leasing',
  }
  if (isUuid(to.query.notification_company_id)) query.notification_company_id = to.query.notification_company_id
  if (isUuid(to.query.leasing_company_id)) query.leasing_company_id = to.query.leasing_company_id
  const storefront = readWorkspaceReturnStorefront(to.params.storefrontSlug)
    ?? readWorkspaceReturnStorefront(to.query.return_storefront)
  return navigateTo(buildWorkspaceLocation(
    `/workspace/questionnaire/${encodeURIComponent(applicationId)}`, storefront, query,
  ), { replace: true })
})
