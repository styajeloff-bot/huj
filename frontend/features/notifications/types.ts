import type { UUID } from '~/types/ids'

export const notificationTypes = [
  'application_status', 'document_request', 'approval', 'general',
  'document_status', 'leasing_approval', 'system', 'exchange_new_request',
  'exchange_new_bid', 'exchange_bid_updated', 'exchange_bid_accepted',
  'exchange_request_changed', 'exchange_bid_withdrawn', 'exchange_deadline',
  'exchange_request_finalized', 'exchange_bid_not_selected',
] as const

export type NotificationType = typeof notificationTypes[number]

/** Public filters are business categories; legacy resources remain readable. */
export const filterableNotificationTypes = [
  'application_status', 'document_request', 'document_status', 'leasing_approval',
  'exchange_new_request', 'exchange_new_bid', 'exchange_bid_updated',
  'exchange_bid_accepted', 'exchange_request_changed', 'exchange_bid_withdrawn',
  'exchange_deadline', 'exchange_request_finalized', 'exchange_bid_not_selected',
] as const satisfies readonly NotificationType[]

export interface NotificationData {
  event_type?: string
  entity_type?: 'leasing_application' | 'exchange_request' | 'exchange_bid' | 'reference_document'
  entity_id?: UUID
  event_id?: UUID
  request_number?: string
  changed_fields?: string[]
  previous_values?: Record<string, unknown>
  new_values?: Record<string, unknown>
  expiration_at?: string | null
  remaining_time?: string
  remaining_seconds?: number
  [key: string]: unknown
}

export interface NotificationItem {
  id: UUID
  title: string
  message: string
  type: NotificationType
  is_read: boolean
  read_at: string | null
  created_at: string
  action_url?: string | null
  application_id?: UUID | null
  application_display_number?: string | null
  event_id?: UUID | null
  data?: NotificationData | null
}
