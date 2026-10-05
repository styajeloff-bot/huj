import type { UUID } from '~/types/ids'
import type { RegistryImage, RegistryImageOrderRequest, RegistryMediaUploadResponse } from './types'

export interface ProductGalleryImageState {
  altText: string | null
  sortOrder: number
  isPrimary: boolean
}

export interface ProductGallerySyncState {
  draftImages: RegistryImage[]
  pendingFiles: File[]
  removedImageIds: Set<UUID>
  initialImageState: Map<UUID, ProductGalleryImageState>
  reorderPending: boolean
}

interface ConditionalResponse<T> {
  data: T
  etag: string
}

export interface ProductGallerySyncOperations {
  deleteImage: (imageId: UUID, etag: string) => Promise<{ etag: string }>
  updateImage: (imageId: UUID, altText: string | null, etag: string) => Promise<ConditionalResponse<RegistryImage>>
  uploadImage: (file: File, altText: string, etag: string) => Promise<ConditionalResponse<RegistryMediaUploadResponse>>
  reorderImages: (body: RegistryImageOrderRequest, etag: string) => Promise<ConditionalResponse<RegistryMediaUploadResponse>>
}

const cloneState = (state: ProductGallerySyncState): ProductGallerySyncState => ({
  draftImages: state.draftImages.map((image) => ({ ...image })),
  pendingFiles: [...state.pendingFiles],
  removedImageIds: new Set(state.removedImageIds),
  initialImageState: new Map([...state.initialImageState].map(([imageId, image]) => [imageId, { ...image }])),
  reorderPending: state.reorderPending,
})

const imageState = (image: RegistryImage): ProductGalleryImageState => ({
  altText: image.alt_text,
  sortOrder: image.sort_order,
  isPrimary: image.is_primary,
})

const imageStateChanged = (left: ProductGalleryImageState, right: ProductGalleryImageState): boolean =>
  left.altText !== right.altText || left.sortOrder !== right.sortOrder || left.isPrimary !== right.isPrimary

const ordered = (images: RegistryImage[]): RegistryImage[] => [...images].sort((left, right) =>
  left.sort_order - right.sort_order || left.id.localeCompare(right.id),
)

/** Rebase local gallery intent onto the latest server gallery after a 412. */
export const rebaseProductGallery = (
  current: ProductGallerySyncState,
  serverImages: RegistryImage[],
): { state: ProductGallerySyncState; conflicts: string[]; serverChanged: boolean } => {
  const local = cloneState(current)
  const baseline = local.initialImageState
  const localById = new Map(local.draftImages.map((image) => [image.id, image]))
  const serverOrdered = ordered(serverImages)
  const serverById = new Map(serverOrdered.map((image) => [image.id, image]))
  const conflicts = new Set<string>()

  const serverChanged = baseline.size !== serverById.size || [...baseline].some(([imageId, initial]) => {
    const server = serverById.get(imageId)
    return !server || imageStateChanged(initial, imageState(server))
  })

  const mergedById = new Map<UUID, RegistryImage>()
  for (const server of serverOrdered) {
    const initial = baseline.get(server.id)
    const localImage = localById.get(server.id)
    if (local.removedImageIds.has(server.id)) {
      if (initial && imageStateChanged(initial, imageState(server))) {
        conflicts.add(`Изображение ${server.id} изменено на сервере, но локально помечено на удаление.`)
      }
      continue
    }
    if (!initial || !localImage) {
      mergedById.set(server.id, { ...server })
      continue
    }
    const localAltChanged = localImage.alt_text !== initial.altText
    const serverAltChanged = server.alt_text !== initial.altText
    if (localAltChanged && serverAltChanged && localImage.alt_text !== server.alt_text) {
      conflicts.add(`Alt-текст изображения ${server.id} изменён и локально, и на сервере; сохранён локальный вариант.`)
    }
    mergedById.set(server.id, {
      ...server,
      alt_text: localAltChanged ? localImage.alt_text : server.alt_text,
    })
  }

  for (const [imageId, initial] of baseline) {
    if (serverById.has(imageId) || local.removedImageIds.has(imageId)) continue
    const localImage = localById.get(imageId)
    if (localImage && imageStateChanged(initial, imageState(localImage))) {
      conflicts.add(`Изображение ${imageId} удалено на сервере; его локальные настройки восстановить невозможно.`)
    }
  }

  const baselineLayout = [...baseline]
    .sort(([, left], [, right]) => left.sortOrder - right.sortOrder)
    .map(([imageId]) => imageId)
  const serverLayout = serverOrdered.map((image) => image.id)
  const remoteLayoutChanged = baselineLayout.join('|') !== serverLayout.join('|')
    || serverOrdered.some((image) => baseline.get(image.id)?.isPrimary !== image.is_primary)
  if (local.reorderPending && remoteLayoutChanged) {
    conflicts.add('Порядок или главное изображение изменены параллельно; сохранён локальный порядок с добавлением новых серверных изображений.')
  }

  const locallyOrderedIds = ordered(local.draftImages).map((image) => image.id)
  const desiredIds = local.reorderPending
    ? [...locallyOrderedIds, ...serverLayout.filter((imageId) => !locallyOrderedIds.includes(imageId))]
    : serverLayout
  const merged = desiredIds.flatMap((imageId) => {
    const image = mergedById.get(imageId)
    return image ? [{ ...image }] : []
  })

  const localPrimaryId = local.draftImages.find((image) => image.is_primary)?.id
  const serverPrimaryId = serverOrdered.find((image) => image.is_primary)?.id
  const desiredPrimaryId = local.reorderPending && localPrimaryId && mergedById.has(localPrimaryId)
    ? localPrimaryId
    : serverPrimaryId && mergedById.has(serverPrimaryId)
      ? serverPrimaryId
      : merged[0]?.id
  const draftImages = merged.map((image, sortOrder) => ({
    ...image,
    sort_order: sortOrder,
    is_primary: image.id === desiredPrimaryId,
  }))
  const removedImageIds = new Set([...local.removedImageIds].filter((imageId) => serverById.has(imageId)))
  const serverComparable = serverOrdered.map((image, sortOrder) => ({ ...image, sort_order: sortOrder }))
  const reorderPending = removedImageIds.size > 0
    || draftImages.map((image) => image.id).join('|') !== serverComparable.map((image) => image.id).join('|')
    || draftImages.some((image, position) => image.is_primary !== serverComparable[position]?.is_primary)

  return {
    state: {
      draftImages,
      pendingFiles: local.pendingFiles,
      removedImageIds,
      initialImageState: new Map(serverOrdered.map((image) => [image.id, imageState(image)])),
      reorderPending,
    },
    conflicts: [...conflicts],
    serverChanged,
  }
}

