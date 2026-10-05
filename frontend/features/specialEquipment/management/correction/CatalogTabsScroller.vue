<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  activeKey?: string | number | null
}>()

const scrollerRef = ref<HTMLElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)

let resizeObserver: ResizeObserver | null = null
let mutationObserver: MutationObserver | null = null

const getScrollContainer = (): HTMLElement | null => {
  if (!scrollerRef.value) return null
  return (
    scrollerRef.value.querySelector<HTMLElement>('.se-tabs') ??
    (scrollerRef.value.firstElementChild as HTMLElement | null)
  )
}

const updateScrollState = () => {
  const container = getScrollContainer()
  if (!container) {
    canScrollLeft.value = false
    canScrollRight.value = false
    return
  }

  const { scrollLeft, scrollWidth, clientWidth } = container
  const maxScroll = Math.max(0, scrollWidth - clientWidth)

  canScrollLeft.value = scrollLeft > 1
  canScrollRight.value = maxScroll > 1 && scrollLeft < maxScroll - 1
}

const scrollByDirection = (direction: -1 | 1) => {
  const container = getScrollContainer()
  if (!container) return
  const distance = Math.round(container.clientWidth * 0.8) * direction
  if (typeof container.scrollBy === 'function') {
    container.scrollBy({
      left: distance,
      behavior: 'smooth',
    })
  } else {
    container.scrollLeft += distance
  }
  setTimeout(updateScrollState, 150)
  setTimeout(updateScrollState, 400)
}

const scrollLeft = () => scrollByDirection(-1)
const scrollRight = () => scrollByDirection(1)

const onWheel = (event: WheelEvent) => {
  const container = getScrollContainer()
  if (!container) return
  if (container.scrollWidth <= container.clientWidth + 1) return

  if (event.deltaY !== 0) {
    event.preventDefault()
    container.scrollLeft += event.deltaY
    updateScrollState()
  }
}

const scrollActiveIntoView = () => {
  const container = getScrollContainer()
  if (!container) return
  const activeEl = container.querySelector<HTMLElement>(
    '[aria-current="page"], .se-tab--active'
  )
  if (activeEl) {
    activeEl.scrollIntoView({ inline: 'nearest', block: 'nearest' })
    updateScrollState()
  }
}

const onScroll = () => {
  updateScrollState()
}

const onKeydown = (event: KeyboardEvent) => {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
  const container = getScrollContainer()
  if (!container) return
  const tabsList = Array.from(
    container.querySelectorAll<HTMLButtonElement>('.se-tab')
  )
  const currentIndex = tabsList.findIndex((el) => el === document.activeElement)
  if (currentIndex === -1) return

  event.preventDefault()
  let nextIndex: number
  if (event.key === 'ArrowRight') {
    nextIndex = (currentIndex + 1) % tabsList.length
  } else {
    nextIndex = (currentIndex - 1 + tabsList.length) % tabsList.length
  }
  const nextEl = tabsList[nextIndex]
  if (nextEl) {
    nextEl.focus()
    nextEl.scrollIntoView({ inline: 'nearest', block: 'nearest' })
    nextEl.click()
  }
}

const onFocusIn = (event: FocusEvent) => {
  const target = event.target as HTMLElement | null
  if (target && target.classList.contains('se-tab')) {
    target.scrollIntoView({ inline: 'nearest', block: 'nearest' })
    updateScrollState()
  }
}

watch(
  () => props.activeKey,
  () => {
    nextTick(() => {
      scrollActiveIntoView()
    })
  }
)

onMounted(() => {
  const container = getScrollContainer()
  if (container) {
    container.addEventListener('scroll', onScroll, { passive: true })
    container.addEventListener('keydown', onKeydown)
    container.addEventListener('focusin', onFocusIn)
  }
  if (scrollerRef.value) {
    scrollerRef.value.addEventListener('wheel', onWheel, { passive: false })
  }

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateScrollState()
    })
    if (scrollerRef.value) resizeObserver.observe(scrollerRef.value)
    if (container) resizeObserver.observe(container)
  }

  if (container && typeof MutationObserver !== 'undefined') {
    mutationObserver = new MutationObserver((mutations) => {
      let activeChanged = false
      for (const m of mutations) {
        if (
          m.type === 'attributes' &&
          (m.attributeName === 'class' || m.attributeName === 'aria-current')
        ) {
          activeChanged = true
          break
        }
      }
      updateScrollState()
      if (activeChanged) {
        scrollActiveIntoView()
      }
    })
    mutationObserver.observe(container, {
      attributes: true,
      subtree: true,
      attributeFilter: ['class', 'aria-current'],
      childList: true,
    })
  }

  nextTick(() => {
    updateScrollState()
    scrollActiveIntoView()
    requestAnimationFrame(() => {
      updateScrollState()
      scrollActiveIntoView()
    })
  })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  mutationObserver?.disconnect()
  const container = getScrollContainer()
  if (container) {
    container.removeEventListener('scroll', onScroll)
    container.removeEventListener('keydown', onKeydown)
    container.removeEventListener('focusin', onFocusIn)
  }
  if (scrollerRef.value) {
    scrollerRef.value.removeEventListener('wheel', onWheel)
  }
})
</script>

<template>
  <div ref="scrollerRef" class="se-tabs-scroller">
    <button
      v-if="canScrollLeft"
      type="button"
      class="se-tabs-scroll-btn se-tabs-scroll-btn--left"
      aria-label="Прокрутить вкладки влево"
      @click="scrollLeft"
    >
      <span aria-hidden="true" class="se-tabs-scroll-btn__icon">‹</span>
    </button>
    <slot />
    <button
      v-if="canScrollRight"
      type="button"
      class="se-tabs-scroll-btn se-tabs-scroll-btn--right"
      aria-label="Прокрутить вкладки вправо"
      @click="scrollRight"
    >
      <span aria-hidden="true" class="se-tabs-scroll-btn__icon">›</span>
    </button>
  </div>
</template>
