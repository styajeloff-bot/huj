import { ref, getCurrentScope, onScopeDispose } from 'vue'
import { useNotificationCompanyContext, useNotificationCompanyRequest } from '~/features/notifications'
import { clearLegacy, useScopedStorage } from '~/features/auth/composables/useScopedStorage'
import type { UUID } from '~/types/ids'

interface CompanyOkved {
  code: string
  description?: string
}

interface CompanyBank {
  bik?: string
  name?: string
}

interface CompanyFounder {
  name?: string
  share?: string | number | null
  share_percentage?: number
  surname?: string
  first_name?: string
  patronymic?: string
  inn?: string
  birth_date?: string
  birth_place?: string
  passport_series?: string
  passport_number?: string
  passport_issue_date?: string
  passport_department_code?: string
  passport_issued_by?: string
  registration_postal_code?: string
  registration_address?: string
  registration_house?: string
  registration_apartment?: string
  registration_date?: string
  actual_postal_code?: string
  actual_address?: string
  actual_house?: string
  actual_apartment?: string
  phone?: string
  email?: string
  share_nominal_value?: number
  share_paid_part?: number
}

interface CompanyData {
  enrichment_status?: 'pending' | 'fetching' | 'failed' | 'success'
  full_name?: string
  short_name?: string
  inn?: string
  ogrn?: string
  kpp?: string
  okpo?: string
  okato?: string
  main_okved?: CompanyOkved
  main_okved_code?: string
  main_okved_description?: string
  legal_address?: string
  bank?: CompanyBank
  bank_bik?: string
  bank_name?: string
  registration_department?: string
  city?: string
  legal_form?: string
  founders?: CompanyFounder[]
  [key: string]: unknown
}

type CompanyProfileResponse = CompanyData

// Shared state across all composable instances (singleton pattern)
const autofilledFields = ref<Record<string, boolean>>({})
const fieldConfidence = ref<Record<string, number>>({})
const loadingCompanyData = ref(false)
const companyDataLoaded = ref(false)
const companyDataError = ref('')
const companyExternalData = ref<CompanyData | null>(null)

function _parseShare(value: string | number | null | undefined): number | undefined {
  if (value === null || value === undefined) return undefined
  if (typeof value === 'number') return value
  const cleaned = String(value).replace('%', '').replace(',', '.').trim()
  const num = Number(cleaned)
  return Number.isFinite(num) ? num : undefined
}

function _splitFullName(fullName: string | null | undefined): { surname: string; first_name: string; patronymic: string } {
  if (!fullName) return { surname: '', first_name: '', patronymic: '' }
  const parts = fullName.trim().split(/\s+/)
  return {
    surname: parts[0] || '',
    first_name: parts[1] || '',
    patronymic: parts[2] || '',
  }
}

