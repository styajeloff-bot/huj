import { isUuid, type UUID } from '~/types/ids'
import { createSpecialEquipmentImportApi } from '../api/specialEquipmentImportApi'
import type {
  SpecialEquipmentImportApplyRequest,
  SpecialEquipmentImportCreateRequest,
  SpecialEquipmentImportJob,
  SpecialEquipmentImportProblem,
  SpecialEquipmentImportSource,
} from '../types'
import {
  acquireImportCreateIdempotencyKey,
  clearImportCreateIntent,
} from './importCreateIntent'

const RECOVERY_KEY = 'carcraft:special-equipment:import-upload:v1'

interface RecoveryState {
  jobId: UUID
  filename: string
  size: number
  lastModified: number
}

interface FetchFailure {
  data?: SpecialEquipmentImportProblem
  message?: string
  name?: string
  response?: { status?: number }
  status?: number
  statusCode?: number
}

const failureMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== 'object') return fallback
  const failure = error as FetchFailure
  return failure.data?.detail ?? failure.data?.title ?? failure.message ?? fallback
}

const isCreateConflict = (error: unknown): boolean => {
  if (!error || typeof error !== 'object') return false
  const failure = error as FetchFailure
  return (failure.statusCode ?? failure.status ?? failure.response?.status) === 409
}

const readRecovery = (): RecoveryState | null => {
  if (!import.meta.client) return null
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(RECOVERY_KEY) ?? 'null')
    if (!raw || typeof raw !== 'object') return null
    const data = raw as Record<string, unknown>
    if (!isUuid(data.jobId) || typeof data.filename !== 'string' || typeof data.size !== 'number' || typeof data.lastModified !== 'number') return null
    return { jobId: data.jobId, filename: data.filename, size: data.size, lastModified: data.lastModified }
  } catch {
    return null
  }
}

const isTerminalStatus = (status: string) => [
  'validation_failed', 'completed', 'completed_with_warnings', 'failed', 'cancelled',
].includes(status)

const digestBlob = async (blob: Blob): Promise<string> => {
  const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
  const binary = Array.from(new Uint8Array(digest), (byte) => String.fromCharCode(byte)).join('')
  return `sha-256=:${btoa(binary)}:`
}

