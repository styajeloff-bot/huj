<template>
  <section data-storefront-block="equipment.gallery" aria-label="Фотографии техники" class="text-storefront-text">
    <div
      id="special-equipment-gallery-panel"
      role="tabpanel"
      :aria-labelledby="`special-equipment-gallery-tab-${currentIndex}`"
      class="bg-storefront-image relative aspect-[4/3] overflow-hidden rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"

      tabindex="0"
      @keydown.left.prevent="previous"
      @keydown.right.prevent="next"
      @touchstart.passive="handleTouchStart"
      @touchend.passive="handleTouchEnd"
    >
      <img
        v-if="activeImage && !failedImageIds.has(activeImage.id)"
        :src="activeImage.content_url"
        :alt="activeImage.alt_text || `${title}, фотография ${currentIndex + 1}`"
        class="h-full w-full object-contain"
        width="960"
        height="720"
        fetchpriority="high"
        @error="markFailed(activeImage.id)"
      >
      <div v-else class="grid h-full place-items-center text-storefront-text-muted">
        <TruckIcon class="h-20 w-20 text-storefront-icon" aria-hidden="true" />
        <p class="sr-only">Фотография отсутствует</p>
      </div>

      <template v-if="proxyImages.length > 1">
        <button
          type="button"
          class="absolute left-3 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full bg-storefront-surface/95 text-storefront-text storefront-shadow-sm hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
          aria-label="Предыдущая фотография"
          @click="previous"
        >
          <ChevronLeftIcon class="h-6 w-6 text-storefront-icon" aria-hidden="true" />
        </button>
        <button
          type="button"
          class="absolute right-3 top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full bg-storefront-surface/95 text-storefront-text storefront-shadow-sm hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary"
          aria-label="Следующая фотография"
          @click="next"
        >
          <ChevronRightIcon class="h-6 w-6 text-storefront-icon" aria-hidden="true" />
        </button>
        <span class="absolute bottom-3 right-3 rounded-full bg-storefront-badge/75 px-3 py-1 text-sm tabular-nums text-storefront-badge-text">
          {{ currentIndex + 1 }} / {{ proxyImages.length }}
        </span>
      </template>
    </div>

    <div v-if="proxyImages.length > 1" class="mt-3 flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Выбор фотографии">
      <button
        v-for="(image, index) in proxyImages"
        :key="image.id"
        type="button"
        role="tab"
        :id="`special-equipment-gallery-tab-${index}`"
        aria-controls="special-equipment-gallery-panel"
        :tabindex="index === currentIndex ? 0 : -1"
        class="h-16 w-20 shrink-0 overflow-hidden rounded-lg border-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
        :class="[
          index === currentIndex ? 'border-storefront-selected-border' : 'border-transparent hover:border-storefront-secondary-hover-border',
          'bg-storefront-image',
        ]"
        :aria-selected="index === currentIndex"
        :aria-label="`Показать фотографию ${index + 1}`"
        :ref="(element) => setThumbnailRef(element, index)"
        @click="currentIndex = index"
        @keydown.left.prevent="focusThumbnail(index - 1)"
        @keydown.right.prevent="focusThumbnail(index + 1)"
        @keydown.home.prevent="focusThumbnail(0)"
        @keydown.end.prevent="focusThumbnail(proxyImages.length - 1)"
      >
        <img
          v-if="!failedImageIds.has(image.id)"
          :src="image.content_url"
          :alt="image.alt_text || ''"
          class="h-full w-full object-cover"
          width="160"
          height="128"
          loading="lazy"
          @error="markFailed(image.id)"
        >
        <TruckIcon v-else class="mx-auto h-6 w-6 text-storefront-icon-muted" aria-hidden="true" />
      </button>
    </div>
    <p v-if="proxyImages.length > 1" class="mt-2 text-xs text-storefront-text-muted">
      Используйте стрелки клавиатуры или свайп для просмотра.
    </p>
  </section>
</template>

<script setup lang="ts">
import { ChevronLeftIcon, ChevronRightIcon, TruckIcon } from '@heroicons/vue/24/outline'
import type { UUID } from '~/types/ids'
import type { SpecialEquipmentImage } from '../types'
import { toSpecialEquipmentProxyUrl } from '../media'

const props = defineProps<{
  images: SpecialEquipmentImage[]
  title: string
}>()

const currentIndex = ref(0)
const touchStartX = ref<number | null>(null)
const failedImageIds = ref<Set<UUID>>(new Set())
const thumbnailButtons = ref<HTMLButtonElement[]>([])

const proxyImages = computed(() => props.images.filter(image => toSpecialEquipmentProxyUrl(image.content_url)))
const activeImage = computed(() => proxyImages.value[currentIndex.value] ?? null)

const previous = () => {
  if (proxyImages.value.length < 2) return
  currentIndex.value = (currentIndex.value - 1 + proxyImages.value.length) % proxyImages.value.length
}

const next = () => {
  if (proxyImages.value.length < 2) return
  currentIndex.value = (currentIndex.value + 1) % proxyImages.value.length
}

const setThumbnailRef = (element: Element | ComponentPublicInstance | null, index: number) => {
  if (element instanceof HTMLButtonElement) thumbnailButtons.value[index] = element
}

const focusThumbnail = (index: number) => {
  const length = proxyImages.value.length
  if (length === 0) return
  currentIndex.value = (index + length) % length
  void nextTick(() => thumbnailButtons.value[currentIndex.value]?.focus())
}

const handleTouchStart = (event: TouchEvent) => {
  touchStartX.value = event.changedTouches[0]?.clientX ?? null
}

const handleTouchEnd = (event: TouchEvent) => {
  const start = touchStartX.value
  const end = event.changedTouches[0]?.clientX
  touchStartX.value = null
  if (start === null || end === undefined || Math.abs(start - end) < 50) return
  if (start > end) next()
  else previous()
}

const markFailed = (imageId: UUID) => {
  failedImageIds.value = new Set([...failedImageIds.value, imageId])
}

watch(proxyImages, () => {
  currentIndex.value = 0
  failedImageIds.value = new Set()
  thumbnailButtons.value = []
})
</script>