export const useCheckoutAutofill = (notificationCompanyContext = useNotificationCompanyContext()) => {
  let disposed = false
  if (getCurrentScope()) onScopeDispose(() => { disposed = true })
  let profileRequest = 0
  const { request: notificationRequest } = useNotificationCompanyRequest(notificationCompanyContext)
  const config = useRuntimeConfig()
  const checkoutStore = useCheckoutStore()
  const toast = useToast()

  const getFieldClasses = (fieldName: string): string => {
    const confidence = fieldConfidence.value[fieldName]
    if (confidence !== undefined && confidence > 0 && confidence < 0.4) {
      return 'border-yellow-400 bg-yellow-50'
    }
    return ''
  }

  const getFieldWarning = (fieldName: string): string | null => {
    const confidence = fieldConfidence.value[fieldName]
    if (confidence !== undefined && confidence > 0 && confidence < 0.4) {
      const percentage = Math.round(confidence * 100)
      return `⚠️ Пожалуйста, проверьте точность заполненного поля (точность распознавания: ${percentage}%)`
    }
    return null
  }

  // Passport autofill is not used anymore - remove this function if needed
  const autofillQuestionnaireFromPassport = (_mappedData: Record<string, unknown>, _confidenceData?: Record<string, number>) => {
    // deprecated — no-op
  }

  /**
   * Fetch company data from company profile (which includes external data)
   * Data is fetched in background after registration and stored in DB
   */
  const fetchCompanyData = async (companyId?: UUID | null) => {
    const request = ++profileRequest
    const context = notificationCompanyContext()
    loadingCompanyData.value = true
    companyDataError.value = ''
    companyDataLoaded.value = false

    try {
      const endpoint = companyId
        ? `/api/v1/companies/${companyId}/profile`
        : '/api/v1/companies/profile'

      // Fetch company profile which includes external data
      const companyData = await notificationRequest<CompanyProfileResponse>(endpoint, {
        method: 'GET',
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      if (disposed || request !== profileRequest || context !== notificationCompanyContext()) return

      // Store company data for component use
      companyExternalData.value = companyData || null

      // If no company data available yet, silently return (no error to user)
      if (!companyData) {
        loadingCompanyData.value = false
        return
      }

      // If data is still loading, silently return
      if (companyData.enrichment_status === 'pending' || companyData.enrichment_status === 'fetching') {
        loadingCompanyData.value = false
        return
      }

      // If fetch failed, silently return (don't bother user with external data errors)
      if (companyData.enrichment_status === 'failed') {
        loadingCompanyData.value = false
        return
      }

      if (companyData.enrichment_status === 'success') {
        const updates: Record<string, string | number | boolean | CompanyFounder[] | undefined> = {}
        const fieldsToAutofill: Record<string, boolean> = {}

        if (companyData.full_name) {
          updates.full_company_name = companyData.full_name
          fieldsToAutofill.full_company_name = true
        }

        if (companyData.short_name) {
          updates.short_company_name = companyData.short_name
          fieldsToAutofill.short_company_name = true
        }

        if (companyData.inn) {
          updates.inn = companyData.inn
          fieldsToAutofill.inn = true
        }

        if (companyData.ogrn) {
          updates.ogrn = companyData.ogrn
          fieldsToAutofill.ogrn = true
        }

        if (companyData.kpp) {
          updates.kpp = companyData.kpp
          fieldsToAutofill.kpp = true
        }

        if (companyData.okpo) {
          updates.okpo = companyData.okpo
          fieldsToAutofill.okpo = true
        }

        if (companyData.okato) {
          updates.okato = companyData.okato
          fieldsToAutofill.okato = true
        }

        // Support both nested (legacy) and flat (current) OKVED shape
        const okvedCode = companyData.main_okved?.code || companyData.main_okved_code
        const okvedDesc = companyData.main_okved?.description || companyData.main_okved_description
        if (okvedCode) {
          const okvedMain = okvedDesc
            ? `${okvedCode} - ${okvedDesc}`
            : okvedCode
          updates.okved_main = okvedMain
          fieldsToAutofill.okved_main = true
        }

        if (companyData.legal_address) {
          updates.legal_address = companyData.legal_address
          fieldsToAutofill.legal_address = true
        }

        // Support both nested (legacy) and flat (current) bank shape
        const bankBik = companyData.bank?.bik || companyData.bank_bik
        const bankName = companyData.bank?.name || companyData.bank_name
        if (bankBik) {
          updates.bik = bankBik
          fieldsToAutofill.bik = true
        }

        if (bankName) {
          updates.bank_name = bankName
          fieldsToAutofill.bank_name = true
        }

        if (companyData.registration_department) {
          updates.registration_department = companyData.registration_department
          fieldsToAutofill.registration_department = true
        }

        updates.registration_country = 'Россия'
        fieldsToAutofill.registration_country = true

        // Extract city from legal_address or use city field from company data
        if (companyData.city) {
          updates.registration_city = companyData.city.replace(/^г\.\s*/, '').trim()
          fieldsToAutofill.registration_city = true
        } else if (companyData.legal_address) {
          const cityMatch = companyData.legal_address.match(/г\.\s*([А-Яа-яЁё\-\s]+)/i) ||
                           companyData.legal_address.match(/город\s+([А-Яа-яЁё\-\s]+)/i)
          if (cityMatch) {
            updates.registration_city = cityMatch[1].trim()
            fieldsToAutofill.registration_city = true
          }
        }

        const today = new Date().toISOString().split('T')[0]
        updates.questionnaire_date = today
        fieldsToAutofill.questionnaire_date = true

        // Determine legal form from company data or INN length
        if (companyData.legal_form) {
          updates.legal_form = companyData.legal_form
          fieldsToAutofill.legal_form = true
        } else if (companyData.inn) {
          const innLength = companyData.inn.length
          if (innLength === 10) {
            updates.legal_form = 'ООО'
            fieldsToAutofill.legal_form = true
          } else if (innLength === 12) {
            updates.legal_form = 'ИП'
            fieldsToAutofill.legal_form = true
          }
        }

        if (companyData.founders && Array.isArray(companyData.founders) && companyData.founders.length > 0) {
          const founders = companyData.founders
            .map((f: CompanyFounder) => {
              const sharePercentage = _parseShare(f.share_percentage ?? f.share)
              const { surname, first_name, patronymic } = _splitFullName(f.name)
              return {
                type: 'individual' as const,
                share_encumbrance: '',
                citizenship: 'РФ',
                surname: f.surname || surname || '',
                first_name: f.first_name || first_name || '',
                patronymic: f.patronymic || patronymic || '',
                no_patronymic: !(f.patronymic || patronymic),
                inn: f.inn || '',
                snils: '',
                birth_date: f.birth_date || '',
                birth_place: f.birth_place || '',
                passport_series: f.passport_series || '',
                passport_number: f.passport_number || '',
                passport_issue_date: f.passport_issue_date || '',
                passport_department_code: f.passport_department_code || '',
                passport_issued_by: f.passport_issued_by || '',
                registration_country: 'Россия',
                registration_postal_code: f.registration_postal_code || '',
                registration_address: f.registration_address || '',
                registration_house: f.registration_house || '',
                registration_apartment: f.registration_apartment || '',
                registration_date: f.registration_date || '',
                actual_country: 'Россия',
                actual_postal_code: f.actual_postal_code || '',
                actual_address: f.actual_address || '',
                actual_house: f.actual_house || '',
                actual_apartment: f.actual_apartment || '',
                phone: f.phone || '',
                email: f.email || '',
                share_percentage: sharePercentage,
                share_nominal_value: f.share_nominal_value || undefined,
                share_paid_part: f.share_paid_part || undefined
              }
            })
            .filter((f) => f.share_percentage !== undefined && f.share_percentage >= 25)

          if (founders.length > 0) {
            updates.founders = founders
          }
        }

        autofilledFields.value = { ...autofilledFields.value, ...fieldsToAutofill }

        companyDataLoaded.value = true
      }
    } catch (_err: unknown) {
      // Don't show error to user — silently ignore
    } finally {
      if (!disposed && request === profileRequest && context === notificationCompanyContext()) loadingCompanyData.value = false
    }
  }

  const autofilledStorage = useScopedStorage<Record<string, boolean>>('checkout-autofilled-fields')
  const confidenceStorage = useScopedStorage<Record<string, unknown>>('checkout-field-confidence')
  clearLegacy('checkout-autofilled-fields')
  clearLegacy('checkout-field-confidence')

  const loadAutofilledFieldsFromStorage = () => {
    if (!process.client) return
    const savedAutofilledFields = autofilledStorage.get()
    if (savedAutofilledFields) autofilledFields.value = savedAutofilledFields
    const savedFieldConfidence = confidenceStorage.get()
    if (savedFieldConfidence) fieldConfidence.value = savedFieldConfidence as typeof fieldConfidence.value
  }

  const clearAutofillFlag = (fieldName: string) => {
    if (autofilledFields.value[fieldName]) {
      autofilledFields.value = { ...autofilledFields.value, [fieldName]: false }
      if (process.client) autofilledStorage.set(autofilledFields.value)
    }
  }

  return {
    autofilledFields,
    fieldConfidence,
    loadingCompanyData,
    companyDataLoaded,
    companyDataError,
    companyExternalData,
    getFieldClasses,
    getFieldWarning,
    autofillQuestionnaireFromPassport,
    fetchCompanyData,
    loadAutofilledFieldsFromStorage,
    clearAutofillFlag
  }
}
