import {
  computed,
  getCurrentInstance,
  onMounted,
  onScopeDispose,
  readonly,
  ref,
  toValue,
  watch,
  type MaybeRefOrGetter,
} from 'vue'
import type { SupportBadgeProgram } from '~/types/support'

export const SUPPORT_BADGE_ROTATION_MS = 10_000

export const useRotatingSupportBadge = (
  programsSource: MaybeRefOrGetter<readonly SupportBadgeProgram[]>,
  intervalMs: MaybeRefOrGetter<number> = SUPPORT_BADGE_ROTATION_MS,
) => {
  const currentIndex = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  let mounted = false

  const programs = computed(() => [...toValue(programsSource)].sort(
    (left, right) => left.id.localeCompare(right.id),
  ))
  const rotationIntervalMs = computed(() => {
    const value = toValue(intervalMs)
    return Number.isFinite(value) && value > 0 ? value : SUPPORT_BADGE_ROTATION_MS
  })
  const currentProgram = computed(() => programs.value[currentIndex.value] ?? null)

  const stop = () => {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  const start = () => {
    stop()
    if (programs.value.length <= 1) return
    timer = setInterval(() => {
      currentIndex.value = (currentIndex.value + 1) % programs.value.length
    }, rotationIntervalMs.value)
  }

  const reset = () => {
    currentIndex.value = 0
    start()
  }

  watch(
    [
      () => programs.value.map(program => program.id).join(','),
      rotationIntervalMs,
    ],
    () => {
      currentIndex.value = 0
      if (mounted) start()
    },
  )

  if (getCurrentInstance()) {
    onMounted(() => {
      mounted = true
      start()
    })
  }
  onScopeDispose(() => {
    mounted = false
    stop()
  })

  return {
    currentProgram,
    currentIndex: readonly(currentIndex),
    reset,
    start,
    stop,
  }
}
