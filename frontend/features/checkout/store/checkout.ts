import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { clearLegacy, useScopedStorage } from '~/features/auth/composables/useScopedStorage'
import type { QuestionnaireData } from '~/features/applications/constants/application'
import type { CommerceApplicationItem, CommerceCheckoutLine } from '~/features/commerce/types'
import { type CatalogId, type UUID, safeRandomUuid } from '~/types/ids'
import { normalizeCheckoutStep } from '../utils/steps'
import { useAuthStore } from '~/features/auth/store/auth'

export interface Vehicle {
  vehicle_id?: UUID
  id?: UUID
  modification_id?: CatalogId
  complectation_id?: CatalogId
  vin?: string
  mark_name: string
  model_name: string
  group_name?: string
  configuration_name?: string
  year?: number
  vehicle_year?: number
  color?: string
  allow_overstock?: boolean
  quantity?: number
  base_price?: number
  discount_price?: number
  custom_price?: number | null
  comment?: string
  equipments?: Array<{ equipment_code: string; price?: number | null }>
  services?: Array<{ service_code: string; price?: number | null }>
  leasing_purpose?: string | null
  leasing_purposes?: string[] | null
  leasing_purpose_comment?: string | null
  region?: string | null
  regions?: string[]
  effective_price?: number
  price_from?: number
  images?: string[] | readonly string[]
  [key: string]: unknown
}

export interface Calculation {
  total_amount: number
  down_payment: number
  down_payment_percent: number
  lease_term_months: number
  buyout_amount?: number
  selected_support?: Record<UUID, UUID[]>
  vehicle_quantities?: Record<string, number>
  support_per_vehicle?: unknown[]
  support_per_program?: unknown[]
  support_program_details?: unknown[]
  calculations_per_vehicle?: unknown[]
  eligible_support_program_ids_by_vehicle?: unknown[]
  calculation?: {
    monthlyPayment?: number
    rate?: number
    markup?: number
    totalCost?: number
    totalInterest?: number
    buyoutAmount?: number
    vatRefund?: number
    profitTaxSavings?: number
    totalSavings?: number
  }
  [key: string]: unknown
}

interface CheckoutForm {
  name: string
  companyNameOrInn: string
  email: string
  agreement: boolean
  selectedLeasingCompanies: UUID[]
  selectedDocuments: Record<string, UUID | UUID[] | null>
  uploadedFiles: Record<string, File | File[]>
}

type ApplicationStage = 'leasing_companies' | 'company_data' | 'accounting' | 'manual_input' | 'documents' | 'questionnaire' | 'pdf' | 'completed'

export interface AccountingData {
  inn: string
  fetch_status: 'success' | 'not_found' | 'failed' | 'pending' | 'fetching'
  cached?: boolean
  stale?: boolean
  skipped?: boolean
  payload?: Record<string, unknown> | null
}

export interface ApplicationCompanyPayload {
  id?: UUID
  name: string
  inn?: string | null
  kpp?: string | null
  ogrn?: string | null
  legal_address?: string | null
  actual_address?: string | null
  manager_name?: string | null
  entity_type?: string | null
  phone?: string | null
  email?: string | null
  [key: string]: unknown
}
type ReviewTier = 'basic' | 'extended' | 'maximum'

const CHECKOUT_STATE_KEY = 'checkout-state'

