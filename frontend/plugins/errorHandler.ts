import { useAuthStore } from '~/features/auth/store/auth'

interface ApiError {
  statusCode?: number
  message?: string
}

interface ErrorHandler {
  handleApiError: (error: ApiError, customMessage?: string) => void
  handleValidationError: (errors: unknown) => void
}

export default defineNuxtPlugin({
  name: 'error-handler',
  setup(nuxtApp) {
    // Обработка ошибок Vue
    nuxtApp.hook('vue:error', (error: unknown, _instance, info: string) => {
      console.error('Vue error:', error)
      console.error('Error info:', info)

      // Показать уведомление пользователю для критических ошибок
      if (process.client && error && typeof error === 'object') {
        const toast = useToast()
        const errorObj = error as { message?: string }

        if (errorObj.message?.includes('Network')) {
          toast.error('Ошибка сети. Проверьте подключение к интернету.')
        } else if (errorObj.message?.includes('timeout')) {
          toast.error('Превышено время ожидания ответа от сервера.')
        } else {
          // Не показываем технические ошибки пользовател��
          console.error('Technical error suppressed from user view:', error)
        }
      }
    })

    // Обработка ошибок Nuxt (включая fetch-ошибки)
    nuxtApp.hook('app:error', (error: unknown) => {
      const err = error as { statusCode?: number; message?: string; _handledByAuthInterceptor?: boolean }
      console.error('Nuxt app error:', error)

      if (!err?.statusCode || err.statusCode < 400) return

      // The fetch-auth interceptor already handled 401 (refresh + redirect).
      if (err._handledByAuthInterceptor) return

      if (process.client) {
        const toast = useToast()

        if (err.statusCode === 401) {
          const authStore = useAuthStore()
          if (authStore.isAuthenticated) {
            toast.warning('Ваша сессия истекла. Пожалуйста, авторизуйтесь снова.')
          }
          // Redirect is handled by the fetch-auth interceptor; keep this as a fallback.
          if (!window.location.pathname.startsWith('/auth')) {
            navigateTo('/auth')
          }
        } else if (err.statusCode === 403) {
          toast.error('У вас недостаточно прав для выполнения этого действия.')
        } else if (err.statusCode === 404) {
          toast.error('Запрашиваемый ресурс не найден.')
        } else if (err.statusCode === 500) {
          toast.error('Произошла ошибка на сервере. Попробуйте позже.')
        } else if (err.statusCode >= 400) {
          toast.error(err.message || 'Произошла ошибка при выполнении запроса.')
        }
      }
    })

    // Глобальный обработчик необработанных ошибок
    if (process.client) {
      window.addEventListener('error', (event: ErrorEvent) => {
        console.error('Global error:', event.error)
      })

      window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
        console.error('Unhandled promise rejection:', event.reason)

        // Показать уведомление для критических ошибок
        const toast = useToast()
        if (event.reason?.message?.includes('Network')) {
          toast.error('Ошибка сети. Проверьте подключение к интернету.')
        } else if (event.reason?.message?.includes('timeout')) {
          toast.error('Превышено время ожидания ответа от сервера.')
        }
      })
    }

    // Добавить глобальные методы для обработки ошибок
    nuxtApp.provide('errorHandler', {
      handleApiError: (error: ApiError, customMessage?: string) => {
        console.error('API Error:', error)

        if (process.client) {
          const toast = useToast()

          if (error?.statusCode === 401) {
            // The fetch-auth interceptor already attempts refresh + redirect.
            // Only show a toast if we end up here as a fallback.
            toast.warning(customMessage || 'Требуется авторизация')
          } else if (error?.statusCode === 403) {
            toast.error(customMessage || 'У вас недостаточно прав')
          } else if (error?.statusCode === 404) {
            toast.error(customMessage || 'Ресурс не найден')
          } else if (error?.statusCode === 500) {
            toast.error(customMessage || 'Ошибка сервера. Попробуйте позже')
          } else {
            toast.error(customMessage || error?.message || 'Произошла ошибка')
          }
        }
      },

      handleValidationError: (errors: unknown) => {
        if (process.client) {
          const toast = useToast()

          if (Array.isArray(errors)) {
            errors.forEach((error: string) => toast.error(error))
          } else if (typeof errors === 'object' && errors !== null) {
            Object.values(errors).forEach((error: unknown) => {
              if (Array.isArray(error)) {
                error.forEach((msg: string) => toast.error(msg))
              } else if (typeof error === 'string') {
                toast.error(error)
              }
            })
          } else if (typeof errors === 'string') {
            toast.error(errors)
          }
        }
      }
    } satisfies ErrorHandler)
  }
})
