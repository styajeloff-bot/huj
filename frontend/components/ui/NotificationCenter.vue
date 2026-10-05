<template>
  <div data-storefront-block="client.notifications" v-if="isOpen" class="fixed inset-0 z-50 overflow-hidden">
    <!-- Backdrop -->
    <div class="absolute inset-0 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/var(--tw-bg-opacity,1))] bg-opacity-25" @click="close"></div>
    
    <!-- Notification Panel -->
    <div class="absolute right-0 top-0 h-full w-full max-w-md bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-xl">
      <div class="flex flex-col h-full">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h2 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Уведомления</h2>
          <div class="flex items-center space-x-2">
            <button
              v-if="unreadCount > 0"
              @click="markAllAsRead"
              class="storefront-action-ghost text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
              :disabled="markingAllAsRead"
            >
              {{ markingAllAsRead ? 'Отмечаем...' : 'Прочитать все' }}
            </button>
            <button @click="close" aria-label="Закрыть уведомления" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)]">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Filters -->
        <div class="p-4 border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <div class="flex flex-wrap gap-2">
            <button
              @click="currentFilter = 'all'"
              :class="currentFilter === 'all' ? 'bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#1e40af)]' : 'bg-[color:rgb(var(--storefront-primary-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#374151)]'"
              class="storefront-action-ghost px-3 py-1 text-xs font-medium rounded-full hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]"
            >
              Все ({{ totalCount }})
            </button>
            <button
              @click="currentFilter = 'unread'"
              :class="currentFilter === 'unread' ? 'bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#1e40af)]' : 'bg-[color:rgb(var(--storefront-primary-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#374151)]'"
              class="storefront-action-ghost px-3 py-1 text-xs font-medium rounded-full hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]"
            >
              Непрочитанные ({{ unreadCount }})
            </button>
            <select
              v-model="typeFilter"
              aria-label="Тип уведомлений"
              class="storefront-control text-xs border border-[color:var(--storefront-border,#d1d5db)] rounded px-2 py-1 select-field rounded-full"
              style="width: auto;"
            >
              <option value="">Все типы</option>
              <option v-for="option in notificationTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
        </div>

        <!-- Notifications List -->
        <div class="flex-1 overflow-y-auto">
          <div v-if="loading" class="p-4 text-center">
            <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
            <p class="mt-2 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем уведомления...</p>
          </div>

          <div v-else-if="loadError" class="p-4 text-sm text-[color:var(--storefront-error-text,#b91c1c)]" role="alert">
            <p>{{ loadError }}</p>
            <button type="button" class="btn-secondary mt-3" @click="loadNotifications(true)">Повторить</button>
          </div>
          <div v-else-if="filteredNotifications.length === 0" class="p-4 text-center">
            <BellSnoozeIcon class="mx-auto h-12 w-12 text-[color:var(--storefront-icon,#9ca3af)] mb-3" />
            <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
              {{ currentFilter === 'unread' ? 'Нет непрочитанных уведомлений' : 'Уведомления отсутствуют' }}
            </p>
          </div>

          <div v-else class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
            <div
              v-for="notification in filteredNotifications"
              :key="notification.id"
              :data-notification-id="notification.id"
              @click="handleNotificationClick(notification)"
            @keydown.enter.self="handleNotificationClick(notification)"
            @keydown.space.self.prevent="handleNotificationClick(notification)"
            tabindex="0"
            role="link"
              :class="[
                'p-4 cursor-pointer hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--storefront-focus,#3b82f6)]',
                !notification.is_read ? 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border-l-4 border-l-[color:var(--storefront-border,#3b82f6)]' : ''
              ]"
            >
              <div class="flex items-start space-x-3">
                <!-- Notification Icon -->
                <div class="flex-shrink-0 mt-1">
                  <div :class="getNotificationIconClass(notification.type, notification.data)" class="w-8 h-8 rounded-full flex items-center justify-center">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                      <path :d="getNotificationIconPath(notification.type)" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                    </svg>
                  </div>
                </div>

                <!-- Notification Content -->
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">{{ notification.title }}</p>
                  <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">{{ notification.message }}</p>
                  <div class="flex items-center justify-between mt-2">
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

                <!-- Unread Indicator -->
                <div v-if="!notification.is_read" class="flex-shrink-0">
                  <div class="w-2 h-2 bg-[color:rgb(var(--storefront-primary-rgb,59_130_246)/var(--tw-bg-opacity,1))] rounded-full"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="p-4 border-t border-[color:var(--storefront-border,#e5e7eb)]">
          <button
            @click="loadMore"
            v-if="hasMore && !loading"
            class="storefront-action-ghost w-full text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)] py-2"
          >
            Загрузить еще
          </button>
          <div v-if="hasMore && loading" class="text-center py-2">
            <div class="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStorefront } from '~/features/storefront'
import { notificationActionRoute } from '~/features/notifications/actionRoute'
import { BellSnoozeIcon } from '@heroicons/vue/24/outline'
import type { NotificationItem as Notification, NotificationType } from '~/features/notifications/types'
import { createNotificationsApi } from '~/features/notifications/api/notificationsApi'
import { useNotificationTypes } from '~/features/notifications/composables/useNotificationTypes'

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'notification-click'])

