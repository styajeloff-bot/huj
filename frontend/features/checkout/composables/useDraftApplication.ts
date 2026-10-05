/**
 * Phase 17 — application checkout flow helpers.
 *
 * Wraps the sub-resource PUTs introduced by Phase 16:
 * `/applications/{id}/conditions|company|vehicles|leasing-companies|questionnaire`.
 *
 * The application itself is created via `POST /applications/draft`
 * — see `createApplication()` below for a thin wrapper that
 * reuses the cart + calculation already living in `checkoutStore`.
 */
import { persistedLeasingPurposes } from '~/features/checkout/utils/leasingPurposes'
import { questionnaireWritePayload } from '~/features/questionnaire/types'
import type { QuestionnaireData } from '~/features/applications/constants/application'
import { useNotificationCompanyContext, useNotificationCompanyRequest } from '~/features/notifications'
import { useAuthStore } from '~/features/auth/store/auth'
import type { ApplicationCompanyPayload } from '~/features/checkout/store/checkout'
import { buildApplicationCalculationPayload } from '~/features/checkout/utils/applicationCalculation'
import { type CatalogId, type UUID, safeRandomUuid } from '~/types/ids'
import { useStorefront } from '~/features/storefront'

interface ApplicationCreateResponse {
  application_id: UUID
  status: string
}

/**
 * `GET /api/v1/applications/{id}` returns a **flat** object — all the
 * application fields plus nested `vehicles`, `questionnaire`,
 * `calculation`, `leasing_company_applications`, `selected_companies_info`,
 * `comments`. There is no outer `application` envelope. Typing this loosely
 * with `Record<string, unknown>` — callers narrow individual fields.
 */
type ApplicationFetchResponse = Record<string, unknown> & {
  id: UUID
  company_id?: UUID | null
}

const buildQuestionnairePayload = (payload: QuestionnaireData): Record<string, unknown> => questionnaireWritePayload(payload)

interface VehiclePayload {
  product_id?: UUID | null
  modification_id?: CatalogId | null
  allow_overstock?: boolean
  quantity?: number
  custom_price?: number | null
  comment?: string | null
  is_model_order?: boolean
  equipments?: Array<{ equipment_code: string; price?: number | null }>
  services?: Array<{ service_code: string; price?: number | null }>
  leasing_purpose?: string | null
  leasing_purposes?: string[] | null
  regions?: string[]
  region?: string | null
  mark_name?: string | null
  model_name?: string | null
}

