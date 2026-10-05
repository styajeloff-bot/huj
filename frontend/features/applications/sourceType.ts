import { formatApplicationNumber, type ApplicationNumberSource } from '~/utils'

export type SiteApplicationSourceType = 'platform' | 'dealer_site' | 'distributor_site'
export type ApplicationSourceType = SiteApplicationSourceType | 'dealer_account' | 'exchange'

export const applicationSourceOptions = [
  { value: 'platform', label: 'Заявка с сайта платформы МЛ', prefix: 'AP', icon: 'platform' },
  { value: 'dealer_site', label: 'Заявка с сайта дилера', prefix: 'ADE', icon: 'dealer' },
  { value: 'distributor_site', label: 'Заявка с сайта дистрибьютора', prefix: 'ADI', icon: 'distributor' },
] as const

export const applicationSourcePresentation = (source: unknown) =>
  applicationSourceOptions.find(option => option.value === source)

export const canViewApplicationSource = (role: string | null | undefined): boolean =>
  ['admin', 'carcraft_employee', 'leasing_company', 'distributor', 'dealer'].includes(role ?? '')

export const formatSourcedApplicationNumber = (
  application: (ApplicationNumberSource & { source_type?: ApplicationSourceType | null }) | null | undefined,
  visible = true,
): string => {
  const number = formatApplicationNumber(application)
  const source = visible ? applicationSourcePresentation(application?.source_type) : undefined
  return number !== '—' && source ? `${source.prefix} ${number}` : number
}
