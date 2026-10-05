import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  fetchApplicationStatusFunnel,
  type ApplicationStatusFunnelResponse,
  type ApplicationStatusFunnelSelectionMode,
} from '../api/analytics'

const REPORT_TIMEZONE = 'Europe/Moscow'
const RELOAD_DEBOUNCE_MS = 300

type FunnelErrorCode =
  | 'ANALYTICS_UNAVAILABLE'
  | 'HISTORY_NOT_AVAILABLE'
  | 'INVALID_DATE_RANGE'
  | 'PERIOD_TOO_LARGE'

export interface ApplicationStatusFunnelErrorDetails {
  code: FunnelErrorCode | string | null
  message: string
  historyAvailableFrom: string | null
}

export function resolveHistoryBoundaryClamp(
  details: ApplicationStatusFunnelErrorDetails,
  periodFrom: string,
  periodTo: string,
  allowAutoClamp: boolean,
): string | null {
  const watermark = details.historyAvailableFrom
  if (
    !allowAutoClamp
    || details.code !== 'HISTORY_NOT_AVAILABLE'
    || !watermark
    || watermark <= periodFrom
    || watermark > periodTo
  ) {
    return null
  }
  return watermark
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object'
    ? value as Record<string, unknown>
    : null
}

function readString(
  source: Record<string, unknown> | null,
  ...keys: string[]
): string | null {
  for (const key of keys) {
    const value = source?.[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

function formatRussianDate(value: string): string {
  const [year, month, day] = value.split('-')
  if (!year || !month || !day) return value
  return `${day}.${month}.${year}`
}

export function parseApplicationStatusFunnelError(
  error: unknown,
): ApplicationStatusFunnelErrorDetails {
  const root = asRecord(error)
  const data = asRecord(root?.data) ?? root
  const detail = asRecord(data?.detail)
  const payload = detail ?? data
  const code = readString(payload, 'error_code', 'errorCode', 'code')
  const historyAvailableFrom = readString(
    payload,
    'history_available_from',
    'historyAvailableFrom',
  ) ?? readString(data, 'history_available_from', 'historyAvailableFrom')

  if (code === 'HISTORY_NOT_AVAILABLE') {
    const suffix = historyAvailableFrom
      ? ` начиная с ${formatRussianDate(historyAvailableFrom)}`
      : ''
    return {
      code,
      historyAvailableFrom,
      message: `Достоверная история статусов доступна${suffix}. Выберите более поздний период.`,
    }
  }

  if (code === 'ANALYTICS_UNAVAILABLE' || root?.statusCode === 503 || data?.statusCode === 503) {
    return {
      code: code ?? 'ANALYTICS_UNAVAILABLE',
      historyAvailableFrom,
      message: 'Сервис аналитики временно недоступен. Попробуйте повторить запрос позже.',
    }
  }

  const fallbackByCode: Record<string, string> = {
    INVALID_DATE_RANGE: 'Дата начала периода не может быть позже даты окончания.',
    PERIOD_TOO_LARGE: 'Период отчёта не может превышать 366 дней.',
  }

  return {
    code,
    historyAvailableFrom,
    message: (code && fallbackByCode[code])
      || readString(payload, 'message', 'error')
      || readString(data, 'detail')
      || readString(root, 'message')
      || 'Не удалось загрузить воронку. Попробуйте повторить запрос.',
  }
}

export function getMoscowPeriodDefaults(now = new Date()): {
  periodFrom: string
  periodTo: string
} {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: REPORT_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)

  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? ''
  const year = part('year')
  const month = part('month')
  const day = part('day')

  return {
    periodFrom: `${year}-${month}-01`,
    periodTo: `${year}-${month}-${day}`,
  }
}

export function useApplicationStatusFunnel() {
  const defaults = getMoscowPeriodDefaults()
  const periodFrom = ref(defaults.periodFrom)
  const periodTo = ref(defaults.periodTo)
  const selectionMode = ref<ApplicationStatusFunnelSelectionMode>('created_in_period')
  const data = ref<ApplicationStatusFunnelResponse | null>(null)
  const isLoading = ref(true)
  const errorCode = ref<string | null>(null)
  const errorMessage = ref('')
  const historyAvailableFrom = ref<string | null>(null)

  let activeController: AbortController | null = null
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let requestToken = 0
  let suppressNextFilterSchedule = false

  const rows = computed(() => data.value?.rows ?? [])
  const selectedCount = computed(() => data.value?.selectedCount ?? 0)
  const isHistoryUnavailable = computed(
    () => errorCode.value === 'HISTORY_NOT_AVAILABLE',
  )

  function setLocalError(code: FunnelErrorCode, message: string) {
    isLoading.value = false
    errorCode.value = code
    errorMessage.value = message
  }

  async function loadFunnel(allowHistoryAutoClamp = true) {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    activeController?.abort()

    if (!periodFrom.value || !periodTo.value) {
      setLocalError('INVALID_DATE_RANGE', 'Укажите обе даты отчётного периода.')
      return
    }
    if (periodFrom.value > periodTo.value) {
      setLocalError(
        'INVALID_DATE_RANGE',
        'Дата начала периода не может быть позже даты окончания.',
      )
      return
    }
    if (
      historyAvailableFrom.value
      && periodFrom.value < historyAvailableFrom.value
    ) {
      setLocalError(
        'HISTORY_NOT_AVAILABLE',
        `Достоверная история статусов доступна начиная с ${formatRussianDate(historyAvailableFrom.value)}. Выберите более поздний период.`,
      )
      return
    }

    const controller = new AbortController()
    activeController = controller
    const token = ++requestToken
    isLoading.value = true
    errorCode.value = null
    errorMessage.value = ''

    try {
      const result = await fetchApplicationStatusFunnel({
        periodFrom: periodFrom.value,
        periodTo: periodTo.value,
        selectionMode: selectionMode.value,
      }, controller.signal)

      if (controller.signal.aborted || token !== requestToken) return
      data.value = result
      historyAvailableFrom.value = result.historyAvailableFrom
      isLoading.value = false
    } catch (error: unknown) {
      if (controller.signal.aborted || token !== requestToken) return
      const details = parseApplicationStatusFunnelError(error)
      if (details.historyAvailableFrom) {
        historyAvailableFrom.value = details.historyAvailableFrom
      }
      const clampedPeriodFrom = resolveHistoryBoundaryClamp(
        details,
        periodFrom.value,
        periodTo.value,
        allowHistoryAutoClamp,
      )
      if (clampedPeriodFrom) {
        suppressNextFilterSchedule = true
        periodFrom.value = clampedPeriodFrom
        await loadFunnel(false)
        return
      }
      errorCode.value = details.code
      errorMessage.value = details.message
      isLoading.value = false
    }
  }

  function scheduleLoad() {
    if (debounceTimer) clearTimeout(debounceTimer)
    activeController?.abort()
    requestToken += 1
    isLoading.value = true
    errorCode.value = null
    errorMessage.value = ''
    debounceTimer = setTimeout(() => {
      void loadFunnel()
    }, RELOAD_DEBOUNCE_MS)
  }

  function refresh() {
    void loadFunnel()
  }

  watch([periodFrom, periodTo, selectionMode], () => {
    if (suppressNextFilterSchedule) {
      suppressNextFilterSchedule = false
      return
    }
    scheduleLoad()
  })

  onMounted(() => {
    void loadFunnel()
  })

  onBeforeUnmount(() => {
    requestToken += 1
    if (debounceTimer) clearTimeout(debounceTimer)
    activeController?.abort()
  })

  return {
    periodFrom,
    periodTo,
    selectionMode,
    data,
    rows,
    selectedCount,
    isLoading,
    errorCode,
    errorMessage,
    historyAvailableFrom,
    isHistoryUnavailable,
    refresh,
  }
}
