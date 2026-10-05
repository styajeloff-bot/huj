<template>
  <div data-storefront-block="client.notifications" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-8">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)]">Уведомления</h1>
            <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">
              Все ваши уведомления в одном месте
            </p>
          </div>
          <div class="flex items-center space-x-3">
            <button
              v-if="unreadCount > 0"
              @click="markAllAsRead"
              class="btn-secondary"
              :disabled="markingAllAsRead"
            >
              {{ markingAllAsRead ? 'Отмечаем...' : 'Прочитать все' }}
            </button>
            <button @click="refreshNotifications" class="btn-primary">
              Обновить
            </button>
          </div>
        </div>
      </div>

      <!-- Statistics Cards -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-6">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-5 5v-5zM9 9l3-3 3 3M9 9a9.02 9.02 0 000 6.4"/>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <div class="text-2xl font-bold text-[color:var(--storefront-text,#111827)]">{{ totalCount }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Всего уведомлений</div>
            </div>
          </div>
        </div>

        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-6">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-[color:var(--storefront-warning-icon,#ca8a04)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <div class="text-2xl font-bold text-[color:var(--storefront-text,#111827)]">{{ unreadCount }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Непрочитанные</div>
            </div>
          </div>
        </div>

        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-6">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4"/>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <div class="text-2xl font-bold text-[color:var(--storefront-text,#111827)]">{{ receivedTodayCount }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Получено сегодня</div>
            </div>
          </div>
        </div>

        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-6">
          <div class="flex items-center">
            <div class="flex-shrink-0">
              <div class="w-8 h-8 bg-[color:rgb(var(--storefront-info-rgb,243_232_255)/var(--tw-bg-opacity,1))] rounded-full flex items-center justify-center">
                <svg class="w-5 h-5 text-[color:var(--storefront-info-icon,#9333ea)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                </svg>
              </div>
            </div>
            <div class="ml-4">
              <div class="text-2xl font-bold text-[color:var(--storefront-text,#111827)]">{{ thisWeekCount }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">За эту неделю</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Filters -->
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-6 mb-8">
        <div class="flex flex-wrap items-center gap-4">
          <div class="flex items-center space-x-2">
            <label class="text-sm font-medium text-[color:var(--storefront-label,#374151)]">Статус:</label>
            <select v-model="filters.is_read" class="storefront-control select-field w-auto">
              <option value="">Все</option>
              <option value="false">Непрочитанные</option>
              <option value="true">Прочитанные</option>
            </select>
          </div>

          <div class="flex items-center space-x-2">
            <label class="text-sm font-medium text-[color:var(--storefront-label,#374151)]">Тип:</label>
            <select v-model="filters.type" aria-label="Тип уведомлений" class="storefront-control select-field w-auto">
              <option value="">Все типы</option>
              <option v-for="option in notificationTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>

          <div class="flex items-center space-x-2">
            <label class="text-sm font-medium text-[color:var(--storefront-label,#374151)]">Период:</label>
            <select v-model="filters.period" class="storefront-control select-field w-auto">
              <option value="">Все время</option>
              <option value="today">Сегодня</option>
              <option value="week">Неделя</option>
              <option value="month">Месяц</option>
            </select>
          </div>

          <button @click="clearFilters" class="btn-secondary text-sm">
            Сбросить фильтры
          </button>
        </div>
      </div>

      <!-- Notifications List -->
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow">
        <div v-if="loading" class="p-8 text-center">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
          <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем уведомления...</p>
        </div>

        <div v-else-if="loadError" class="p-4 text-sm text-[color:var(--storefront-error-text,#b91c1c)]" role="alert">
            <p>{{ loadError }}</p>
            <button type="button" class="btn-secondary mt-3" @click="loadNotifications()">Повторить</button>
          </div>
          <div v-else-if="notifications.length === 0" class="p-8 text-center">
          <svg class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-5 5v-5zM9 9l3-3 3 3M9 9a9.02 9.02 0 000 6.4"/>
          </svg>
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-2">Уведомления не найдены</h3>
          <p class="text-[color:var(--storefront-text-muted,#4b5563)]">Попробуйте изменить фильтры или проверьте позже</p>
        </div>

        <div v-else class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
          <div
            v-for="notification in notifications"
            :key="notification.id"
            :data-notification-id="notification.id"
            @click="handleNotificationClick(notification)"
            @keydown.enter.self="handleNotificationClick(notification)"
            @keydown.space.self.prevent="handleNotificationClick(notification)"
            tabindex="0"
            role="link"
            :class="[
              'p-6 cursor-pointer hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--storefront-focus,#3b82f6)]',
              !notification.is_read ? 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border-l-4 border-l-[color:var(--storefront-border,#3b82f6)]' : ''
            ]"
          >
            <div class="flex items-start space-x-4">
              <!-- Icon -->
              <div class="flex-shrink-0 mt-1">
                <div :class="getNotificationIconClass(notification.type, notification.data)" class="w-10 h-10 rounded-full flex items-center justify-center">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path :d="getNotificationIconPath(notification.type)" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                  </svg>
                </div>
              </div>

              <!-- Content -->
              <div class="flex-1 min-w-0">
                <div class="flex items-start justify-between">
                  <div class="flex-1">
                    <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)] mb-1">{{ notification.title }}</h4>
                    <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-2">{{ notification.message }}</p>
                  </div>
                  <div class="flex items-center space-x-2 ml-4">
                    <div v-if="!notification.is_read" class="w-2 h-2 bg-[color:rgb(var(--storefront-primary-rgb,59_130_246)/var(--tw-bg-opacity,1))] rounded-full"></div>
                    <button
                      @click.stop="deleteNotification(notification.id)"
                      class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#dc2626)] p-1"
                      title="Удалить"
                    >
                      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                      </svg>
                    </button>
                  </div>
                </div>
                
                <div class="flex items-center justify-between mt-3">
                  <span class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ formatDate(notification.created_at) }}</span>
                  <div class="flex items-center space-x-2">
                    <span
                      v-if="(notification.data?.request_number || notification.application_display_number)"
                      class="inline-flex px-2 py-1 text-xs font-medium bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)] rounded"
                    >
                      Заявка {{ (notification.data?.request_number || notification.application_display_number) }}
                    </span>
                    <span
                      :class="getNotificationTypeClass(notification.type, notification.data)"
                      class="inline-flex px-2 py-1 text-xs font-medium rounded"
                    >
                      {{ getNotificationTypeText(notification.type) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="pagination.pages > 1" class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-6 py-3 flex items-center justify-between border-t border-[color:var(--storefront-border,#e5e7eb)]">
          <div class="flex flex-1 items-center justify-between">
            <div>
              <p class="text-sm text-[color:var(--storefront-text,#374151)]">
                Показано
                <span class="font-medium">{{ (pagination.page - 1) * pagination.limit + 1 }}</span>
                до
                <span class="font-medium">{{ Math.min(pagination.page * pagination.limit, pagination.total) }}</span>
                из
                <span class="font-medium">{{ pagination.total }}</span>
                результатов
              </p>
            </div>
            <div>
              <nav class="relative z-0 inline-flex rounded-md shadow-sm -space-x-px">
                <button 
                  @click="changePage(pagination.page - 1)"
                  :disabled="pagination.page <= 1"
                  class="storefront-action-secondary relative inline-flex items-center px-2 py-2 rounded-l-md border border-[color:var(--storefront-secondary-border,#d1d5db)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-sm font-medium text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <span class="sr-only">Предыдущая</span>
                  <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clip-rule="evenodd" />
                  </svg>
                </button>
                
                <button 
                  v-for="page in getVisiblePages()" 
                  :key="page"
                  @click="changePage(page)"
                  :class="page === pagination.page ? 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-primary-border,#3b82f6)] text-[color:var(--storefront-primary-foreground,#2563eb)]' : 'bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))] border-[color:var(--storefront-primary-border,#d1d5db)] text-[color:var(--storefront-primary-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]'"
                  class="storefront-action-secondary relative inline-flex items-center px-4 py-2 border text-sm font-medium"
                >
                  {{ page }}
                </button>
                
                <button 
                  @click="changePage(pagination.page + 1)"
                  :disabled="pagination.page >= pagination.pages"
                  class="storefront-action-secondary relative inline-flex items-center px-2 py-2 rounded-r-md border border-[color:var(--storefront-secondary-border,#d1d5db)] bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-sm font-medium text-[color:var(--storefront-secondary-foreground,#6b7280)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <span class="sr-only">Следующая</span>
                  <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd" />
                  </svg>
                </button>
              </nav>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { notificationActionRoute } from '~/features/notifications/actionRoute'
import { createNotificationsApi } from '~/features/notifications/api/notificationsApi'
import type { NotificationsQuery, NotificationItem as ApiNotificationItem } from '~/features/notifications/api/notificationsApi'
import { useNotificationTypes } from '~/features/notifications/composables/useNotificationTypes'
import type { UUID } from '~/types/ids'

definePageMeta({
  middleware: 'auth'
})

const config = useRuntimeConfig()
const router = useRouter()
const { publicRoute } = useStorefront()
const toast = useToast()
const api = createNotificationsApi(config)
const { getNotificationIconClass, getNotificationTypeClass, getNotificationTypeText, getNotificationIconPath, notificationTypeOptions } = useNotificationTypes()

// Reactive data
const loading = ref(true)
const markingAllAsRead = ref(false)
const loadError = ref('')
let listRequestVersion = 0
const notifications = ref<ApiNotificationItem[]>([])
const totalCount = ref(0)
const unreadCount = ref(0)
const receivedTodayCount = ref(0)
const thisWeekCount = ref(0)

const filters = ref<{ is_read: string; type: import('~/features/notifications/types').NotificationType | ''; period: string }>({
  is_read: '',
  type: '',
  period: ''
})

const pagination = ref({
  page: 1,
  limit: 20,
  total: 0,
  pages: 0
})

// Methods
const formatDate = (date: string) => {
  const now = new Date()
  const notificationDate = new Date(date)
  const diffInHours = (now.getTime() - notificationDate.getTime()) / (1000 * 60 * 60)

  if (diffInHours < 1) {
    const diffInMinutes = Math.floor(diffInHours * 60)
    return diffInMinutes <= 1 ? 'Только что' : `${diffInMinutes} мин. назад`
  } else if (diffInHours < 24) {
    return `${Math.floor(diffInHours)} ч. назад`
  } else if (diffInHours < 48) {
    return 'Вчера'
  } else {
    return notificationDate.toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }
}

const loadNotifications = async () => {
  const version = ++listRequestVersion
  loadError.value = ''
  loading.value = true
  try {
    const query: NotificationsQuery = {
      page: pagination.value.page,
      limit: pagination.value.limit
    }
    if (filters.value.is_read) query.is_read = filters.value.is_read
    if (filters.value.type) query.type = filters.value.type
    if (filters.value.period) query.period = filters.value.period

    const response = await api.getNotifications(query)
    if (version !== listRequestVersion) return
    notifications.value = response.notifications
    pagination.value = response.pagination
  } catch (error: unknown) {
    if (version !== listRequestVersion) return
    loadError.value = 'Не удалось загрузить уведомления. Повторите попытку.'
    console.error('Error loading notifications:', error)
    toast.apiError(error as string)
  } finally {
    if (version === listRequestVersion) loading.value = false
  }
}

const loadStats = async () => {
  try {
    const [countResp, todayResp, weekResp] = await Promise.all([
      api.getCount(),
      api.getNotifications({ period: 'today', limit: 1 }),
      api.getNotifications({ period: 'week', limit: 1 }),
    ])

    totalCount.value = countResp.total_count
    unreadCount.value = countResp.unread_count
    receivedTodayCount.value = todayResp.pagination?.total || 0
    thisWeekCount.value = weekResp.pagination?.total || 0
  } catch (error) {
    console.error('Error loading stats:', error)
  }
}

const refreshNotifications = async () => {
  await Promise.all([loadNotifications(), loadStats()])
  toast.success('Уведомления обновлены')
}

const markAllAsRead = async () => {
  if (unreadCount.value === 0) return

  markingAllAsRead.value = true
  try {
    await api.markAllAsRead()
    notifications.value.forEach(n => {
      n.is_read = true
      n.read_at = new Date().toISOString()
    })
    unreadCount.value = 0
    toast.success('Все уведомления отмечены как прочитанные')
  } catch (error: unknown) {
    console.error('Error marking all as read:', error)
    toast.apiError(error as string)
  } finally {
    markingAllAsRead.value = false
  }
}

const handleNotificationClick = async (notification: ApiNotificationItem) => {
  if (!notification.is_read) {
    try {
      await api.markAsRead(notification.id)
      notification.is_read = true
      notification.read_at = new Date().toISOString()
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch (error) {
      console.error('Error marking notification as read:', error)
    }
  }

  const actionRoute = notificationActionRoute(notification.action_url, publicRoute, notification.id)
  if (actionRoute) {
    await router.push(actionRoute)
  }
}

const deleteNotification = async (notificationId: UUID) => {
  if (!confirm('Вы уверены, что хотите удалить это уведомление?')) return

  try {
    await api.deleteNotification(notificationId)
    const index = notifications.value.findIndex(n => n.id === notificationId)
    if (index > -1) {
      if (!notifications.value[index].is_read) {
        unreadCount.value = Math.max(0, unreadCount.value - 1)
      }
      notifications.value.splice(index, 1)
      totalCount.value = Math.max(0, totalCount.value - 1)
    }
    toast.success('Уведомление удалено')
  } catch (error: unknown) {
    console.error('Error deleting notification:', error)
    toast.apiError(error as string)
  }
}

const clearFilters = () => {
  filters.value = {
    is_read: '',
    type: '',
    period: ''
  }
  pagination.value.page = 1
  loadNotifications()
}

const changePage = (page: number) => {
  if (page >= 1 && page <= pagination.value.pages) {
    pagination.value.page = page
    loadNotifications()
  }
}

const getVisiblePages = () => {
  const current = pagination.value.page
  const total = pagination.value.pages
  const visible = []
  
  let start = Math.max(1, current - 2)
  let end = Math.min(total, current + 2)
  
  if (end - start < 4) {
    if (start === 1) {
      end = Math.min(total, start + 4)
    } else {
      start = Math.max(1, end - 4)
    }
  }
  
  for (let i = start; i <= end; i++) {
    visible.push(i)
  }
  
  return visible
}

// Watchers
watch(filters, () => {
  pagination.value.page = 1
  loadNotifications()
}, { deep: true })

// Initialize
onMounted(() => {
  Promise.all([loadNotifications(), loadStats()])
})

// Meta
useSeoMeta({
  title: 'Уведомления - CarCraft Multileasing',
  description: 'Управление уведомлениями в системе CarCraft Multileasing'
})
</script>
