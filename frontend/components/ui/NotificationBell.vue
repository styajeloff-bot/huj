<template>
  <div data-storefront-block="client.notifications" class="relative">
    <button
      @click="toggleNotifications"
      class="storefront-action-ghost relative grid min-h-11 min-w-11 place-items-center rounded-lg p-2 text-[color:var(--storefront-primary-foreground,#4b5563)] transition-colors duration-200 hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] hover:text-[color:var(--storefront-primary-hover-foreground,#2563eb)]"
      title="Уведомления"
      :aria-label="unreadCount > 0 ? `Уведомления, ${unreadCount} непрочитанных` : 'Уведомления'"
    >
      <BellIcon class="w-5 h-5" />
      
      <!-- Unread Count Badge -->
      <span 
        v-if="unreadCount > 0"
        class="absolute -right-1 -top-1 flex h-5 min-w-5 animate-pulse items-center justify-center rounded-full bg-[color:rgb(var(--storefront-primary-rgb,239_68_68)/var(--tw-bg-opacity,1))] px-1 text-xs text-[color:var(--storefront-primary-foreground,#ffffff)]"
        aria-hidden="true"
      >
        {{ unreadCount > 99 ? '99+' : unreadCount }}
      </span>

      <!-- New Notification Indicator -->
      <div 
        v-if="hasNewNotifications"
        class="absolute -top-0.5 -right-0.5 w-3 h-3 bg-[color:rgb(var(--storefront-error-rgb,239_68_68)/var(--tw-bg-opacity,1))] rounded-full animate-ping"
        aria-hidden="true"
      ></div>
    </button>

    <!-- Notification Center -->
    <NotificationCenter
      :is-open="showNotifications"
      @close="showNotifications = false"
      @notification-click="handleNotificationUpdate"
    />
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { BellIcon } from '@heroicons/vue/24/outline'
import NotificationCenter from '~/components/ui/NotificationCenter.vue'

const config = useRuntimeConfig()
const authStore = useAuthStore()

// Reactive data
const showNotifications = ref(false)
const unreadCount = ref(0)
const hasNewNotifications = ref(false)
const lastCheckedTime = ref(new Date())
const checkInterval = ref<ReturnType<typeof setInterval> | null>(null)

// Methods
const toggleNotifications = () => {
  showNotifications.value = !showNotifications.value
  if (showNotifications.value) {
    hasNewNotifications.value = false
  }
}

const fetchUnreadCount = async () => {
  try {
    // Проверяем аутентификацию перед запросом
    if (!authStore.isAuthenticated) {
      unreadCount.value = 0
      hasNewNotifications.value = false
      return
    }

    const response = await $fetch<{ unread_count: number }>('/api/v1/notifications?fields=count', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const newUnreadCount = response.unread_count

    // Check if there are new notifications
    if (newUnreadCount > unreadCount.value) {
      hasNewNotifications.value = true
    }

    unreadCount.value = newUnreadCount
    lastCheckedTime.value = new Date()
  } catch (error: unknown) {
    console.error('Error fetching notification count:', error)

    // Если ошибка 401, сбрасываем счетчик
    if ((error as { status?: number }).status === 401) {
      unreadCount.value = 0
      hasNewNotifications.value = false
    }
  }
}

const handleNotificationUpdate = (event: { type: string; unreadCount?: number }) => {
  if (event.type === 'count-updated') {
    unreadCount.value = event.unreadCount ?? 0
    hasNewNotifications.value = false
  }
}

const startPeriodicCheck = () => {
  // Check for new notifications every 30 seconds, but only if authenticated
  if (authStore.isAuthenticated) {
    checkInterval.value = setInterval(fetchUnreadCount, 30000)
  }
}

const stopPeriodicCheck = () => {
  if (checkInterval.value) {
    clearInterval(checkInterval.value)
    checkInterval.value = null
  }
}

// Lifecycle hooks
onMounted(() => {
  if (authStore.isAuthenticated) {
    fetchUnreadCount()
    startPeriodicCheck()
  }
})

onUnmounted(() => {
  stopPeriodicCheck()
})

// Watch for auth changes
watch(() => authStore.isAuthenticated, (isAuthenticated) => {
  if (isAuthenticated) {
    fetchUnreadCount()
    startPeriodicCheck()
  } else {
    unreadCount.value = 0
    hasNewNotifications.value = false
    stopPeriodicCheck()
  }
})
</script>

<style scoped>
@keyframes ring {
  0% { transform: rotate(0deg); }
  10% { transform: rotate(15deg); }
  20% { transform: rotate(-10deg); }
  30% { transform: rotate(15deg); }
  40% { transform: rotate(-10deg); }
  50% { transform: rotate(5deg); }
  60% { transform: rotate(-5deg); }
  100% { transform: rotate(0deg); }
}

.notification-bell:hover {
  animation: ring 0.8s ease-in-out;
}
</style>
