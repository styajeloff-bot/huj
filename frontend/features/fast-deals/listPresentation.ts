import type { AssigneeOut, FastDealListItem } from './types'
import { invitedLeasingCompaniesLabel } from './status'

/** The part of a list row that decides how the parties of a deal are named. */
export type FastDealPartiesSource = Pick<
  FastDealListItem,
  'source_type' | 'initiator_company' | 'dealer_company' | 'leasing_company' | 'invited_lc_count'
>

export interface FastDealParties {
  dealer: string
  leasing: string
}

export interface FastDealPartiesOptions {
  /**
   * The viewer is a leasing company. The server tells it only about its own invitation, so before
   * its offer is selected the leasing side of a dealer → LC deal is «Ваша компания», not a count.
   */
  viewerIsLeasing?: boolean
}

/**
 * Dealer and leasing company of a list row. In a dealer → LC deal the LC is unknown until the
 * dealer selects one offer: before that «в N лизинговых компаний» is shown. In a LC → dealer deal
 * a draft has no dealer yet (it is derived from the positions when the deal is sent).
 */
export function fastDealParties(
  deal: FastDealPartiesSource,
  options: FastDealPartiesOptions = {},
): FastDealParties {
  if (deal.source_type === 'dealer_to_leasing') {
    const invited = deal.invited_lc_count ?? 0
    const pending = options.viewerIsLeasing
      ? 'Ваша компания'
      : invited > 0 ? invitedLeasingCompaniesLabel(invited) : 'Лизинговые компании не выбраны'
    return {
      dealer: deal.dealer_company?.name ?? deal.initiator_company.name,
      leasing: deal.leasing_company?.name ?? pending,
    }
  }
  return {
    dealer: deal.dealer_company?.name ?? 'Дилер не указан',
    leasing: deal.leasing_company?.name ?? deal.initiator_company.name,
  }
}

export interface AssigneeSummary {
  key: string
  roleLabel: string
  name: string
  /** Company the employee works for; lets the viewer tell the parties apart. */
  companyName: string | null
}

const ASSIGNEE_ROLE_LABELS: Record<AssigneeOut['role'], string> = {
  primary: 'Основной',
  additional: 'Дополнительный',
}

/** Primary employees first; the company name is resolved among the parties of the row. */
export function assigneeSummaries(
  deal: Pick<FastDealListItem, 'assignees' | 'initiator_company' | 'dealer_company' | 'leasing_company'>,
): AssigneeSummary[] {
  const companies = [deal.initiator_company, deal.dealer_company, deal.leasing_company]
  const companyName = (id: string): string | null => companies.find(company => company?.id === id)?.name ?? null
  return [...(deal.assignees ?? [])]
    .sort((left, right) => Number(right.role === 'primary') - Number(left.role === 'primary'))
    .map(assignee => ({
      key: `${assignee.company_id}:${assignee.role}:${assignee.user_id}`,
      roleLabel: ASSIGNEE_ROLE_LABELS[assignee.role] ?? assignee.role,
      name: assignee.user_name || 'Сотрудник',
      companyName: companyName(assignee.company_id),
    }))
}
