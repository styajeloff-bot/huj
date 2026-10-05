export type ApplicationVehicleDisplayStatus =
  | 'active'
  | 'not_confirmed'
  | 'confirmed'
  | 'replacement'

export type ApplicationVehicleStatusPresentation = Readonly<{
  status: ApplicationVehicleDisplayStatus
  label: string
  badgeClass: string
}>

const APPLICATION_VEHICLE_STATUS_PRESENTATIONS: Readonly<
  Record<ApplicationVehicleDisplayStatus, ApplicationVehicleStatusPresentation>
> = {
  active: {
    status: 'active',
    label: 'Подтверждается',
    badgeClass: 'bg-[color:var(--storefront-info,#dbeafe)] text-[color:var(--storefront-info-text,#1e40af)]',
  },
  not_confirmed: {
    status: 'not_confirmed',
    label: 'Не подтверждено',
    badgeClass: 'bg-[color:var(--storefront-error,#fee2e2)] text-[color:var(--storefront-error-text,#991b1b)]',
  },
  confirmed: {
    status: 'confirmed',
    label: 'Подтверждено',
    badgeClass: 'bg-[color:var(--storefront-success,#dcfce7)] text-[color:var(--storefront-success-text,#166534)]',
  },
  replacement: {
    status: 'replacement',
    label: 'Замена ТС',
    badgeClass: 'bg-[color:var(--storefront-warning,#fef3c7)] text-[color:var(--storefront-warning-text,#92400e)]',
  },
}

const normalizeApplicationVehicleStatus = (
  status: string | null | undefined,
): ApplicationVehicleDisplayStatus => {
  if (status === 'rejected') return 'not_confirmed'
  if (status === 'not_confirmed' || status === 'confirmed' || status === 'replacement') {
    return status
  }
  return 'active'
}

export const applicationVehicleStatusPresentation = (
  status: string | null | undefined,
): ApplicationVehicleStatusPresentation =>
  APPLICATION_VEHICLE_STATUS_PRESENTATIONS[normalizeApplicationVehicleStatus(status)]
