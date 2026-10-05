import type { UUID } from '~/types/ids'

/** Shared media contracts retained by the corrected catalog gallery. */
export interface RegistryImage {
  id: UUID
  content_url: string
  alt_text: string | null
  sort_order: number
  is_primary: boolean
}

export interface RegistryImageOrderRequest {
  images: Array<{
    id: UUID
    sort_order: number
    is_primary: boolean
  }>
}

export interface RegistryMediaUploadResponse {
  image?: RegistryImage | null
  images?: RegistryImage[]
  category?: unknown | null
}
