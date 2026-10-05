import type { RouteLocationRaw } from 'vue-router'
import { useStorefront } from '~/features/storefront'
import { CHECKOUT_STEPS, CHECKOUT_STATUS_SECTIONS } from '~/features/checkout'
import { useAuthStore } from '~/features/auth/store/auth'
import { buildWorkspaceLocation, readWorkspaceReturnStorefront } from '~/features/workspace/returnContext'
import { isUuid, type UUID } from '~/types/ids'

type QuestionnaireSource = 'application' | 'applications' | 'leasing'
type QuestionnaireContext = {
  notificationCompanyId?: UUID | null
  leasingCompanyId?: UUID | null
}
const sections = new Set<string>([...CHECKOUT_STEPS, ...CHECKOUT_STATUS_SECTIONS].map(item => item.section))

/** Only known application screens may be used as questionnaire return targets. */
export function useQuestionnaireNavigation() {
  const route = useRoute()
  const authStore = useAuthStore()
  const { publicRoute } = useStorefront()
  const contextQuery = (context: QuestionnaireContext = {}): Record<string, string> => {
    const query: Record<string, string> = {}
    const company = context.notificationCompanyId ?? route.query.notification_company_id
    const leasingCompany = context.leasingCompanyId ?? route.query.leasing_company_id
    if (isUuid(company)) query.notification_company_id = company
    if (isUuid(leasingCompany)) query.leasing_company_id = leasingCompany
    const storefront = readWorkspaceReturnStorefront(route.params.storefrontSlug)
      ?? readWorkspaceReturnStorefront(route.query.return_storefront)
    if (storefront) query.return_storefront = storefront
    return query
  }

  const questionnaireLocation = (applicationId: UUID, source: QuestionnaireSource, context: QuestionnaireContext = {}): RouteLocationRaw => {
    // Enter the questionnaire itself, never inherit a company/status step from its caller.
    const query: Record<string, string> = { ...contextQuery(context), source }
    return {
      path: source === 'application' ? publicRoute(`/questionnaire/${applicationId}`) : `/workspace/questionnaire/${applicationId}`,
      query,
    }
  }

  const applicationLocation = (applicationId: UUID, workspace: boolean): RouteLocationRaw => {
    const source = authStore.isLeasingCompany ? 'leasing'
      : workspace ? (route.query.source === 'leasing' && authStore.isCarCraftEmployee ? 'leasing' : 'applications')
        : 'application'
    const query = contextQuery()
    if (source === 'leasing') {
      return buildWorkspaceLocation(`/workspace/leasing-applications/${applicationId}`, readWorkspaceReturnStorefront(query.return_storefront), query)
    }
    if (source === 'applications') {
      return buildWorkspaceLocation('/workspace/applications', readWorkspaceReturnStorefront(query.return_storefront), { ...query, application: applicationId })
    }
    const section = route.query.section
    const step = route.query.step
    if (typeof section === 'string' && sections.has(section)) query.section = section
    if (typeof step === 'string' && /^[1-7]$/.test(step)) query.step = step
    return { path: publicRoute(`/application/${applicationId}`), query }
  }
  return { questionnaireLocation, applicationLocation }
}
