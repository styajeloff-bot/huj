import { defineStore, skipHydrate } from 'pinia'

interface Toast {
  id: number
  type: 'success' | 'error' | 'warning' | 'info'
  title?: string
  message: string
  duration: number
  persistent: boolean
  actionText?: string
  actionCallback?: () => void
  remainingTime: number
}

export const useToastStore = defineStore('toast', {
  state: () => ({
    toasts: skipHydrate([] as Toast[]), // Исключаем из гидратации
    nextId: 1
  }),

  actions: {
    addToast(options: Partial<Toast> & { message: string }) {
      const toast: Toast = {
        id: this.nextId++,
        type: options.type || 'info',
        title: options.title,
        message: options.message,
        duration: options.duration !== undefined ? options.duration : 5000,
        persistent: options.persistent || false,
        actionText: options.actionText,
        actionCallback: options.actionCallback,
        remainingTime: options.duration !== undefined ? options.duration : 5000
      }

      this.toasts.push(toast)

      // Auto-dismiss if not persistent (только на клиенте)
      if (process.client && !toast.persistent && toast.duration > 0) {
        const startTime = Date.now()
        const interval = setInterval(() => {
          const elapsed = Date.now() - startTime
          toast.remainingTime = Math.max(0, toast.duration - elapsed)
          
          if (elapsed >= toast.duration) {
            this.removeToast(toast.id)
            clearInterval(interval)
          }
        }, 100)
      }

      return toast.id
    },

    removeToast(id: number) {
      const index = this.toasts.findIndex(t => t.id === id)
      if (index > -1) {
        this.toasts.splice(index, 1)
      }
    },

    clearAllToasts() {
      this.toasts = []
    },

    success(message: string, options: Partial<Toast> = {}) {
      return this.addToast({ type: 'success', message, ...options })
    },

    error(message: string, options: Partial<Toast> = {}) {
      return this.addToast({ type: 'error', message, ...options })
    },

    warning(message: string, options: Partial<Toast> = {}) {
      return this.addToast({ type: 'warning', message, ...options })
    },

    info(message: string, options: Partial<Toast> = {}) {
      return this.addToast({ type: 'info', message, ...options })
    },

    show(options: Partial<Toast> & { message: string }) {
      return this.addToast(options)
    }
  }
})
