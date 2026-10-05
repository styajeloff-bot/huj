<template>
  <div class="se-image-editor">
    <div v-if="single && safeCategoryImage" class="se-category-image-card">
      <div class="se-image-visual se-checkerboard">
        <img :src="safeCategoryImage" alt="Текущее изображение категории">
      </div>
      <button
        v-if="!readonly"
        type="button"
        class="se-button se-button--ghost-danger"
        @click="$emit('remove-category-image')"
      >
        <TrashIcon aria-hidden="true" />
        Удалить изображение
      </button>
    </div>

    <div v-if="!single && existingImages.length" class="se-image-grid">
      <article v-for="(image, position) in existingImages" :key="image.id" class="se-image-card">
        <div class="se-image-visual se-checkerboard">
          <img v-if="safeUrl(image.content_url)" :src="safeUrl(image.content_url) || ''" :alt="image.alt_text || ''">
          <PhotoIcon v-else aria-hidden="true" />
          <span class="se-image-position">{{ position + 1 }}</span>
          <span v-if="image.is_primary" class="se-image-primary">Главное</span>
        </div>
        <div class="se-image-card__body">
          <label class="se-field se-field--compact">
            <span>Описание изображения</span>
            <input
              type="text"
              :disabled="readonly"
              :value="image.alt_text || ''"
              maxlength="1000"
              @input="$emit('change-alt', image.id, ($event.target as HTMLInputElement).value)"
            >
          </label>
          <div v-if="!readonly" class="se-image-actions">
            <button type="button" class="se-icon-button" :disabled="position === 0" aria-label="Переместить левее" @click="$emit('move', image.id, -1)">
              <ArrowLeftIcon aria-hidden="true" />
            </button>
            <button type="button" class="se-icon-button" :disabled="position === existingImages.length - 1" aria-label="Переместить правее" @click="$emit('move', image.id, 1)">
              <ArrowRightIcon aria-hidden="true" />
            </button>
            <button type="button" class="se-icon-button" :disabled="image.is_primary" aria-label="Сделать главным" @click="$emit('make-primary', image.id)">
              <StarIcon aria-hidden="true" />
            </button>
            <button type="button" class="se-icon-button se-icon-button--danger" aria-label="Удалить изображение" @click="$emit('remove-image', image.id)">
              <TrashIcon aria-hidden="true" />
            </button>
          </div>
        </div>
      </article>
    </div>

    <div v-if="pendingPreviews.length" class="se-image-grid">
      <article v-for="preview in pendingPreviews" :key="preview.key" class="se-image-card">
        <div class="se-image-visual se-checkerboard">
          <img :src="preview.url" :alt="preview.file.name">
          <span class="se-image-primary se-image-primary--pending">После сохранения</span>
        </div>
        <div class="se-image-card__body">
          <span class="se-pending-file">{{ preview.file.name }}</span>
          <button
            v-if="!readonly"
            type="button"
            class="se-button se-button--ghost-danger se-button--small"
            @click="$emit('remove-pending', preview.position)"
          >
            Убрать
          </button>
        </div>
      </article>
    </div>

    <label
      v-if="!readonly && (!single || (!safeCategoryImage && pendingFiles.length === 0))"
      class="se-dropzone"
      :class="{ 'se-dropzone--dragging': dragging }"
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="handleDrop"
    >
      <input class="sr-only" type="file" :multiple="!single" accept="image/png,image/jpeg,image/webp" @change="handleInput">
      <ArrowUpTrayIcon aria-hidden="true" />
      <strong>{{ single ? 'Загрузить изображение категории' : 'Добавить фотографии' }}</strong>
      <span>PNG, JPEG или WebP до 15 МБ. После загрузки изображение будет оптимизировано; прозрачность и исходный фон сохранятся.</span>
    </label>

    <p v-if="localError" class="se-inline-error" role="alert">
      <ExclamationCircleIcon aria-hidden="true" />
      {{ localError }}
    </p>
    <p class="se-proxy-note">
      <ShieldCheckIcon aria-hidden="true" />
      Файлы передаются через защищённый каталог. Прямой адрес хранилища пользователю не показывается.
    </p>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowUpTrayIcon,
  ExclamationCircleIcon,
  PhotoIcon,
  ShieldCheckIcon,
  StarIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import { toSpecialEquipmentProxyUrl } from '../../media'
import type { RegistryImage } from '../types'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  existingImages: RegistryImage[]
  pendingFiles: File[]
  categoryImageUrl?: string | null
  single?: boolean
  readonly: boolean
}>()

const emit = defineEmits<{
  'add-files': [files: File[]]
  'remove-pending': [position: number]
  'remove-image': [imageId: UUID]
  'remove-category-image': []
  move: [imageId: UUID, direction: -1 | 1]
  'make-primary': [imageId: UUID]
  'change-alt': [imageId: UUID, value: string]
}>()

const dragging = ref(false)
const localError = ref('')
const previewUrls = new Map<string, string>()

const fileKey = (file: File, position: number): string => `${file.name}-${file.size}-${file.lastModified}-${position}`
const safeUrl = (value: string | null | undefined): string | null => toSpecialEquipmentProxyUrl(value)
const safeCategoryImage = computed(() => safeUrl(props.categoryImageUrl))
const pendingPreviews = computed(() => props.pendingFiles.map((file, position) => {
  const key = fileKey(file, position)
  let url = previewUrls.get(key)
  if (!url) {
    url = URL.createObjectURL(file)
    previewUrls.set(key, url)
  }
  return { file, position, key, url }
}))

const validateFiles = (files: File[]): File[] => {
  localError.value = ''
  const accepted = files.filter((file) => ['image/png', 'image/jpeg', 'image/webp'].includes(file.type) && file.size <= 15 * 1024 * 1024)
  const availableSlots = props.single ? 1 : Math.max(0, 50 - props.existingImages.length - props.pendingFiles.length)
  const withinLimit = accepted.slice(0, availableSlots)
  const messages: string[] = []
  if (accepted.length !== files.length) messages.push('Допустимы только PNG, JPEG и WebP размером до 15 МБ.')
  if (withinLimit.length !== accepted.length) messages.push(props.single ? 'Для категории можно выбрать только одно изображение.' : 'В галерее может быть не более 50 изображений.')
  localError.value = messages.join(' ')
  return withinLimit
}

const add = (files: File[]) => {
  const accepted = validateFiles(files)
  if (accepted.length) emit('add-files', accepted)
}
const handleInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  add([...input.files ?? []])
  input.value = ''
}
const handleDrop = (event: DragEvent) => {
  dragging.value = false
  add([...event.dataTransfer?.files ?? []])
}

watch(
  () => props.pendingFiles.map(fileKey),
  (activeKeys) => {
    const active = new Set(activeKeys)
    for (const [key, url] of previewUrls) {
      if (active.has(key)) continue
      URL.revokeObjectURL(url)
      previewUrls.delete(key)
    }
  },
)

onBeforeUnmount(() => {
  for (const url of previewUrls.values()) URL.revokeObjectURL(url)
  previewUrls.clear()
})
</script>
