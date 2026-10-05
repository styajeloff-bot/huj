import type { UUID } from '~/types/ids'
import type { NotificationItem, NotificationType } from '../types'
export type { NotificationItem } from '../types'

type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export interface NotificationsPagination {
  page: number
  limit: number
  total: number
  pages: number
}

export interface NotificationsResponse {
  notifications: NotificationItem[]
  pagination: NotificationsPagination
}

export interface NotificationsCountResponse {
  total_count: number
  unread_count: number
}

export interface NotificationsQuery {
  page?: number
  limit?: number
  is_read?: string
  type?: NotificationType | ''
  period?: string
}

export const createNotificationsApi = (config: RuntimeConfig) => {
  const request = <T>(url: string, options: Record<string, unknown> = {}) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
      ...options,
    })

  return {
    getNotifications: ({ type, ...query }: NotificationsQuery) =>
      request<NotificationsResponse>('/api/v1/notifications', {
        query: { ...query, notification_type: type || undefined },
      }),

    getCount: () =>
      request<NotificationsCountResponse>('/api/v1/notifications?fields=count'),

    markAsRead: (id: UUID) =>
      request<unknown>(`/api/v1/notifications/${id}`, {
        method: 'PATCH',
        body: { is_read: true },
      }),

    markAllAsRead: () =>
      request<unknown>('/api/v1/notifications', {
        method: 'PATCH',
        body: { is_read: true },
      }),

    deleteNotification: (id: UUID) =>
      request<unknown>(`/api/v1/notifications/${id}`, { method: 'DELETE' }),
  }
}