const config = useRuntimeConfig()
const router = useRouter()
const { publicRoute } = useStorefront()

// Reactive data
const loading = ref(false)
const markingAllAsRead = ref(false)
const loadError = ref('')
let listRequestVersion = 0
const notifications = ref<Notification[]>([])
const currentFilter = ref('all')
const typeFilter = ref<NotificationType | ''>('')
const totalCount = ref(0)
const unreadCount = ref(0)
const currentPage = ref(1)
const hasMore = ref(false)

// Computed
const filteredNotifications = computed(() => {
  let filtered = notifications.value

  if (currentFilter.value === 'unread') {
    filtered = filtered.filter(n => !n.is_read)
  }

  if (typeFilter.value) {
    filtered = filtered.filter(n => n.type === typeFilter.value)
  }

  return filtered
})

// Methods
const formatDate = (date: string): string => {
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
      month: '2-digit'
    })
  }
}

const api = createNotificationsApi(config)
const { getNotificationIconClass, getNotificationTypeClass, getNotificationTypeText, getNotificationIconPath, notificationTypeOptions } = useNotificationTypes()

const close = () => {
  emit('close')
}

const loadNotifications = async (reset = false) => {
  const version = ++listRequestVersion
  loadError.value = ''
  if (reset) {
    currentPage.value = 1
    notifications.value = []
  }

  loading.value = true

  try {
    const response = await api.getNotifications({
      page: currentPage.value,
      limit: 20,
      type: typeFilter.value,
      is_read: currentFilter.value === 'unread' ? 'false' : undefined,
    })

    if (version !== listRequestVersion) return
    if (reset) {
      notifications.value = response.notifications
    } else {
      notifications.value.push(...response.notifications)
    }

    hasMore.value = currentPage.value < response.pagination.pages
  } catch (error) {
    if (version !== listRequestVersion) return
    loadError.value = 'Не удалось загрузить уведомления. Повторите попытку.'
    console.error('Error loading notifications:', error)
  } finally {
    if (version === listRequestVersion) loading.value = false
  }
}

const loadNotificationCounts = async () => {
  try {
    const response = await api.getCount()

    totalCount.value = response.total_count
    unreadCount.value = response.unread_count
  } catch (error) {
    console.error('Error loading notification counts:', error)
  }
}

const loadMore = async () => {
  if (hasMore.value && !loading.value) {
    currentPage.value++
    await loadNotifications()
  }
}

const markAllAsRead = async () => {
  if (unreadCount.value === 0) return

  markingAllAsRead.value = true

  try {
    await api.markAllAsRead()

    // Update local state
    notifications.value.forEach(n => {
      n.is_read = true
      n.read_at = new Date().toISOString()
    })

    unreadCount.value = 0
    emit('notification-click', { type: 'count-updated', unreadCount: 0 })
  } catch (error) {
    console.error('Error marking all notifications as read:', error)
  } finally {
    markingAllAsRead.value = false
  }
}

const handleNotificationClick = async (notification: Notification) => {
  // Mark as read if not already read
  if (!notification.is_read) {
    try {
      await api.markAsRead(notification.id)

      notification.is_read = true
      notification.read_at = new Date().toISOString()
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      emit('notification-click', { type: 'count-updated', unreadCount: unreadCount.value })
    } catch (error) {
      console.error('Error marking notification as read:', error)
    }
  }

  // Navigate to action URL if provided
  const actionRoute = notificationActionRoute(notification.action_url, publicRoute, notification.id)
  if (actionRoute) {
    close()
    await router.push(actionRoute)
  }

  emit('notification-click', { type: 'clicked', notification })
}

// Watchers
watch([currentFilter, typeFilter], () => {
  loadNotifications(true)
})

watch(() => props.isOpen, (isOpen) => {
  if (isOpen) {
    loadNotifications(true)
    loadNotificationCounts()
  }
})

// Initialize when component is opened
onMounted(() => {
  if (props.isOpen) {
    loadNotifications(true)
    loadNotificationCounts()
  }
})
</script>
