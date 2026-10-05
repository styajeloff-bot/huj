import type { UUID } from '~/types/ids'

export interface ApplicationSupportProgramRow {
  key: string
  id: UUID | null
  name: string
  pricing: string
}
