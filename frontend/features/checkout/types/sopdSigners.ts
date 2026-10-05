export type SopdSigningMethod = 'sms' | 'file'

export type SopdSignerRole = 'director_applicant' | 'director_management_company' | 'founder' | 'beneficiary' | 'representative'

export interface SopdSignerCandidate {
  key: string
  full_name: string
  role: SopdSignerRole
  role_label: string
  inn?: string | null
  share?: string | null
  signing_method: SopdSigningMethod
  source: string
  sort_order: number
}