export const useCheckoutStore = defineStore('checkout', () => {
  const authStore = useAuthStore()
  const storage = useScopedStorage<Record<string, unknown>>(CHECKOUT_STATE_KEY)
  // Drop the pre-scope unscoped key from old builds so it doesn't leak into a
  // user's namespace. Safe to run on every store init — it's a single
  // localStorage.removeItem on a fixed key.
  clearLegacy(CHECKOUT_STATE_KEY)

  const currentStep = ref(1)
  const currentStage = ref<ApplicationStage>('leasing_companies')
  const applicationId = ref<UUID | null>(null)
  const applicationCreateIdempotencyKey = ref<string | null>(null)
  const selectedCompanyId = ref<UUID | null>(null)
  const selectedApplicationCompany = ref<ApplicationCompanyPayload | null>(null)
  const vehicles = ref<Vehicle[]>([])
  const commerceItems = ref<CommerceCheckoutLine[]>([])
  const applicationItems = ref<CommerceApplicationItem[]>([])
  const calculation = ref<Calculation | null>(null)
  const questionnaireProgress = ref(0)
  const questionnaireData = ref<QuestionnaireData>({})
  const questionnaireSubStep = ref(1)
  const completedSubSteps = ref<number[]>([])
  const selectedTier = ref<ReviewTier>('basic')
  const sourcePurchaseOrderId = ref<UUID | null>(null)
  const accountingData = ref<AccountingData | null>(null)

  const form = ref<CheckoutForm>({
    name: '',
    companyNameOrInn: '',
    email: '',
    agreement: false,
    selectedLeasingCompanies: [],
    selectedDocuments: {},
    uploadedFiles: {}
  })
  
  const loadStateFromStorage = () => {
    if (process.client) {
      const state = storage.get() as Record<string, unknown> | null
      if (state) {
        try {
          currentStep.value = normalizeCheckoutStep(state.currentStep)
          currentStage.value = (state.currentStage as ApplicationStage) || 'leasing_companies'
          applicationId.value = (state.applicationId as UUID | null) || null
          applicationCreateIdempotencyKey.value = (state.applicationCreateIdempotencyKey as string | null) || null
          selectedCompanyId.value = (state.selectedCompanyId as UUID | null) ?? null
          selectedApplicationCompany.value = (state.selectedApplicationCompany as ApplicationCompanyPayload | null) ?? null
          vehicles.value = (state.vehicles as Vehicle[]) || []
          commerceItems.value = (state.commerceItems as CommerceCheckoutLine[]) || []
          applicationItems.value = (state.applicationItems as CommerceApplicationItem[]) || []
          calculation.value = (state.calculation as Calculation | null) || null
          questionnaireProgress.value = (state.questionnaireProgress as number) || 0
          questionnaireData.value = (state.questionnaireData as QuestionnaireData) || {}
          questionnaireSubStep.value = (state.questionnaireSubStep as number) || 1
          completedSubSteps.value = (state.completedSubSteps as number[]) || []
          selectedTier.value = (state.selectedTier as ReviewTier) || 'basic'
          accountingData.value = (state.accountingData as AccountingData | null) || null
          form.value = {
            ...form.value,
            ...(state.form as Partial<CheckoutForm> | undefined),
            uploadedFiles: {}
          }
        } catch (e) {
          console.error('❌ Ошибка загрузки состояния при инициализации:', e)
        }
      }
    }
  }

  loadStateFromStorage()

  const isSingleCarMode = computed(() => {
    return vehicles.value.length === 1
  })

  const isMultipleCarsMode = computed(() => {
    return vehicles.value.length > 1
  })

  const totalAmount = computed(() => {
    return vehicles.value.reduce((sum, vehicle) => {
      const price = Number(vehicle.custom_price) || Number(vehicle.discount_price) || Number(vehicle.base_price) || 0
      return sum + price * (vehicle.quantity || 1)
    }, 0)
  })

  const setVehicles = (newVehicles: Vehicle[]) => {
    vehicles.value = newVehicles
    saveState()
  }

  const setCommerceItems = (newItems: CommerceCheckoutLine[]) => {
    commerceItems.value = newItems
    saveState()
  }

  const setApplicationItems = (newItems: CommerceApplicationItem[]) => {
    applicationItems.value = newItems
    saveState()
  }

  const setCalculation = (newCalculation: Calculation | null) => {
    calculation.value = newCalculation
    saveState()
  }

  const setStep = (step: number) => {
    currentStep.value = normalizeCheckoutStep(step)
    saveState()
  }

  const setStage = (stage: ApplicationStage) => {
    currentStage.value = stage
    saveState()
  }

  const setApplicationId = (id: UUID) => {
    applicationId.value = id
    saveState()
  }

  const startApplicationCreateAttempt = () => {
    applicationCreateIdempotencyKey.value = safeRandomUuid()
    saveState()
    return applicationCreateIdempotencyKey.value
  }

  const getApplicationCreateIdempotencyKey = () => (
    applicationCreateIdempotencyKey.value || startApplicationCreateAttempt()
  )

  const clearApplicationCreateIdempotencyKey = () => {
    applicationCreateIdempotencyKey.value = null
    saveState()
  }

  const setSelectedCompanyId = (id: UUID | null) => {
    selectedCompanyId.value = id
    saveState()
  }

  const setSelectedApplicationCompany = (company: ApplicationCompanyPayload | null) => {
    selectedApplicationCompany.value = company
    saveState()
  }

  const setAccountingData = (data: AccountingData | null) => {
    accountingData.value = data
    saveState()
  }

  const updateForm = (updates: Partial<CheckoutForm>) => {
    form.value = { ...form.value, ...updates }
    saveState()
  }

  const updateQuestionnaireData = (updates: Partial<QuestionnaireData>) => {
    questionnaireData.value = { ...questionnaireData.value, ...updates }
    updateQuestionnaireProgress()
    saveState()
  }

  const resetQuestionnaireData = () => {
    questionnaireData.value = {}
    questionnaireProgress.value = 0
    questionnaireSubStep.value = 1
    completedSubSteps.value = []
    accountingData.value = null
    saveState()
  }

  const setQuestionnaireSubStep = (step: number) => {
    questionnaireSubStep.value = step
    saveState()
  }

  const setSubStepCompleted = (step: number, completed: boolean) => {
    const alreadyCompleted = completedSubSteps.value.includes(step)
    if (completed && !alreadyCompleted) {
      completedSubSteps.value.push(step)
      saveState()
    } else if (!completed && alreadyCompleted) {
      completedSubSteps.value = completedSubSteps.value.filter((item) => item !== step)
      saveState()
    }
  }

  const markSubStepCompleted = (step: number) => setSubStepCompleted(step, true)

  const isSubStepUnlocked = (step: number) => {
    if (step === 1) return true
    return completedSubSteps.value.includes(step - 1)
  }

  const updateQuestionnaireProgress = () => {
    const requiredFields = [
      'full_company_name', 'short_company_name', 'inn', 'ogrn', 'kpp', 'okpo', 'okato',
      'okved_main', 'legal_form', 'legal_address', 'actual_address',
      'phone', 'email',
      'director_surname', 'director_first_name',
      'director_citizenship', 'director_share_percentage',
      'director_birth_date', 'director_birth_country', 'director_birth_place',
      'director_passport_series', 'director_passport_number',
      'director_passport_issue_date', 'director_passport_department_code', 'director_passport_issued_by',
      'director_registration_country', 'director_registration_postal_code', 'director_registration_address',
      'director_registration_house', 'director_registration_date',
      'employees_count', 'questionnaire_date', 'registration_department', 
      'registration_country', 'registration_city'
    ]
    
    let filledCount = 0
    
    requiredFields.forEach(field => {
      const value = questionnaireData.value[field as keyof QuestionnaireData]
      if (field === 'director_share_percentage') {
        if (value !== undefined && value !== null) filledCount++
      } else {
        if (value !== undefined && value !== null && value !== '') filledCount++
      }
    })
    
    if (questionnaireData.value.director_patronymic || questionnaireData.value.director_no_patronymic) {
      filledCount++
    }
    
    questionnaireProgress.value = Math.round((filledCount / (requiredFields.length + 1)) * 100)
  }

  const getStageProgress = (stage: ApplicationStage): number => {
    switch (stage) {
      case 'leasing_companies':
        // Stage is completed when company is selected
        return selectedCompanyId.value || selectedApplicationCompany.value ? 100 : 0
      case 'company_data':
        // Company data is always 100% (auto-filled)
        return 100
      case 'accounting':
        // Optional step: counted as complete if fetched (any status) or user skipped
        return accountingData.value ? 100 : 0
      case 'manual_input':
        // Manual input progress based on required fields
        return 0 // Will be calculated by component
      case 'documents':
        return Object.keys(form.value.selectedDocuments).length > 0 || 
               Object.keys(form.value.uploadedFiles).length > 0 ? 100 : 0
      default:
        return 0
    }
  }

  const setSelectedTier = (tier: ReviewTier) => {
    selectedTier.value = tier
    saveState()
  }

  const reset = () => {
    currentStep.value = 1
    currentStage.value = 'leasing_companies'
    applicationId.value = null
    applicationCreateIdempotencyKey.value = null
    selectedCompanyId.value = null
    selectedApplicationCompany.value = null
    vehicles.value = []
    commerceItems.value = []
    applicationItems.value = []
    calculation.value = null
    questionnaireProgress.value = 0
    questionnaireData.value = {}
    questionnaireSubStep.value = 1
    completedSubSteps.value = []
    selectedTier.value = 'basic'
    accountingData.value = null
    form.value = {
      name: '',
      companyNameOrInn: '',
      email: '',
      agreement: false,
      selectedLeasingCompanies: [],
      selectedDocuments: {},
      uploadedFiles: {}
    }
    clearState()
  }

  const serializableState = () => ({
    currentStep: currentStep.value,
    currentStage: currentStage.value,
    applicationId: applicationId.value,
    applicationCreateIdempotencyKey: applicationCreateIdempotencyKey.value,
    selectedCompanyId: selectedCompanyId.value,
    selectedApplicationCompany: selectedApplicationCompany.value,
    vehicles: vehicles.value,
    commerceItems: commerceItems.value,
    applicationItems: applicationItems.value,
    calculation: calculation.value,
    questionnaireProgress: questionnaireProgress.value,
    questionnaireData: questionnaireData.value,
    questionnaireSubStep: questionnaireSubStep.value,
    completedSubSteps: completedSubSteps.value,
    selectedTier: selectedTier.value,
    accountingData: accountingData.value,
    form: {
      ...form.value,
      uploadedFiles: {},
    },
  })

  const saveState = () => {
    if (process.client) {
      storage.set(serializableState())
    }
  }

  const loadState = () => {
    if (process.client) {
      const state = storage.get() as Record<string, unknown> | null
      if (state) {
        try {
          currentStep.value = normalizeCheckoutStep(state.currentStep)
          currentStage.value = (state.currentStage as ApplicationStage) || 'leasing_companies'
          applicationId.value = (state.applicationId as UUID | null) || null
          applicationCreateIdempotencyKey.value = (state.applicationCreateIdempotencyKey as string | null) || null
          selectedCompanyId.value = (state.selectedCompanyId as UUID | null) ?? null
          selectedApplicationCompany.value = (state.selectedApplicationCompany as ApplicationCompanyPayload | null) ?? null
          vehicles.value = (state.vehicles as Vehicle[]) || []
          commerceItems.value = (state.commerceItems as CommerceCheckoutLine[]) || []
          applicationItems.value = (state.applicationItems as CommerceApplicationItem[]) || []
          calculation.value = (state.calculation as Calculation | null) || null
          questionnaireProgress.value = (state.questionnaireProgress as number) || 0
          questionnaireData.value = (state.questionnaireData as QuestionnaireData) || {}
          questionnaireSubStep.value = (state.questionnaireSubStep as number) || 1
          completedSubSteps.value = (state.completedSubSteps as number[]) || []
          selectedTier.value = (state.selectedTier as ReviewTier) || 'basic'
          accountingData.value = (state.accountingData as AccountingData | null) || null
          form.value = {
            ...form.value,
            ...(state.form as Partial<CheckoutForm> | undefined),
            uploadedFiles: {}
          }
          return true
        } catch (e) {
          console.error('❌ Ошибка загрузки состояния checkout:', e)
          clearState()
          return false
        }
      }
    }
    return false
  }

  const clearState = () => {
    if (process.client) {
      storage.remove()
    }
  }

  const migrateGuestStateToCurrentUser = (): boolean => {
    if (!process.client || !authStore.user?.id) return false

    const guestKey = `${CHECKOUT_STATE_KEY}:guest`
    const userKey = `${CHECKOUT_STATE_KEY}:u${authStore.user.id}`

    try {
      const guestRaw = window.localStorage.getItem(guestKey)
      if (guestRaw === null) return loadState()
      JSON.parse(guestRaw)
      window.localStorage.setItem(userKey, guestRaw)
      window.localStorage.removeItem(guestKey)
      return loadState()
    } catch {
      try {
        window.localStorage.removeItem(guestKey)
      } catch {
        // Storage can be unavailable in privacy mode; keep in-memory state.
      }
      return false
    }
  }

  return {
    currentStep,
    currentStage,
    applicationId,
    applicationCreateIdempotencyKey,
    selectedCompanyId,
    selectedApplicationCompany,
    vehicles,
    commerceItems,
    applicationItems,
    calculation,
    form,
    questionnaireProgress,
    questionnaireData,
    questionnaireSubStep,
    completedSubSteps,
    selectedTier,
    sourcePurchaseOrderId,
    accountingData,
    isSingleCarMode,
    isMultipleCarsMode,
    totalAmount,
    setVehicles,
    setCommerceItems,
    setApplicationItems,
    setCalculation,
    setStep,
    setStage,
    setApplicationId,
    startApplicationCreateAttempt,
    getApplicationCreateIdempotencyKey,
    clearApplicationCreateIdempotencyKey,
    setSelectedCompanyId,
    setSelectedApplicationCompany,
    setAccountingData,
    setSelectedTier,
    updateForm,
    updateQuestionnaireData,
    resetQuestionnaireData,
    updateQuestionnaireProgress,
    setQuestionnaireSubStep,
    setSubStepCompleted,
    markSubStepCompleted,
    isSubStepUnlocked,
    getStageProgress,
    reset,
    saveState,
    loadState,
    clearState,
    migrateGuestStateToCurrentUser
  }
})
