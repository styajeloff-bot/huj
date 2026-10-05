<template>
  <div class="min-h-screen bg-gray-50 py-8">
    <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
      <NuxtLink to="/admin/users" class="text-sm text-blue-600 hover:underline">
        ← К поиску
      </NuxtLink>

      <div class="mt-4 mb-6">
        <h1 class="text-3xl font-bold text-gray-900">
          Пользователь #{{ userId }}
        </h1>
      </div>

      <div v-if="loadingUser" class="bg-white rounded-lg shadow p-8 text-center">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        <p class="mt-2 text-gray-600">Загружаем данные пользователя...</p>
      </div>

      <div v-else-if="!user" class="bg-white rounded-lg shadow p-8 text-center text-gray-600">
        Пользователь не найден.
      </div>

      <div v-else class="space-y-6">
        <!-- Profile card + actions -->
        <div class="bg-white rounded-lg shadow p-6">
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div class="text-xl font-semibold text-gray-900">
                {{ user.name || '—' }}
              </div>
              <div class="mt-1 text-sm text-gray-600 space-y-0.5">
                <div v-if="user.phone">Телефон: {{ user.phone }}</div>
                <div v-if="user.email">Email: {{ user.email }}</div>
                <div v-if="user.role">Роль: {{ user.role }}</div>
                <div>
                  Статус:
                  <span
                    class="ml-1 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold"
                    :class="
                      user.is_active
                        ? 'bg-green-100 text-green-800'
                        : 'bg-red-100 text-red-800'
                    "
                  >
                    {{ user.is_active ? 'Активен' : 'Заблокирован' }}
                  </span>
                </div>
                <div v-if="user.mfa_enabled !== undefined">
                  MFA: {{ user.mfa_enabled ? 'включена' : 'выключена' }}
                </div>
              </div>
            </div>

            <div class="flex flex-col sm:flex-row gap-2">
              <button
                class="btn-secondary"
                :disabled="acting"
                @click="handleForceLogout"
              >
                Force logout
              </button>
              <button
                v-if="user.is_active"
                class="btn-danger"
                :disabled="acting"
                @click="handleDisable"
              >
                Отключить
              </button>
              <button
                v-else
                class="btn-primary"
                :disabled="acting"
                @click="handleEnable"
              >
                Включить
              </button>
            </div>
          </div>
        </div>

        <!-- Tabs -->
        <div class="bg-white rounded-lg shadow">
          <div class="border-b border-gray-200 px-6 pt-4">
            <nav class="flex gap-4">
              <button
                v-for="t in tabs"
                :key="t.id"
                class="px-3 py-2 text-sm font-medium border-b-2 transition-colors"
                :class="
                  activeTab === t.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                "
                @click="activeTab = t.id"
              >
                {{ t.label }}
              </button>
            </nav>
          </div>

          <div class="p-6">
            <div v-if="activeTab === 'sessions'">
              <div v-if="loadingSessions" class="text-center py-6">
                <div class="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600" />
              </div>

              <div v-else-if="sessions.length === 0" class="text-sm text-gray-600">
                Активных сессий нет.
              </div>

              <ul v-else class="divide-y divide-gray-200">
                <li
                  v-for="s in sessions"
                  :key="s.id"
                  class="py-3 flex items-start justify-between gap-4 flex-wrap"
                >
                  <div class="min-w-0">
                    <div class="text-sm font-medium text-gray-900">
                      {{ parseUa(s.userAgent).browser }} · {{ parseUa(s.userAgent).os }}
                    </div>
                    <div class="text-xs text-gray-500 mt-1 space-x-2">
                      <span v-if="s.ipAddress">IP: {{ s.ipAddress }}</span>
                      <span v-if="s.countryCode">{{ s.countryCode }}</span>
                      <span>· создана {{ formatDate(s.createdAt) }}</span>
                      <span v-if="s.lastUsedAt">
                        · активность {{ formatDate(s.lastUsedAt) }}
                      </span>
                    </div>
                  </div>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  createAdminAuthApi,
  type AdminSessionInfo,
  type AdminUserDetail
} from '~/features/admin/auth/api/adminAuthApi'