export const useSpecialEquipmentImport = () => {
  const api = createSpecialEquipmentImportApi(useRuntimeConfig())
  const job = ref<SpecialEquipmentImportJob | null>(null)
  const selectedFile = shallowRef<File | null>(null)
  const recovery = ref<RecoveryState | null>(null)
  const etag = ref<string | null>(null)
  const uploading = ref(false)
  const paused = ref(false)
  const uploadError = ref('')
  const actionError = ref('')
  const actionMessage = ref('')
  const uploadedBytes = ref(0)
  const uploadSpeedBytes = ref(0)
  const uploadStartedAt = ref<number | null>(null)
  const activeControllers = new Set<AbortController>()
  let pollingTimer: ReturnType<typeof setTimeout> | null = null

  const source = computed<SpecialEquipmentImportSource | null>(() => job.value?.source ?? null)
  const progressPercent = computed(() => {
    const total = source.value?.bytesTotal ?? selectedFile.value?.size ?? 0
    return total > 0 ? Math.min(100, Math.round((uploadedBytes.value / total) * 100)) : 0
  })
  const etaSeconds = computed<number | null>(() => {
    const total = source.value?.bytesTotal ?? selectedFile.value?.size ?? 0
    if (uploadSpeedBytes.value <= 0 || uploadedBytes.value >= total) return null
    return Math.ceil((total - uploadedBytes.value) / uploadSpeedBytes.value)
  })
  const requiresFileReselection = computed(() => Boolean(recovery.value && job.value?.status === 'awaiting_upload' && !selectedFile.value))

  const persistRecovery = (file: File, jobId: UUID) => {
    if (!import.meta.client) return
    const state: RecoveryState = { jobId, filename: file.name, size: file.size, lastModified: file.lastModified }
    localStorage.setItem(RECOVERY_KEY, JSON.stringify(state))
    recovery.value = state
  }

  const clearRecovery = () => {
    if (import.meta.client) localStorage.removeItem(RECOVERY_KEY)
    recovery.value = null
  }

  const setJob = (next: SpecialEquipmentImportJob) => {
    job.value = next
    const bytes = next.source?.bytesReceived ?? next.counters.find((counter) => counter.unit === 'bytes')?.done ?? 0
    uploadedBytes.value = Math.max(uploadedBytes.value, bytes)
    if (isTerminalStatus(next.status) || next.status !== 'awaiting_upload') {
      if (next.status !== 'awaiting_upload') clearRecovery()
    }
  }

  const refreshJob = async (silent = false) => {
    if (!job.value) return null
    try {
      const response = await api.getImport(job.value.id, silent ? etag.value ?? undefined : undefined)
      etag.value = response.etag
      if (!response.notModified && response.data) setJob(response.data)
      return job.value
    } catch (error: unknown) {
      if (!silent) actionError.value = failureMessage(error, 'Не удалось получить состояние импорта.')
      return null
    }
  }

  const schedulePolling = (retryAfterSeconds = 3) => {
    if (pollingTimer) clearTimeout(pollingTimer)
    if (!job.value || isTerminalStatus(job.value.status) || job.value.status === 'awaiting_upload' || job.value.status === 'preview_ready') return
    pollingTimer = setTimeout(async () => {
      const response = job.value ? await api.getImport(job.value.id, etag.value ?? undefined).catch(() => null) : null
      if (response) {
        etag.value = response.etag
        if (!response.notModified && response.data) setJob(response.data)
        schedulePolling(response.retryAfterSeconds ?? 3)
      } else {
        schedulePolling(Math.min(15, retryAfterSeconds + 2))
      }
    }, Math.max(2, retryAfterSeconds) * 1000)
  }

  const selectFile = (file: File | null) => {
    uploadError.value = ''
    if (!file) {
      selectedFile.value = null
      return true
    }
    if (!file.name.toLowerCase().endsWith('.xlsx') || file.name.toLowerCase().endsWith('.xlsm')) {
      uploadError.value = 'Поддерживаются только файлы .xlsx без макросов.'
      return false
    }
    if (file.size <= 0 || file.size > 2 * 1024 * 1024 * 1024) {
      uploadError.value = 'Размер файла должен быть больше нуля и не превышать 2 ГБ.'
      return false
    }
    selectedFile.value = file
    return true
  }

  const calculateConfirmedBytes = (parts: Set<number>, partSize: number, fileSize: number): number => {
    let total = 0
    for (const partNumber of parts) {
      const start = (partNumber - 1) * partSize
      total += Math.max(0, Math.min(partSize, fileSize - start))
    }
    return total
  }

  const uploadSelectedFile = async () => {
    const currentJob = job.value
    const file = selectedFile.value
    if (!currentJob || !file || currentJob.status !== 'awaiting_upload') return
    uploading.value = true
    paused.value = false
    uploadError.value = ''
    actionMessage.value = ''
    uploadStartedAt.value = Date.now()

    try {
      const latestSource = await api.getSource(currentJob.id)
      if (!job.value) return
      job.value = { ...job.value, source: latestSource }
      const partSize = latestSource.partSize
      const totalParts = Math.ceil(file.size / partSize)
      const confirmed = new Set(latestSource.receivedParts)
      uploadedBytes.value = Math.max(latestSource.bytesReceived, calculateConfirmedBytes(confirmed, partSize, file.size))
      let nextPart = 1
      let firstError: unknown = null

      const worker = async () => {
        while (!paused.value && !firstError) {
          while (nextPart <= totalParts && confirmed.has(nextPart)) nextPart += 1
          if (nextPart > totalParts) return
          const partNumber = nextPart
          nextPart += 1
          const byteStart = (partNumber - 1) * partSize
          const byteEndExclusive = Math.min(file.size, byteStart + partSize)
          const chunk = file.slice(byteStart, byteEndExclusive)
          const controller = new AbortController()
          activeControllers.add(controller)
          try {
            const digest = await digestBlob(chunk)
            if (paused.value) return
            await api.putPart(currentJob.id, partNumber, chunk, {
              'Content-Range': `bytes ${byteStart}-${byteEndExclusive - 1}/${file.size}`,
              'Content-Digest': digest,
              'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            }, controller.signal)
            confirmed.add(partNumber)
            uploadedBytes.value = calculateConfirmedBytes(confirmed, partSize, file.size)
            const elapsed = Math.max(1, (Date.now() - (uploadStartedAt.value ?? Date.now())) / 1000)
            uploadSpeedBytes.value = Math.max(0, (uploadedBytes.value - latestSource.bytesReceived) / elapsed)
          } catch (error: unknown) {
            const isAbort = error instanceof DOMException && error.name === 'AbortError'
            if (!paused.value && !isAbort) {
              firstError = error
              for (const active of activeControllers) active.abort()
            }
          } finally {
            activeControllers.delete(controller)
          }
        }
      }

      const workerCount = Math.max(1, Math.min(latestSource.maxParallelParts, 3, totalParts))
      await Promise.all(Array.from({ length: workerCount }, () => worker()))
      if (paused.value) return
      if (firstError) throw firstError

      await api.completeSource(currentJob.id)
      await refreshJob()
      actionMessage.value = 'Файл полностью загружен. Началась проверка.'
      clearRecovery()
      schedulePolling()
    } catch (error: unknown) {
      uploadError.value = failureMessage(error, 'Загрузка прервалась. Уже подтверждённые части сохранены — можно повторить попытку.')
    } finally {
      uploading.value = false
      activeControllers.clear()
    }
  }

  const createAndUpload = async (request: Omit<SpecialEquipmentImportCreateRequest, 'filename' | 'size'>) => {
    const file = selectedFile.value
    if (!file) {
      uploadError.value = 'Выберите XLSX-файл.'
      return
    }
    actionError.value = ''
    actionMessage.value = ''
    const storage = import.meta.client ? localStorage : null
    if (!storage) {
      uploadError.value = 'Создание импорта доступно только в браузере.'
      return
    }
    try {
      const idempotencyKey = await acquireImportCreateIdempotencyKey(storage, file, request)
      const created = await api.createImport(
        { ...request, filename: file.name, size: file.size },
        idempotencyKey,
      )
      setJob(created)
      persistRecovery(file, created.id)
      clearImportCreateIntent(storage)
      await uploadSelectedFile()
    } catch (error: unknown) {
      if (isCreateConflict(error)) clearImportCreateIntent(storage)
      uploadError.value = failureMessage(error, 'Не удалось создать импорт.')
    }
  }

  const pauseUpload = () => {
    if (!uploading.value) return
    paused.value = true
    for (const controller of activeControllers) controller.abort()
    actionMessage.value = 'Загрузка приостановлена. Сервер уже сохранил подтверждённые части.'
  }

  const resumeUpload = async () => {
    paused.value = false
    await uploadSelectedFile()
  }

  const attachRecoveryFile = (file: File): boolean => {
    if (!recovery.value) return selectFile(file)
    if (file.name !== recovery.value.filename || file.size !== recovery.value.size || file.lastModified !== recovery.value.lastModified) {
      uploadError.value = 'Выбран другой файл. Для продолжения нужны те же имя, размер и дата изменения.'
      return false
    }
    return selectFile(file)
  }

  const restore = async () => {
    recovery.value = readRecovery()
    if (!recovery.value) return null
    try {
      const response = await api.getImport(recovery.value.jobId)
      etag.value = response.etag
      if (response.data) {
        setJob(response.data)
        clearImportCreateIntent(localStorage)
      }
      return job.value
    } catch {
      clearRecovery()
      return null
    }
  }

  const openJob = async (jobId: UUID) => {
    actionError.value = ''
    selectedFile.value = null
    const response = await api.getImport(jobId)
    etag.value = response.etag
    if (response.data) {
      setJob(response.data)
      if (import.meta.client) clearImportCreateIntent(localStorage)
    }
    schedulePolling(response.retryAfterSeconds ?? 3)
    return job.value
  }

  const startNewImport = () => {
    if (pollingTimer) clearTimeout(pollingTimer)
    for (const controller of activeControllers) controller.abort()
    job.value = null
    selectedFile.value = null
    etag.value = null
    uploadedBytes.value = 0
    uploadSpeedBytes.value = 0
    uploadError.value = ''
    actionError.value = ''
    actionMessage.value = ''
    paused.value = false
    uploading.value = false
    clearRecovery()
    if (import.meta.client) clearImportCreateIntent(localStorage)
  }

  const applyImport = async (request: SpecialEquipmentImportApplyRequest) => {
    if (!job.value?.previewHash) return
    actionError.value = ''
    actionMessage.value = ''
    try {
      setJob(await api.applyImport(job.value.id, job.value.previewHash, request))
      actionMessage.value = 'Применение началось. Дождитесь завершения обработки.'
      schedulePolling()
    } catch (error: unknown) {
      actionError.value = failureMessage(error, 'Не удалось применить импорт. Возможно, каталог изменился после проверки.')
      await refreshJob(true)
    }
  }

  const cancelImport = async () => {
    if (!job.value) return
    actionError.value = ''
    actionMessage.value = ''
    for (const controller of activeControllers) controller.abort()
    try {
      setJob(await api.cancelImport(job.value.id))
      clearRecovery()
      actionMessage.value = 'Импорт отменён. Данные каталога не изменены.'
    } catch (error: unknown) {
      actionError.value = failureMessage(error, 'Не удалось отменить импорт.')
    }
  }

  onBeforeUnmount(() => {
    if (pollingTimer) clearTimeout(pollingTimer)
    for (const controller of activeControllers) controller.abort()
  })

  return {
    api,
    job: readonly(job),
    selectedFile: readonly(selectedFile),
    recovery: readonly(recovery),
    uploading: readonly(uploading),
    paused: readonly(paused),
    uploadError: readonly(uploadError),
    actionError: readonly(actionError),
    actionMessage: readonly(actionMessage),
    uploadedBytes: readonly(uploadedBytes),
    uploadSpeedBytes: readonly(uploadSpeedBytes),
    progressPercent,
    etaSeconds,
    requiresFileReselection,
    selectFile,
    attachRecoveryFile,
    createAndUpload,
    pauseUpload,
    resumeUpload,
    restore,
    openJob,
    startNewImport,
    refreshJob,
    applyImport,
    cancelImport,
  }
}
