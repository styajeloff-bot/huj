<template>
  <div data-storefront-block="client.auth" class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8">
    <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
      <div class="mb-8 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)]">
            Активные устройства
          </h1>
          <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">
            Список устройств и браузеров, с которых выполнен вход в ваш аккаунт.
          </p>
        </div>
        <button
          class="storefront-action-destructive btn-danger"
          :disabled="revokingAll"
          @click="handleRevokeAll"
        >
          {{ revokingAll ? 'Выходим...' : 'Выйти со всех устройств' }}
        </button>
      </div>

      <div v-if="loading" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-8 text-center">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]" />
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем сессии...</p>
      </div>

      <div v-else-if="sessions.length === 0" class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-8 text-center text-[color:var(--storefront-text-muted,#4b5563)]">
        Активных сессий не найдено.
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow p-5 flex items-start justify-between gap-4 flex-wrap"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-semibold text-[color:var(--storefront-text,#111827)]">
                {{ parseUa(session.userAgent).browser }}
              </span>
              <span class="text-[color:var(--storefront-text-muted,#6b7280)]">·</span>
              <span class="text-[color:var(--storefront-text,#374151)]">{{ parseUa(session.userAgent).os }}</span>
              <span
                v-if="isCurrent(session)"
                class="ml-2 inline-flex items-center rounded-full bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] px-2.5 py-0.5 text-xs font-medium text-[color:var(--storefront-success-text,#166534)]"
              >
                Это устройство
              </span>
            </div>

            <div class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)] space-x-3">
              <span v-if="session.ipAddress">IP: {{ session.ipAddress }}</span>
              <span v-if="session.countryCode">{{ session.countryCode }}</span>
            </div>

            <div class="mt-2 text-xs text-[color:var(--storefront-text-muted,#6b7280)] space-x-3">
              <span>Создана {{ formatRelative(session.createdAt) }}</span>
              <span v-if="session.lastUsedAt">
                · активность {{ formatRelative(session.lastUsedAt) }}
              </span>
              <span v-if="session.expiresAt">
                · истекает {{ formatDate(session.expiresAt) }}
              </span>
            </div>
          </div>

          <div>
            <button
              v-if="!isCurrent(session)"
              class="btn-secondary text-sm"
              :disabled="revokingId === session.id"
              @click="handleRevoke(session.id)"
            >
              {{ revokingId === session.id ? 'Выходим...' : 'Выйти с устройства' }}
            </button>
            <span v-else class="text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">Текущая сессия</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { createAuthApi, type SessionInfo } from '~/features/auth/api/authApi'

definePageMeta({ middleware: 'auth' })
useHead({ title: 'Активные устройства — CarCraft Multileasing' })

const config = useRuntimeConfig()
const api = createAuthApi(config)
const authStore = useAuthStore()
const toast = useToast()

const sessions = ref<SessionInfo[]>([])
const loading = ref(true)
const revokingId = ref<string | null>(null)
const revokingAll = ref(false)

const fetchSessions = async () => {
  loading.value = true
  try {
    const res = await api.listSessions()
    sessions.value = res.sessions || []
  } catch (err) {
    toast.apiError(err as any, 'Не удалось загрузить сессии')
  } finally {
    loading.value = false
  }
}

/**
 * The backend ideally sets `isCurrent`. As a fallback when it does not,
 * we fall back to matching `userAgent` + IP. This is best-effort — only
 * the backend can know for sure, because the UA can be shared between
 * devices (e.g. proxy, corporate network).
 */
const isCurrent = (session: SessionInfo): boolean => {
  if (typeof session.isCurrent === 'boolean') return session.isCurrent
  if (!process.client) return false
  const ua = session.userAgent
  return Boolean(ua && typeof navigator !== 'undefined' && navigator.userAgent === ua)
}

/**
 * Minimal UA parser — avoids pulling in ua-parser-js for a cosmetic label.
 * Covers the common cases; everything else falls back to "Другой браузер".
 */
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
    return new Date(iso).toLocaleDateString('ru-RU', {
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

const formatRelative = (iso?: string): string => {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = Date.now() - then
  if (diff < 60_000) return 'только что'
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `${mins} мин назад`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} ч назад`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} дн назад`
  return formatDate(iso)
}

const handleRevoke = async (id: string) => {
  if (!confirm('Выйти с выбранного устройства?')) return
  revokingId.value = id
  try {
    await api.revokeSession(id)
    toast.success('Сессия завершена')
    await fetchSessions()
  } catch (err) {
    toast.apiError(err as any, 'Не удалось завершить сессию')
  } finally {
    revokingId.value = null
  }
}

const handleRevokeAll = async () => {
  if (!confirm('Выйти со всех устройств? Вы будете разлогинены везде.')) return
  revokingAll.value = true
  try {
    await api.revokeAllSessions()
    toast.success('Выполнен выход со всех устройств')
    // Local state is gone too — this cleans it up client-side.
    await authStore.logout()
    navigateTo('/auth')
  } catch (err) {
    toast.apiError(err as any, 'Не удалось завершить все сессии')
  } finally {
    revokingAll.value = false
  }
}

onMounted(fetchSessions)
</script>
