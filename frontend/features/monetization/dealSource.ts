import { applicationSourcePresentation, formatSourcedApplicationNumber, type ApplicationSourceType } from '~/features/applications/sourceType'
import type { Deal, FastDealSourceType, SourceType } from './types'

/** Shown next to deals and conditions whose source is the «Регистрация сделки» flow. */
export const fastDealOriginLabel = 'Быстрая регистрация'

/** Deals of these sources have no application: they originate from a fast deal. */
export const isFastDealSource = (value: unknown): value is FastDealSourceType =>
  value === 'dealer_to_leasing' || value === 'leasing_to_dealer'

/** The site source the shared application badge can render; fast deal and other sources have none. */
export const applicationSourceOf = (source: SourceType): ApplicationSourceType | null =>
  applicationSourcePresentation(source)?.value ?? null

/**
 * Application sites prefix the number with their source code, while a fast deal
 * number (`DD|DL-<INN>-<DDMMYY>-<NNN>`) is already final and must stay as is.
 */
export const dealNumber = (deal: Pick<Deal, 'application_number' | 'source_type'>): string =>
  formatSourcedApplicationNumber({ display_number: deal.application_number, source_type: applicationSourceOf(deal.source_type) })