definePageMeta({
  layout: 'workspace',
  middleware: ['auth', 'require-admin']
})

useHead({ title: 'Пользователь — CarCraft Multileasing' })

const route = useRoute()
const config = useRuntimeConfig()
const api = createAdminAuthApi(config)
const toast = useToast()

const userId = computed(() => String(route.params.id))

const user = ref<AdminUserDetail | null>(null)
const sessions = ref<AdminSessionInfo[]>([])
const loadingUser = ref(true)
const loadingSessions = ref(true)
const acting = ref(false)

const tabs = [{ id: 'sessions', label: 'Сессии' }] as const
const activeTab = ref<(typeof tabs)[number]['id']>('sessions')

const loadUser = async () => {
  loadingUser.value = true
  try {
    const res = await api.getUser(userId.value)
    user.value = res.user
  } catch (err: any) {
    user.value = null
    if (err?.status !== 404) {
      toast.apiError(err, 'Не удалось загрузить пользователя')
    }
  } finally {
    loadingUser.value = false
  }
}

const loadSessions = async () => {
  loadingSessions.value = true
  try {
    const res = await api.getUserSessions(userId.value)
    sessions.value = res.sessions || []
  } catch (err) {
    toast.apiError(err as any, 'Не удалось загрузить сессии')
  } finally {
    loadingSessions.value = false
  }
}

const handleForceLogout = async () => {
  if (!confirm('Завершить все сессии пользователя?')) return
  acting.value = true
  try {
    await api.forceLogout(userId.value)
    toast.success('Все сессии пользователя завершены')
    await loadSessions()
  } catch (err) {
    toast.apiError(err as any, 'Не удалось завершить сессии')
  } finally {
    acting.value = false
  }
}

const handleDisable = async () => {
  if (!confirm('Отключить учётную запись пользователя? Он не сможет войти до повторной активации.')) return
  acting.value = true
  try {
    await api.disableUser(userId.value)
    toast.success('Пользователь отключён')
    await loadUser()
  } catch (err) {
    toast.apiError(err as any, 'Не удалось отключить пользователя')
  } finally {
    acting.value = false
  }
}

const handleEnable = async () => {
  if (!confirm('Включить учётную запись пользователя?')) return
  acting.value = true
  try {
    await api.enableUser(userId.value)
    toast.success('Пользователь включён')
    await loadUser()
  } catch (err) {
    toast.apiError(err as any, 'Не удалось включить пользователя')
  } finally {
    acting.value = false
  }
}

const parseUa = (ua?: string): { browser: string; os: string } => {
  if (!ua) return { browser: 'Неизвестный браузер', os: 'Неизвестная ОС' }
  let browser = 'Другой браузер'
  if (/Edg\//.test(ua)) browser = 'Edge'
  else if (/OPR\//.test(ua) || /Opera/.test(ua)) browser = 'Opera'
  else if (/YaBrowser/.test(ua)) browser = 'Яндекс.Браузер'
  else if (/Firefox\//.test(ua)) browser = 'Firefox'
  else if (/Chrome\//.test(ua)) browser = 'Chrome'
  else if (/Safari\//.test(ua)) browser = 'Safari'
  let os = 'Неизвестная ОС'
  if (/Windows NT 10/.test(ua)) os = 'Windows 10/11'
  else if (/Windows/.test(ua)) os = 'Windows'
  else if (/iPhone|iPad|iPod/.test(ua)) os = 'iOS'
  else if (/Mac OS X|Macintosh/.test(ua)) os = 'macOS'
  else if (/Android/.test(ua)) os = 'Android'
  else if (/Linux/.test(ua)) os = 'Linux'
  return { browser, os }
}

const formatDate = (iso?: string): string => {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return iso
  }
}

onMounted(async () => {
  await Promise.all([loadUser(), loadSessions()])
})
</script>
