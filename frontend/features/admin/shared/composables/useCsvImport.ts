import { ref, computed } from 'vue'
import { useToast } from '@/composables/useToast'
import { resolveImportErrorMessage } from '../importErrorMessage'

export type ImportStatus = 'queued' | 'parsing' | 'ingesting' | 'publishing' | 'done' | 'failed'

export interface ImportJob {
  id: string
  kind: string
  filename: string
  status: ImportStatus
  rows_total: number
  rows_done: number
  errors_count: number
  error_sample: string[]
  error: string | null
  created_at: string
  updated_at: string
}

export type TerminalImportJob = ImportJob & { status: 'done' | 'failed' }

interface UploadResponse {
  job_id: string
  status: string
}

const POLL_INTERVAL_MS = 1500

/**
 * Reusable composable for the async CSV import flow.
 *
 * Uploads a File via multipart/form-data (field name `file`) to the given
 * upload URL, receives `{ job_id }` (HTTP 202), then polls
 * `GET /api/v1/imports/{job_id}` every ~1.5s until the job reaches a terminal
 * state (`done` / `failed`).
 *
 * The `uploadUrl` may include query params — they are preserved.
 */
export const useCsvImport = () => {
  const config = useRuntimeConfig()
  const toast = useToast()

  const uploading = ref(false)
  const finished = ref(false)
  const status = ref<ImportStatus | null>(null)
  const filename = ref('')
  const rowsTotal = ref(0)
  const rowsDone = ref(0)
  const errorsCount = ref(0)
  const errorSample = ref<string[]>([])
  const errorMessage = ref('')

  // Progress as a percentage (rows_done / rows_total). When the job is done we
  // pin it to 100, while queued/parsing show a small head-start so the bar
  // doesn't sit at zero.
  const progress = computed<number>(() => {
    if (status.value === 'done') return 100
    if (status.value === 'failed') return 0
    if (status.value === 'queued') return 2
    if (status.value === 'parsing') return 5
    if (rowsTotal.value > 0) {
      return Math.min(99, Math.round((rowsDone.value / rowsTotal.value) * 100))
    }
    return 10
  })

  let pollTimer: ReturnType<typeof setInterval> | null = null

  const stopPolling = () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const applyJob = (job: ImportJob) => {
    status.value = job.status
    filename.value = job.filename
    rowsTotal.value = job.rows_total ?? 0
    rowsDone.value = job.rows_done ?? 0
    errorsCount.value = job.errors_count ?? 0
    errorSample.value = job.error_sample ?? []
  }

  const isTerminalJob = (job: ImportJob): job is TerminalImportJob => {
    return job.status === 'done' || job.status === 'failed'
  }

  const pollJob = (jobId: string): Promise<TerminalImportJob> => {
    stopPolling()
    return new Promise((resolve) => {
      let settled = false
      pollTimer = setInterval(async () => {
        try {
          const job = await $fetch<ImportJob>(`/api/v1/imports/${jobId}`, {
            baseURL: config.public.apiBase,
            credentials: 'include'
          })
          if (settled) return

          applyJob(job)

          if (!isTerminalJob(job)) return

          settled = true
          stopPolling()
          uploading.value = false
          finished.value = true

          if (job.status === 'done') {
            toast.success(`Импорт завершён: загружено ${job.rows_done} из ${job.rows_total}`)
          } else {
            errorMessage.value = resolveImportErrorMessage(job.error, job.error_sample)
            toast.error('Ошибка при импорте')
          }

          resolve(job)
        } catch (err) {
          console.error('Import poll error:', err)
        }
      }, POLL_INTERVAL_MS)
    })
  }

  const reset = () => {
    stopPolling()
    uploading.value = false
    finished.value = false
    status.value = null
    filename.value = ''
    rowsTotal.value = 0
    rowsDone.value = 0
    errorsCount.value = 0
    errorSample.value = []
    errorMessage.value = ''
  }

  /**
   * Upload a CSV file and wait for polling to return the terminal job.
   * Returns null only when the file could not be enqueued. `uploadUrl` is the
   * API path (optionally with query params), e.g. `/api/v1/vehicles/import`.
   */
  const upload = async (uploadUrl: string, file: File): Promise<TerminalImportJob | null> => {
    reset()
    uploading.value = true
    status.value = 'queued'
    filename.value = file.name

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await $fetch<UploadResponse>(uploadUrl, {
        baseURL: config.public.apiBase,
        credentials: 'include',
        method: 'POST',
        body: formData
      })

      if (!response?.job_id) {
        throw new Error('No job_id in response')
      }
      return await pollJob(response.job_id)
    } catch (err) {
      console.error('Import upload error:', err)
      stopPolling()
      uploading.value = false
      finished.value = true
      status.value = 'failed'
      const e = err as { data?: { detail?: string; error?: string } }
      errorMessage.value = e.data?.detail || e.data?.error || 'Ошибка при загрузке файла'
      toast.error('Ошибка при загрузке файла')
      return null
    }
  }

  onUnmounted(() => {
    stopPolling()
  })

  return {
    // state
    uploading,
    finished,
    status,
    filename,
    progress,
    rowsTotal,
    rowsDone,
    errorsCount,
    errorSample,
    errorMessage,
    // actions
    upload,
    reset
  }
}
