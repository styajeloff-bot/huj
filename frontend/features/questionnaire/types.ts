import type { UUID } from '~/types/ids'

export interface QuestionnaireContact { name: string; position: string; phone: string; email: string }
export interface QuestionnairePerson {
  id?: UUID
  signer_key?: string
  full_name?: string
  surname?: string
  first_name?: string
  patronymic?: string
  inn?: string
  birth_date?: string
  birth_place?: string
  citizenship?: string
  sex?: string
  passport_series?: string
  passport_number?: string
  passport_issued_by?: string
  passport_issue_date?: string
  passport_department_code?: string
  registration_address?: string
  share_percentage?: number | null
  is_pdl?: boolean
  pdl_related_person_name?: string
  name_changed?: boolean
  beneficial_owner_basis?: UUID
  beneficial_owner_basis_details?: string
  position?: string
  document_type?: string
  type?: 'individual' | 'legal'
}
export interface ElectronicDocumentSystems {
  sbis: boolean
  diadoc: boolean
  kontur: boolean
  other: boolean
  other_name: string | null
  not_used: boolean
}
export interface QuestionnaireDictionaryItem { id: UUID; code: string; name: string; is_active: boolean }
export type QuestionnaireDictionaryKind = 'beneficial_owner_bases' | 'beneficial_owner_absence_reasons'
export interface QuestionnaireFieldSetting {
  field: string
  label: string
  enabled: boolean
  required: boolean
  required_available: boolean
  required_unavailable_reason: string | null
}
export const questionnaireServerFields = new Set([
  'id', 'application_id', 'created_at', 'updated_at', 'field_sources',
  'questionnaire_completed_at', 'confidence', 'recognition_confidence',
])
export const questionnaireWritePayload = (data: object): Record<string, unknown> =>
  Object.fromEntries(Object.entries(data).filter(([key]) => !questionnaireServerFields.has(key)))
