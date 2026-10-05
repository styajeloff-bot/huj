<template>
  <div data-storefront-block="client.auth" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)]">Настройки Email уведомлений</h1>
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">
          Управляйте тем, какие уведомления вы хотите получать по электронной почте
        </p>
      </div>

      <!-- Main Settings Card -->
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow">
        <!-- Header -->
        <div class="px-6 py-4 border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h2 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Параметры уведомлений</h2>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Вы также будете получать уведомления в системе независимо от этих настроек
          </p>
        </div>

        <!-- Loading State -->
        <div v-if="loading" class="p-8 text-center">
          <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
          <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем настройки...</p>
        </div>

        <!-- Settings Form -->
        <form v-else @submit.prevent="savePreferences" class="p-6">
          <!-- Email Frequency -->
          <div class="mb-8">
            <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-4">🕒 Частота отправки</h3>
            <div class="space-y-3">
              <label class="flex items-center">
                <input 
                  v-model="preferences.email_frequency" 
                  value="immediate" 
                  type="radio" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)]"
                >
                <div class="ml-3">
                  <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">Немедленно</div>
                  <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Получать уведомления сразу после событий</div>
                </div>
              </label>
              <label class="flex items-center">
                <input 
                  v-model="preferences.email_frequency" 
                  value="daily" 
                  type="radio" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)]"
                >
                <div class="ml-3">
                  <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">Ежедневная сводка</div>
                  <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Получать сводку один раз в день</div>
                </div>
              </label>
              <label class="flex items-center">
                <input 
                  v-model="preferences.email_frequency" 
                  value="weekly" 
                  type="radio" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)]"
                >
                <div class="ml-3">
                  <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">Еженедельная сводка</div>
                  <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Получать сводку один раз в неделю</div>
                </div>
              </label>
            </div>
          </div>

          <div class="border-t border-[color:var(--storefront-border,#e5e7eb)] pt-8"></div>

          <!-- Notification Types -->
          <div class="space-y-8">
            <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">📧 Типы уведомлений</h3>

            <!-- Application Status -->
            <div class="flex items-start">
              <div class="flex items-center h-5">
                <input 
                  v-model="preferences.application_status_emails" 
                  type="checkbox" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
              </div>
              <div class="ml-3">
                <label class="text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                  🚗 Статус заявок на лизинг
                </label>
                <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  Уведомления об изменении статуса ваших заявок (подача, рассмотрение, одобрение, отклонение)
                </p>
              </div>
            </div>

            <!-- Document Requests -->
            <div class="flex items-start">
              <div class="flex items-center h-5">
                <input 
                  v-model="preferences.document_request_emails" 
                  type="checkbox" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
              </div>
              <div class="ml-3">
                <label class="text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                  📄 Запросы документов
                </label>
                <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  Уведомления о необходимости предоставить дополнительные документы
                </p>
              </div>
            </div>

            <!-- Document Status -->
            <div class="flex items-start">
              <div class="flex items-center h-5">
                <input 
                  v-model="preferences.document_status_emails" 
                  type="checkbox" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
              </div>
              <div class="ml-3">
                <label class="text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                  ✅ Статус документов
                </label>
                <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  Уведомления об одобрении, отклонении или необходимости доработки документов
                </p>
              </div>
            </div>

            <!-- Leasing Approval -->
            <div class="flex items-start">
              <div class="flex items-center h-5">
                <input 
                  v-model="preferences.leasing_approval_emails" 
                  type="checkbox" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
              </div>
              <div class="ml-3">
                <label class="text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                  🎉 Решения по лизингу
                </label>
                <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  Окончательные решения лизинговых компаний по вашим заявкам
                </p>
              </div>
            </div>

            <label class="flex items-start gap-3 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] p-4">
              <input v-model="preferences.exchange_emails" type="checkbox" class="storefront-control mt-1 h-4 w-4 rounded border-[color:var(--storefront-border,#d1d5db)] text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)]">
              <span><span class="block text-sm font-medium text-[color:var(--storefront-text,#111827)]">Уведомления Биржи</span>
              <span class="mt-1 block text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Заявки, ставки, изменения и напоминания о сроках. Уведомления в личном кабинете сохраняются независимо от этой настройки.</span></span>
            </label>

            <!-- System Notifications -->
            <div class="flex items-start">
              <div class="flex items-center h-5">
                <input 
                  v-model="preferences.system_emails" 
                  type="checkbox" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
              </div>
              <div class="ml-3">
                <label class="text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                  ⚙️ Системные уведомления
                </label>
                <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  Важные системные сообщения, обновления безопасности и изменения в сервисе
                </p>
              </div>
            </div>

            <!-- Weekly Digest -->
            <div class="flex items-start">
              <div class="flex items-center h-5">
                <input 
                  v-model="preferences.weekly_digest" 
                  type="checkbox" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
              </div>
              <div class="ml-3">
                <label class="text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                  📊 Еженедельная сводка
                </label>
                <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  Еженедельный отчет о ваших заявках, документах и активности в системе
                </p>
              </div>
            </div>

            <!-- Marketing Emails -->
            <div class="flex items-start">
              <div class="flex items-center h-5">
                <input 
                  v-model="preferences.marketing_emails" 
                  type="checkbox" 
                  class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
                >
              </div>
              <div class="ml-3">
                <label class="text-sm font-medium text-[color:var(--storefront-label,#111827)] cursor-pointer">
                  📢 Маркетинговые сообщения
                </label>
                <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                  Новости компании, специальные предложения и информация о новых услугах
                </p>
              </div>
            </div>
          </div>

          <!-- Error Message -->
          <div v-if="error" class="mt-6 p-4 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg">
            <p class="text-sm text-[color:var(--storefront-error-text,#991b1b)]">{{ error }}</p>
          </div>

          <!-- Actions -->
          <div class="mt-8 flex items-center justify-between pt-6 border-t border-[color:var(--storefront-border,#e5e7eb)]">
            <div class="flex items-center space-x-4">
              <span v-if="lastUpdated" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                Последнее обновление: {{ formatDate(lastUpdated) }}
              </span>
            </div>
            <div class="flex space-x-3">
              <button
                type="button"
                @click="resetToDefaults"
                class="btn-secondary"
              >
                Сбросить по умолчанию
              </button>
              <button
                type="submit" 
                :disabled="saving"
                class="btn-primary"
              >
                <span v-if="saving">
                  <svg class="animate-spin -ml-1 mr-3 h-4 w-4 text-[color:var(--storefront-primary-icon,#ffffff)] inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Сохраняем...
                </span>
                <span v-else>Сохранить настройки</span>
              </button>
            </div>
          </div>
        </form>
      </div>

      <!-- Test Email Section (Admin Only) -->
      <div v-if="authStore.user?.role === 'carcraft_employee'" class="mt-8 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow">
        <div class="px-6 py-4 border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h2 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">🧪 Тестирование Email</h2>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
            Отправить тестовое уведомление для проверки работы email сервиса
          </p>
        </div>
        <div class="p-6">
          <button
            @click="sendTestEmail"
            :disabled="sendingTest"
            class="btn-secondary"
          >
            <span v-if="sendingTest">
              <svg class="animate-spin -ml-1 mr-3 h-4 w-4 inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Отправляем...
            </span>
            <span v-else>📧 Отправить тестовое уведомление</span>
          </button>
        </div>
      </div>

      <!-- Email Statistics (Admin Only) -->
      <div v-if="authStore.user?.role === 'carcraft_employee'" class="mt-8 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow">
        <div class="px-6 py-4 border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h2 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">📊 Статистика Email</h2>
        </div>
        <div class="p-6">
          <div v-if="emailStats" class="grid grid-cols-1 md:grid-cols-4 gap-6">
            <div class="text-center">
              <div class="text-2xl font-bold text-[color:var(--storefront-text,#111827)]">{{ emailStats.total_emails }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Всего уведомлений к отправке</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ emailStats.delivery_rate }}%</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Успешно принято SMTP</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-[color:var(--storefront-text-muted,#2563eb)]">{{ emailStats.failed_emails }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Ошибки отправки</div>
            </div>
            <div class="text-center">
              <div class="text-2xl font-bold text-[color:var(--storefront-info-text,#9333ea)]">{{ emailStats.today_emails }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Сегодня</div>
            </div>
          </div>
          <p v-if="emailStats" class="mt-4 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Принято SMTP: {{ emailStats.sent_emails }}. Пропущено по настройкам, доступу или актуальности: {{ emailStats.skipped_emails }}. Доля успеха рассчитана среди завершённых попыток. Доставка в ящик и открытия не отслеживаются.</p>
          <button
            @click="loadEmailStats"
            class="mt-4 btn-secondary text-sm"
          >
            Обновить статистику
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { createEmailPreferencesApi } from '~/features/email-preferences/api/emailPreferencesApi'
import type { EmailPreferences, EmailStats, ApiError } from '~/types'
definePageMeta({
  middleware: 'auth'
})

const config = useRuntimeConfig()
const api = createEmailPreferencesApi(config)
const authStore = useAuthStore()
const toast = useToast()

// Reactive data
const loading = ref(true)
const saving = ref(false)
const sendingTest = ref(false)
const error = ref('')
const lastUpdated = ref<string | null>(null)
const emailStats = ref<EmailStats | null>(null)

const preferences = ref({
  application_status_emails: true,
  document_request_emails: true,
  document_status_emails: true,
  leasing_approval_emails: true,
  exchange_emails: true,
  system_emails: true,
  weekly_digest: true,
  marketing_emails: false,
  email_frequency: 'immediate'
})

// Methods
const formatDate = (date: string | null) => {
  if (!date) return ''
  return new Date(date).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const loadPreferences = async () => {
  loading.value = true
  try {
    const response = await api.getPreferences()

    preferences.value = response.preferences
    lastUpdated.value = response.preferences.updated_at || null
  } catch (err: unknown) {
    console.error('Error loading email preferences:', err)
    error.value = 'Ошибка при загрузке настроек'
  } finally {
    loading.value = false
  }
}

const savePreferences = async () => {
  saving.value = true
  error.value = ''

  try {
    const response = await api.savePreferences(preferences.value)

    preferences.value = response.preferences
    lastUpdated.value = response.preferences.updated_at || null
    toast.success('Настройки email успешно сохранены')
  } catch (err: unknown) {
    console.error('Error saving preferences:', err)
    error.value = (err as ApiError).data?.error || 'Ошибка при сохранении настроек'
  } finally {
    saving.value = false
  }
}

const resetToDefaults = () => {
  if (confirm('Вы уверены, что хотите сбросить настройки по умолчанию?')) {
    preferences.value = {
      application_status_emails: true,
      document_request_emails: true,
      document_status_emails: true,
      leasing_approval_emails: true,
      exchange_emails: true,
      system_emails: true,
      weekly_digest: true,
      marketing_emails: false,
      email_frequency: 'immediate'
    }
    toast.info('Настройки сброшены по умолчанию. Не забудьте сохранить изменения.')
  }
}

const sendTestEmail = async () => {
  sendingTest.value = true
  try {
    await api.sendTestEmail()
    toast.success('Тестовое письмо принято SMTP-сервером')
  } catch (err: unknown) {
    console.error('Error sending test email:', err)
    toast.apiError(err as string, 'Ошибка при отправке тестового email')
  } finally {
    sendingTest.value = false
  }
}

const loadEmailStats = async () => {
  try {
    const response = await api.getStats()

    emailStats.value = response.stats
  } catch (err: unknown) {
    console.error('Error loading email stats:', err)
  }
}

// Initialize
onMounted(async () => {
  await loadPreferences()
  
  // Load email stats for admin users
  if (authStore.user?.role === 'carcraft_employee') {
    await loadEmailStats()
  }
})

// Meta
useSeoMeta({
  title: 'Настройки Email - CarCraft Multileasing',
  description: 'Управление настройками email уведомлений'
})
</script>
