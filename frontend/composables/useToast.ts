import { useToastStore } from '@/stores/toast'

interface ToastOptions {
  type?: 'success' | 'error' | 'warning' | 'info'
  title?: string
  message?: string
  duration?: number
  persistent?: boolean
  actionText?: string
  actionCallback?: () => void
  confirmText?: string
  dismissOnConfirm?: boolean
}

interface Notification {
  title: string
  message: string
  action_url?: string
}

interface ApiError {
  data?: { error?: string }
  message?: string
}

export const useToast = () => {
  const toastStore = process.client ? useToastStore() : null

  const showToast = {
    success: (message: string, options: ToastOptions = {}) => {
      if (process.client && toastStore) return toastStore.success(message, options)
    },
    error: (message: string, options: ToastOptions = {}) => {
      if (process.client && toastStore) return toastStore.error(message, options)
    },
    warning: (message: string, options: ToastOptions = {}) => {
      if (toastStore) return toastStore.warning(message, options)
    },
    info: (message: string, options: ToastOptions = {}) => {
      if (toastStore) return toastStore.info(message, options)
    }
  }

  return {
    showToast,
    show: (options: ToastOptions & { message: string }) => (toastStore ? toastStore.show(options) : null),
    success: (message: string, options: ToastOptions = {}) => {
      if (process.client && toastStore) return toastStore.success(message, options)
    },
    error: (message: string, options: ToastOptions = {}) => {
      return toastStore ? toastStore.error(message, options) : null
    },
    warning: (message: string, options: ToastOptions = {}) => {
      return toastStore ? toastStore.warning(message, options) : null
    },
    info: (message: string, options: ToastOptions = {}) => {
      return toastStore ? toastStore.info(message, options) : null
    },
    remove: (id: number) => (toastStore ? toastStore.removeToast(id) : null),
    clear: () => (toastStore ? toastStore.clearAllToasts() : null),
    apiError: (error: ApiError | string, fallbackMessage = 'Произошла ошибка') => {
      if (!toastStore) return null

      let message = fallbackMessage
      if (typeof error === 'string') {
        message = error
      } else if (error?.data?.error) {
        message = error.data.error
      } else if (error?.message) {
        message = error.message
      }

      return toastStore.error(message, { duration: 7000 })
    },
    apiSuccess: (operation: string, entity = 'Операция') => {
      return toastStore ? toastStore.success(`${entity} успешно ${operation}`) : null
    },
    notification: (notification: Notification) => {
      if (!toastStore) return null
      return toastStore.show({
        type: 'info',
        title: notification.title,
        message: notification.message,
        duration: 8000,
        actionText: 'Перейти',
        actionCallback: () => {
          if (notification.action_url) navigateTo(notification.action_url)
        }
      })
    },
    confirm: (message: string, onConfirm: () => void, options: ToastOptions = {}) => {
      if (!toastStore) return null
      return toastStore.show({
        type: 'warning',
        message,
        persistent: true,
        actionText: options.confirmText || 'Подтвердить',
        actionCallback: onConfirm,
        ...options
      })
    }
  }
}
