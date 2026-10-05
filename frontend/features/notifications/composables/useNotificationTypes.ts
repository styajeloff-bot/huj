import { filterableNotificationTypes, type NotificationData, type NotificationType } from '../types'

const TYPE_LABELS: Record<NotificationType, string> = {
  application_status: 'Статус заявки',
  document_request: 'Запрос документов',
  document_status: 'Статус документов',
  leasing_approval: 'Решение ЛК',
  approval: 'Одобрение',
  general: 'Общее',
  system: 'Система',
  exchange_new_request: 'Биржа: новая заявка',
  exchange_new_bid: 'Биржа: новая ставка',
  exchange_bid_updated: 'Биржа: изменение ставки',
  exchange_bid_accepted: 'Биржа: ставка выбрана',
  exchange_request_changed: 'Биржа: изменение заявки',
  exchange_bid_withdrawn: 'Биржа: отзыв ставки',
  exchange_deadline: 'Биржа: срок заявки',
  exchange_request_finalized: 'Биржа: заявка завершена',
  exchange_bid_not_selected: 'Биржа: другая ставка выбрана',
}

const DOCUMENT_ICON = 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
const EXCHANGE_ICON = 'M7 7h14m0 0l-4-4m4 4l-4 4M17 17H3m0 0l4 4m-4-4l4-4'
const CLOCK_ICON = 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z'

export const useNotificationTypes = () => {
  const color = (type: string, data?: NotificationData | null) => data?.event_type === 'leasing.company_not_selected'
    ? 'red' : type === 'exchange_deadline' || type === 'document_request'
    ? 'amber' : type.startsWith('exchange_') || type === 'application_status' ? 'blue'
      : ['document_status', 'leasing_approval', 'approval'].includes(type) ? 'green' : 'gray'
  const styles = {
    red: ['bg-red-100 text-red-700', 'bg-red-100 text-red-800'],
    amber: ['bg-amber-100 text-amber-700', 'bg-amber-100 text-amber-800'],
    blue: ['bg-blue-100 text-blue-600', 'bg-blue-100 text-blue-800'],
    green: ['bg-green-100 text-green-600', 'bg-green-100 text-green-800'],
    gray: ['bg-gray-100 text-gray-600', 'bg-gray-100 text-gray-800'],
  }
  return {
    notificationTypeOptions: filterableNotificationTypes.map(value => ({ value, label: TYPE_LABELS[value] })),
    getNotificationIconClass: (type: string, data?: NotificationData | null) => styles[color(type, data)][0],
    getNotificationTypeClass: (type: string, data?: NotificationData | null) => styles[color(type, data)][1],
    getNotificationTypeText: (type: string) => TYPE_LABELS[type as NotificationType] || 'Уведомление',
    getNotificationIconPath: (type: string) => type === 'exchange_deadline'
      ? CLOCK_ICON : type.startsWith('exchange_') ? EXCHANGE_ICON : DOCUMENT_ICON,
  }
}
