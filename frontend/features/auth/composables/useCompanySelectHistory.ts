import type { UUID } from '~/types/ids'

export interface CompanyOption {
  id: UUID
  name: string
  inn: string | null
  role?: string | null
  position_id?: UUID | null
  position_name?: string | null
  is_active?: boolean
}

export const useCompanySelectHistory = () => {
  const config = useRuntimeConfig()
  const checkoutStore = useCheckoutStore()
  const toast = useToast()

  const companies = ref<CompanyOption[]>([])
  const selectedCompanyId = ref<UUID | null>(null)
  const loadingCompanies = ref(false)
  const loadingSelected = ref(false)
  const savingSelected = ref(false)
  const companiesLoaded = ref(false)

  const applySelectedCompany = (companyId: UUID | null) => {
    selectedCompanyId.value = companyId
    checkoutStore.setSelectedCompanyId(companyId)
    return companyId
  }

  const getResolvedSelectedCompanyId = (companyId: UUID | null) => {
    const availableCompanyIds = new Set(companies.value.map((company) => company.id))

    if (companyId != null && availableCompanyIds.has(companyId)) {
      return companyId
    }

    if (companies.value.length === 1) {
      return companies.value[0].id
    }

    return null
  }

  const loadCompanies = async () => {
    loadingCompanies.value = true
    try {
      const res = await $fetch<{ companies: CompanyOption[] }>('/api/v1/users/me/companies', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      companies.value = res.companies || []
      companiesLoaded.value = true
      return companies.value
    } catch (e) {
      companies.value = []
      companiesLoaded.value = true
      throw e
    } finally {
      loadingCompanies.value = false
    }
  }

  const loadSelectedCompany = async () => {
    loadingSelected.value = true
    try {
      const res = await $fetch<{ company_id: UUID | null }>('/api/v1/users/me/company-select-history', {
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      return applySelectedCompany(getResolvedSelectedCompanyId(res.company_id ?? null))
    } catch (e) {
      return applySelectedCompany(getResolvedSelectedCompanyId(null))
    } finally {
      loadingSelected.value = false
    }
  }

  const selectCompany = async (companyId: UUID) => {
    savingSelected.value = true
    try {
      await $fetch('/api/v1/users/me/company-select-history', {
        method: 'PUT',
      body: { company_id: companyId },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
      applySelectedCompany(companyId)
    } catch (e) {
      toast.error('Не удалось сохранить выбор компании')
      throw e
    } finally {
      savingSelected.value = false
    }
  }

  return {
    companies,
    selectedCompanyId,
    loadingCompanies,
    loadingSelected,
    savingSelected,
    companiesLoaded,
    loadCompanies,
    loadSelectedCompany,
    selectCompany
  }
}
