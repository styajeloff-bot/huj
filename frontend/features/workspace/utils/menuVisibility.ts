import {
  WORKSPACE_MENU,
  type BusinessRole,
  type WorkspaceAuthLike,
  type WorkspaceMenuItem,
} from '~/features/workspace/config/menu'
import { DEFAULT_SECTION_VISIBILITY } from '~/features/sectionVisibility/config'
import { isUuid } from '~/types/ids'

export type WorkspaceSectionVisibility = Readonly<Record<string, boolean>>

const questionnaireRoutePrefix = '/workspace/questionnaire/'

export const MENU_KEY_TO_SECTION_CODES: Record<string, string[]> = {
  applications: ['applications'],
  leasing_applications: ['applications'],
  warehouses: ['warehouses'],
  inventory: ['warehouses'],
  exchange: ['vehicle_exchange'],
  exchange_import: ['vehicle_exchange'],
  employees: ['employees'],
  special_equipment_catalog: ['catalog_management'],
  distributor_analytics: ['analytics'],
  leasing_analytics: ['analytics'],
  reports: ['analytics'],
  stats: ['analytics'],
  support: ['incentive_programs'],
  monetization: ['monetization_income', 'monetization_expense'],
}

/** Checks whether personal section access permits access to the given section codes. */
export function isPersonalSectionAllowed(
  sectionCodes: readonly string[],
  auth: WorkspaceAuthLike,
  visibility: WorkspaceSectionVisibility = {},
): boolean {
  if (auth.isCarCraftEmployee) return true

  // Monetization is permitted if at least one of monetization_income or monetization_expense is not false
  const isMonetization = sectionCodes.length === 2
    && sectionCodes.includes('monetization_income')
    && sectionCodes.includes('monetization_expense')

  if (isMonetization) {
    const incomeDenied = auth.sectionAccess?.['monetization_income'] === false
      || visibility['monetization_income'] === false
    const expenseDenied = auth.sectionAccess?.['monetization_expense'] === false
      || visibility['monetization_expense'] === false
    if (incomeDenied && expenseDenied) return false
    if (auth.sectionAccess?.['monetization'] === false || visibility['monetization'] === false) return false
    return true
  }

  for (const code of sectionCodes) {
    if (auth.sectionAccess?.[code] === false) return false
    if (visibility[code] === false) return false
  }

  if (sectionCodes.includes('applications')) {
    if (!auth.canViewApplications) return false
    if (visibility['leasing_applications'] === false) return false
  }

  return true
}

/** Permit loading one target, not access to its data: its API verifies membership
 * and can_view_applications. This never changes the user's general menu/auth. */
export function canAttemptWorkspaceNotificationTarget(
  role: BusinessRole,
  path: string,
  query: Readonly<Record<string, unknown>>,
  visibility: WorkspaceSectionVisibility,
  auth?: WorkspaceAuthLike,
): boolean {
  const questionnaireTarget = path.startsWith(questionnaireRoutePrefix)
    && isUuid(path.slice(questionnaireRoutePrefix.length))
  const companyTarget = isUuid(query.notification_company_id) && (
    ((role === 'dealer' || role === 'distributor') && (
      (path === '/workspace/applications' && isUuid(query.application)) || questionnaireTarget
    ))
    || (path === '/workspace/exchange' && ['dealer', 'distributor', 'leasing_company'].includes(role) && isUuid(query.request))
  )
  const lcTarget = role === 'leasing_company' && isUuid(query.leasing_company_id) && (
    (path.startsWith('/workspace/leasing-applications/') && isUuid(path.slice('/workspace/leasing-applications/'.length)))
    || questionnaireTarget
  )
  if (!companyTarget && !lcTarget) return false
  const item = findWorkspaceMenuItemForPath(WORKSPACE_MENU[role], path)
  if (!item) return false
  if (auth) {
    const sectionCodes = MENU_KEY_TO_SECTION_CODES[item.key]
    if (sectionCodes && !isPersonalSectionAllowed(sectionCodes, auth, visibility)) {
      return false
    }
  }
  return Boolean(!item.configurable || (visibility[item.key] ?? DEFAULT_SECTION_VISIBILITY[role]?.[item.key] ?? true))
}

/**
 * Returns the single source of truth for workspace navigation availability.
 * Missing visibility values fall back to the shared catalog defaults. This is
 * especially important for employee-only sections that default to hidden.
 */
export function getAvailableWorkspaceMenu(
  role: BusinessRole,
  auth: WorkspaceAuthLike,
  visibility: WorkspaceSectionVisibility = {},
): WorkspaceMenuItem[] {
  return WORKSPACE_MENU[role].filter((item) => {
    if (item.gate && !item.gate(auth)) return false

    // Personal section access check
    const sectionCodes = MENU_KEY_TO_SECTION_CODES[item.key]
    if (sectionCodes && !isPersonalSectionAllowed(sectionCodes, auth, visibility)) {
      return false
    }

    if ((item.key === 'applications' || item.key === 'leasing_applications') && !auth.canViewApplications) {
      return false
    }

    if (!item.configurable) return true
    return visibility[item.key] ?? DEFAULT_SECTION_VISIBILITY[role]?.[item.key] ?? true
  })
}

export function findWorkspaceMenuItemForPath(
  items: readonly WorkspaceMenuItem[],
  path: string,
): WorkspaceMenuItem | undefined {
  // The questionnaire is a detail view of the role's existing applications section.
  if (path.startsWith(questionnaireRoutePrefix)) {
    return items.find(item => item.key === 'applications' || item.key === 'leasing_applications')
  }
  return items.find((item) => path === item.to || path.startsWith(`${item.to}/`))
}

export function isWorkspaceRouteAllowed(
  path: string,
  role: BusinessRole,
  auth: WorkspaceAuthLike,
  visibility: WorkspaceSectionVisibility = {},
): boolean {
  if (auth.isCarCraftEmployee) return true
  const routeItem = findWorkspaceMenuItemForPath(WORKSPACE_MENU[role], path)
  if (!routeItem) return false
  const availableItems = getAvailableWorkspaceMenu(role, auth, visibility)
  return availableItems.some((item) => item.key === routeItem.key)
}

export function getFirstAvailableWorkspaceRoute(
  role: BusinessRole,
  auth: WorkspaceAuthLike,
  visibility: WorkspaceSectionVisibility = {},
): string {
  return getAvailableWorkspaceMenu(role, auth, visibility)[0]?.to ?? '/workspace'
}
