<template>
  <span v-if="authStore.isCarCraftEmployee" ref="trigger" tabindex="0"
    :aria-describedby="open ? tooltipId : undefined"
    class="inline-block rounded text-sm font-medium text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
    @mouseenter="triggerHovered = true; show()" @mouseleave="triggerHovered = false; scheduleClose()"
    @focus="focused = true; show()" @blur="focused = false; scheduleClose()"
    @keydown.esc.stop.prevent="close">
    {{ address }}
  </span>
  <span v-else class="text-sm font-medium text-gray-900">{{ address }}</span>
  <Teleport v-if="mounted && authStore.isCarCraftEmployee" to="body">
    <span v-if="open" :id="tooltipId" ref="tooltip" role="tooltip"
      class="fixed z-[220] max-w-[calc(100vw-32px)] break-words rounded bg-gray-900 px-3 py-2 text-sm font-normal text-white shadow-lg"
      :style="position"
      @mouseenter="tooltipHovered = true; show()" @mouseleave="tooltipHovered = false; scheduleClose()">
      ID склада: {{ warehouseId }}
    </span>
  </Teleport>
</template>

<script setup lang="ts">
import type { CSSProperties } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'

defineProps<{ warehouseId: string; address: string }>()
const authStore = useAuthStore()
const trigger = ref<HTMLElement | null>(null)
const tooltip = ref<HTMLElement | null>(null)
const tooltipId = `warehouse-tooltip-${useId()}`
const mounted = ref(false)
const open = ref(false)
const position = ref<CSSProperties>({ visibility: 'hidden' })
const triggerHovered = ref(false)
const tooltipHovered = ref(false)
const focused = ref(false)
let closeTimer: ReturnType<typeof setTimeout> | undefined

const clearCloseTimer = () => {
  if (closeTimer !== undefined) clearTimeout(closeTimer)
  closeTimer = undefined
}
const show = () => {
  clearCloseTimer()
  if (authStore.isCarCraftEmployee) open.value = true
}
const close = () => {
  clearCloseTimer()
  open.value = false
  tooltipHovered.value = false
}
const scheduleClose = () => {
  clearCloseTimer()
  // Keep the tooltip reachable across the small gap from its trigger.
  closeTimer = setTimeout(() => {
    if (!triggerHovered.value && !tooltipHovered.value && !focused.value) close()
  }, 120)
}
const handleEscape = (event: KeyboardEvent) => {
  if (event.key !== 'Escape') return
  event.preventDefault()
  event.stopPropagation()
  close()
}
const updatePosition = () => {
  if (!trigger.value || !tooltip.value) return
  const anchor = trigger.value.getBoundingClientRect()
  const content = tooltip.value.getBoundingClientRect()
  const padding = 16
  const gap = 8
  if (anchor.bottom <= 0 || anchor.top >= window.innerHeight) {
    close()
    return
  }
  // Same fixed, viewport-clamped positioning pattern as CatalogHelpPopover.
  const left = Math.max(padding, Math.min(anchor.left, window.innerWidth - content.width - padding))
  const preferredTop = anchor.bottom + gap + content.height <= window.innerHeight - padding
    ? anchor.bottom + gap
    : anchor.top - content.height - gap
  const top = Math.max(padding, Math.min(preferredTop, window.innerHeight - content.height - padding))
  position.value = { left: `${left}px`, top: `${top}px`, visibility: 'visible' }
}
const removeListeners = () => {
  window.removeEventListener('scroll', updatePosition, true)
  window.removeEventListener('resize', updatePosition)
  document.removeEventListener('keydown', handleEscape, true)
}
watch(open, async (visible, _previous, onCleanup) => {
  if (!import.meta.client) return
  let cancelled = false
  onCleanup(() => { cancelled = true; removeListeners() })
  if (!visible) return
  position.value = { visibility: 'hidden' }
  await nextTick()
  if (cancelled || !open.value) return
  updatePosition()
  window.addEventListener('scroll', updatePosition, true)
  window.addEventListener('resize', updatePosition)
  document.addEventListener('keydown', handleEscape, true)
})
watch(() => authStore.isCarCraftEmployee, allowed => {
  if (!allowed) {
    triggerHovered.value = false
    focused.value = false
    close()
  }
})
onMounted(() => { mounted.value = true })
onBeforeUnmount(() => { clearCloseTimer(); removeListeners() })
</script>