/**
 * Synchronise a product gallery while checkpointing every committed mutation.
 *
 * Each media endpoint commits independently and advances the product ETag. The
 * progress callback therefore runs after every successful request so a retry
 * resumes at the first unfinished step instead of deleting twice or uploading
 * the same local file again.
 */
export const syncProductGallery = async ({
  initialEtag,
  initialState,
  operations,
  onProgress,
}: {
  initialEtag: string
  initialState: ProductGallerySyncState
  operations: ProductGallerySyncOperations
  onProgress: (state: ProductGallerySyncState, etag: string) => void
}): Promise<{ state: ProductGallerySyncState; etag: string }> => {
  const state = cloneState(initialState)
  let etag = initialEtag

  const checkpoint = () => onProgress(cloneState(state), etag)

  for (const imageId of [...state.removedImageIds]) {
    const response = await operations.deleteImage(imageId, etag)
    etag = response.etag
    state.removedImageIds.delete(imageId)
    state.initialImageState.delete(imageId)
    state.reorderPending = true
    checkpoint()
  }

  for (const image of [...state.draftImages]) {
    const initial = state.initialImageState.get(image.id)
    if (!initial || initial.altText === image.alt_text) continue
    const response = await operations.updateImage(image.id, image.alt_text, etag)
    etag = response.etag
    state.initialImageState.set(image.id, { ...initial, altText: response.data.alt_text })
    checkpoint()
  }

  for (const file of [...state.pendingFiles]) {
    const response = await operations.uploadImage(file, file.name, etag)
    etag = response.etag
    const pendingPosition = state.pendingFiles.indexOf(file)
    if (pendingPosition >= 0) state.pendingFiles.splice(pendingPosition, 1)
    const uploadedImage = response.data.image
    if (!uploadedImage) {
      throw new Error('API реестра не вернул загруженное изображение')
    }
    state.draftImages.push({ ...uploadedImage })
    state.initialImageState.set(uploadedImage.id, imageState(uploadedImage))
    state.reorderPending = true
    checkpoint()
  }

  if (state.draftImages.length === 0) {
    state.reorderPending = false
    checkpoint()
    return { state: cloneState(state), etag }
  }

  if (state.reorderPending) {
    const orderedImages = state.draftImages.map((image, sortOrder) => ({ ...image, sort_order: sortOrder }))
    if (!orderedImages.some((image) => image.is_primary)) {
      orderedImages[0] = { ...orderedImages[0]!, is_primary: true }
    }
    const response = await operations.reorderImages({
      images: orderedImages.map((image) => ({
        id: image.id,
        sort_order: image.sort_order,
        is_primary: image.is_primary,
      })),
    }, etag)
    etag = response.etag
    state.draftImages = orderedImages
    state.initialImageState = new Map(orderedImages.map((image) => [image.id, imageState(image)]))
    state.reorderPending = false
    checkpoint()
  }

  return { state: cloneState(state), etag }
}