export const useDraftApplication = (notificationCompanyContext = useNotificationCompanyContext()) => {
  const { request: notificationRequest } = useNotificationCompanyRequest(notificationCompanyContext)
  const config = useRuntimeConfig()
  const authStore = useAuthStore()
  const checkoutStore = useCheckoutStore()
  const { apiPath, slug } = useStorefront()

  const apiBase = () => config.public.apiBase

  const buildVehicleRegions = (vehicle: typeof checkoutStore.vehicles[number]) => {
    if (Array.isArray(vehicle.regions)) return vehicle.regions
    return vehicle.region ? [vehicle.region] : []
  }

  const buildVehiclesPayload = (): VehiclePayload[] =>
    checkoutStore.vehicles.map((v) => {
      const vehicleId = v.vehicle_id ?? null
      return {
        product_id: vehicleId,
        modification_id: v.modification_id ?? null,
        quantity: v.quantity || 1,
        allow_overstock: v.allow_overstock === true,
        custom_price:
          v.custom_price != null
            ? Number(v.custom_price)
            : v.discount_price != null
              ? Number(v.discount_price)
              : v.base_price != null
                ? Number(v.base_price)
                : null,
        comment: v.comment || null,
        is_model_order: !vehicleId && !!v.modification_id,
        equipments: Array.isArray(v.equipments) ? v.equipments : [],
        services: Array.isArray(v.services) ? v.services : [],
        leasing_purpose: persistedLeasingPurposes(v)[0] ?? null,
        leasing_purposes: persistedLeasingPurposes(v),
        regions: buildVehicleRegions(v),
        region: buildVehicleRegions(v)[0] || null,
        mark_name: v.mark_name || null,
        model_name: v.model_name || null,
      }
    })

  const buildCalculationPayload = () =>
    buildApplicationCalculationPayload(checkoutStore.calculation)

  const buildCompanyDraftPayload = () => {
    if (checkoutStore.selectedCompanyId) {
      return { company_id: checkoutStore.selectedCompanyId }
    }

    const selectedApplicationCompany = checkoutStore.selectedApplicationCompany as ApplicationCompanyPayload | null
    if (authStore.isDealer && selectedApplicationCompany) {
      return { company: selectedApplicationCompany }
    }

    return null
  }

  const createApplication = async (idempotencyKey: string = safeRandomUuid()): Promise<ApplicationCreateResponse> => {
    const companyPayload = buildCompanyDraftPayload()
    if (!companyPayload) {
      throw new Error('Не выбрана компания для заявки')
    }
    if (!authStore.canCreateApplications) {
      throw new Error('Создание заявок ограничено администратором компании. Если вас не устраивает такое положение, напишите в поддержку.')
    }
    if (!checkoutStore.vehicles.length) {
      throw new Error('Нет автомобилей для заявки')
    }
    return await notificationRequest<ApplicationCreateResponse>(apiPath('/applications/draft'), {
      method: 'POST',
      baseURL: apiBase(),
      credentials: 'include',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: {
        source_type: slug.value ? 'dealer_site' : 'platform',
        ...companyPayload,
        vehicles: buildVehiclesPayload(),
        calculation: buildCalculationPayload(),
        name: authStore.user?.name || checkoutStore.form.name,
        email: authStore.user?.email || checkoutStore.form.email,
      },
    })
  }

  const loadApplication = async (applicationId: UUID) =>
    await notificationRequest<ApplicationFetchResponse>(
      apiPath(`/applications/${applicationId}`),
      { baseURL: apiBase(), credentials: 'include' },
    )

  const updateConditions = async (applicationId: UUID) => {
    const calc = buildCalculationPayload()
    if (!calc) return
    await notificationRequest(apiPath(`/applications/${applicationId}/conditions`), {
      method: 'PUT',
      baseURL: apiBase(),
      credentials: 'include',
      body: {
        total_amount: calc.total_amount,
        down_payment: calc.down_payment,
        down_payment_percent: calc.down_payment_percent,
        lease_term_months: calc.lease_term_months,
        monthly_payment: calc.monthly_payment,
        total_cost: calc.total_cost,
        rate: calc.rate,
        total_interest: calc.total_interest,
        buyout_amount: calc.buyout_amount,
        vat_refund: calc.vat_refund,
        profit_tax_savings: calc.profit_tax_savings,
        total_savings: calc.total_savings,
        selected_support: calc.selected_support,
        support_per_vehicle: calc.support_per_vehicle,
        support_per_program: calc.support_per_program,
        support_program_details: calc.support_program_details,
        calculations_per_vehicle: calc.calculations_per_vehicle,
      },
    })
  }

  const updateCompany = async (
    applicationId: UUID,
    companyId: UUID,
  ) => {
    await notificationRequest(apiPath(`/applications/${applicationId}/company`), {
      method: 'PUT',
      baseURL: apiBase(),
      credentials: 'include',
      body: { company_id: companyId },
    })
  }

  const updateVehicles = async (applicationId: UUID) => {
    await notificationRequest(apiPath(`/applications/${applicationId}/vehicles`), {
      method: 'PUT',
      baseURL: apiBase(),
      credentials: 'include',
      body: { vehicles: buildVehiclesPayload() },
    })
  }

  const updateQuestionnaire = async (
    applicationId: UUID,
    payload: QuestionnaireData,
  ) => {
    await notificationRequest(apiPath(`/applications/${applicationId}/questionnaire`), {
      method: 'PUT',
      baseURL: apiBase(),
      credentials: 'include',
      body: buildQuestionnairePayload(payload),
    })
  }

  const updateLeasingCompanies = async (
    applicationId: UUID,
    leasingCompanyIds: UUID[],
  ) => {
    await notificationRequest(
      apiPath(`/applications/${applicationId}/leasing-companies`),
      {
        method: 'PUT',
        baseURL: apiBase(),
        credentials: 'include',
        body: { leasing_company_ids: leasingCompanyIds },
      },
    )
  }

  const submitApplication = async (applicationId: UUID) => {
    void applicationId
    // Parent applications now use the simplified active/rejected/issued
    // lifecycle. Checkout submit is represented by the saved questionnaire
    // and attached documents; LC child rows are created only later by the
    // admin manual distribution flow.
  }

  return {
    createApplication,
    loadApplication,
    updateConditions,
    updateCompany,
    updateVehicles,
    updateQuestionnaire,
    updateLeasingCompanies,
    submitApplication,
  }
}
