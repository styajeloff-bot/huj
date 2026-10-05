<template>
  <span ref="root" class="se-help">
    <button
      ref="trigger"
      type="button"
      class="se-help__trigger"
      :aria-expanded="open"
      :aria-controls="contentId"
      :aria-describedby="open ? contentId : undefined"
      :aria-label="`Пояснение: ${label}`"
      @click="open = !open"
      @keydown.esc.stop.prevent="close"
    >
      ?
    </button>
    <Teleport v-if="teleportTarget" :to="teleportTarget">
      <span
        v-if="open"
        :id="contentId"
        ref="content"
        class="se-help__content"
        role="tooltip"
        :style="contentStyle"
        @keydown.esc.stop.prevent="close"
      >
        {{ text }}
      </span>
    </Teleport>
  </span>
</template>

<script setup lang="ts">
import type { CSSProperties } from 'vue'
import {
  calculateTooltipLeft,
  calculateTooltipTop,
} from './catalogHelpPosition'

const props = defineProps<{ label: string; text: string }>()
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const content = ref<HTMLElement | null>(null)
const teleportTarget = ref<HTMLElement | null>(null)
const open = ref(false)
const contentStyle = ref<CSSProperties>({ visibility: 'hidden' })
const contentId = `catalog-help-${useId()}`
const VIEWPORT_PADDING = 16
const TOOLTIP_GAP = 8
const TOOLTIP_MAX_WIDTH = 290
let positionFrame: number | null = null
let viewportSettleFrame: number | null = null

const close = () => {
  open.value = false
  void nextTick(() => trigger.value?.focus())
}
const handleDocumentClick = (event: MouseEvent) => {
  const target = event.target as Node
  if (
    open.value
    && !root.value?.contains(target)
    && !content.value?.contains(target)
  ) open.value = false
}
const handleDocumentKeydown = (event: KeyboardEvent) => {
  if (!open.value || event.key !== 'Escape') return
  event.preventDefault()
  event.stopPropagation()
  close()
}

const updatePosition = () => {
  if (!import.meta.client || !open.value || !trigger.value || !content.value) return

  const triggerRect = trigger.value.getBoundingClientRect()
  const tooltipWidth = Math.min(
    TOOLTIP_MAX_WIDTH,
    window.innerWidth - VIEWPORT_PADDING * 2,
  )
  content.value.style.width = `${tooltipWidth}px`
  content.value.style.right = 'auto'
  content.value.style.bottom = 'auto'
  const tooltipHeight = content.value.getBoundingClientRect().height
  const left = calculateTooltipLeft({
    triggerCenterX: triggerRect.left + triggerRect.width / 2,
    tooltipWidth,
    viewportWidth: window.innerWidth,
    viewportPadding: VIEWPORT_PADDING,
  })
  const top = calculateTooltipTop({
    triggerTop: triggerRect.top,
    triggerBottom: triggerRect.bottom,
    tooltipHeight,
    viewportHeight: window.innerHeight,
    viewportPadding: VIEWPORT_PADDING,
    gap: TOOLTIP_GAP,
  })

  contentStyle.value = {
    visibility: 'visible',
    top: `${top}px`,
    right: 'auto',
    bottom: 'auto',
    left: `${left}px`,
    width: `${tooltipWidth}px`,
  }
}

const schedulePositionUpdate = () => {
  if (positionFrame !== null) return
  positionFrame = window.requestAnimationFrame(() => {
    positionFrame = null
    updatePosition()
  })
}

const handleViewportResize = () => {
  schedulePositionUpdate()
  if (viewportSettleFrame !== null) {
    window.cancelAnimationFrame(viewportSettleFrame)
  }
  viewportSettleFrame = window.requestAnimationFrame(() => {
    viewportSettleFrame = null
    schedulePositionUpdate()
  })
}

const addPositionListeners = () => {
  window.addEventListener('resize', handleViewportResize)
  window.addEventListener('scroll', schedulePositionUpdate, true)
  document.addEventListener('keydown', handleDocumentKeydown, true)
}

const removePositionListeners = () => {
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('scroll', schedulePositionUpdate, true)
  document.removeEventListener('keydown', handleDocumentKeydown, true)
  if (positionFrame !== null) {
    window.cancelAnimationFrame(positionFrame)
    positionFrame = null
  }
  if (viewportSettleFrame !== null) {
    window.cancelAnimationFrame(viewportSettleFrame)
    viewportSettleFrame = null
  }
}

watch(open, async (isOpen, _previousOpen, onCleanup) => {
  if (!import.meta.client) return
  let cancelled = false
  onCleanup(() => {
    cancelled = true
  })
  removePositionListeners()
  if (!isOpen) return

  contentStyle.value = { visibility: 'hidden' }
  await nextTick()
  if (cancelled || !open.value || !content.value) return
  updatePosition()
  addPositionListeners()
})

onMounted(() => {
  teleportTarget.value = root.value?.closest<HTMLElement>('.se-overlay-root') ?? document.body
  document.addEventListener('click', handleDocumentClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  removePositionListeners()
})
</script>

<style scoped>
.se-help { position: relative; display: inline-flex; margin-left: 5px; vertical-align: middle; }
.se-help__trigger {
  display: inline-grid;
  width: 24px;
  height: 24px;
  place-items: center;
  padding: 0;
  border: 1px solid hsl(var(--se-border-strong));
  border-radius: 50%;
  background: hsl(var(--se-surface));
  color: hsl(var(--se-primary));
  font-size: 13px;
  font-weight: 900;
  cursor: pointer;
}
.se-help__content {
  position: fixed;
  z-index: 220;
  width: min(290px, calc(100vw - 48px));
  max-height: calc(100dvh - 32px);
  overflow-y: auto;
  padding: 10px 12px;
  border: 1px solid hsl(var(--se-border));
  border-radius: var(--se-radius-sm);
  background: hsl(var(--se-text));
  color: white;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
  box-shadow: 0 10px 28px hsl(var(--se-text) / .2);
  overflow-wrap: anywhere;
}
</style>
