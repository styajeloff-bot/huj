<template>
  <div data-storefront-block="equipment.category" class="grid grid-cols-2 gap-4 lg:grid-cols-4 text-storefront-text">
    <button
      v-for="placement in placements"
      :key="placement.identity"
      type="button"
      :data-homepage-category-identity="placement.identity"
      class="group min-h-64 overflow-hidden rounded-xl border bg-storefront-surface p-4 text-left transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 motion-reduce:transition-none"
      :class="attachment
        ? 'border-storefront-primary-border hover:border-storefront-primary-border hover:bg-storefront-selected'
        : 'border-storefront-border hover:border-storefront-primary-border'"
      @click="emit('select', placement.path, placement.identity)"
    >
      <span
        class="relative grid aspect-[3/2] w-full place-items-center overflow-hidden rounded-lg"
        :class="'bg-storefront-image'"
      >
        <PhotoIcon
          v-if="!isCategoryImageLoaded(placement.category)"
          class="h-10 w-10 text-storefront-icon-muted"
          aria-hidden="true"
        />
        <img
          v-if="categoryImageUrl(placement.category)"
          :ref="element => verifyMountedImage(placement.category, element)"
          :src="categoryImageUrl(placement.category) ?? undefined"
          :alt="placement.category.name"
          width="320"
          height="213"
          loading="lazy"
          class="absolute inset-0 h-full w-full object-contain transition-opacity duration-150 motion-reduce:transition-none"
          :class="isCategoryImageLoaded(placement.category) ? 'opacity-100' : 'opacity-0'"
          @load="verifyImageDecoded(placement.category, $event)"
          @error="markImageBroken(placement.category)"
        >
      </span>
      <span class="mt-4 block text-lg font-bold leading-snug text-storefront-text">
        {{ placement.category.name }}
      </span>
      <span class="mt-2 block text-sm font-semibold leading-relaxed text-storefront-link">
        {{ homepageCategoryAction(placement.category, categories, placementsData) }}
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { PhotoIcon } from '@heroicons/vue/24/outline'
import type { SpecialEquipmentHomepagePlacement } from '../homepageCategoryNavigation'
import { homepageCategoryAction } from '../homepageCatalogPresentation'
import { toSpecialEquipmentProxyUrl } from '../media'
import type {
  SpecialEquipmentCategoryNode,
  SpecialEquipmentCategoryPlacement,
} from '../types'

const props = withDefaults(defineProps<{
  placements: SpecialEquipmentHomepagePlacement[]
  categories: SpecialEquipmentCategoryNode[]
  placementsData: SpecialEquipmentCategoryPlacement[]
  attachment?: boolean
}>(), {
  attachment: false,
})
const emit = defineEmits<{
  select: [path: string[], identity?: string]
}>()
const brokenImageUrls = ref<Set<string>>(new Set())
const loadedImageUrls = ref<Set<string>>(new Set())
const pendingImageUrls = new Set<string>()

const rawCategoryImageUrl = (category: SpecialEquipmentCategoryNode): string | null =>
  toSpecialEquipmentProxyUrl(category.image_url)

const categoryImageUrl = (category: SpecialEquipmentCategoryNode): string | null => {
  const url = rawCategoryImageUrl(category)
  return url && !brokenImageUrls.value.has(url) ? url : null
}

const isCategoryImageLoaded = (category: SpecialEquipmentCategoryNode): boolean => {
  const url = categoryImageUrl(category)
  return Boolean(url && loadedImageUrls.value.has(url))
}

const markImageBroken = (category: SpecialEquipmentCategoryNode) => {
  const url = rawCategoryImageUrl(category)
  if (!url) return
  brokenImageUrls.value = new Set([...brokenImageUrls.value, url])
  if (loadedImageUrls.value.has(url)) {
    loadedImageUrls.value = new Set([...loadedImageUrls.value].filter(item => item !== url))
  }
}

const verifyImageElement = async (category: SpecialEquipmentCategoryNode, image: HTMLImageElement) => {
  const url = categoryImageUrl(category)
  if (!url || loadedImageUrls.value.has(url) || pendingImageUrls.has(url)) return
  pendingImageUrls.add(url)
  try {
    await image.decode()
  } catch {
    markImageBroken(category)
    pendingImageUrls.delete(url)
    return
  }
  pendingImageUrls.delete(url)
  if (image.naturalWidth > 0 && image.naturalHeight > 0) {
    loadedImageUrls.value = new Set([...loadedImageUrls.value, url])
    return
  }
  markImageBroken(category)
}

const verifyImageDecoded = async (category: SpecialEquipmentCategoryNode, event: Event) => {
  const image = event.currentTarget
  if (image instanceof HTMLImageElement) await verifyImageElement(category, image)
}

const verifyMountedImage = (category: SpecialEquipmentCategoryNode, element: unknown) => {
  if (element instanceof HTMLImageElement && element.complete) {
    void verifyImageElement(category, element)
  }
}
</script>
