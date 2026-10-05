import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { createFastDealsApi, parseFastDealError } from '~/features/fast-deals/api/fastDealsApi'
import type {
  FastDealFilters,
  FastDealListItem,
  FastDealSource,
  FastDealStatus,
  FilterOptions,
} from '~/features/fast-deals/types'
import { isUuid, type UUID } from '~/types/ids'

export const FAST_DEALS_PAGE_SIZE = 20

/** Form state of the filter bar; an empty string means «not set». */
export interface FastDealListFilterState {
  number: string
  client_inn: string
  client_company_id: UUID | ''
  leasing_company_id: UUID | ''
  dealer_company_id: UUID | ''
  source_type: FastDealSource | ''
  status: FastDealStatus | ''
}

const emptyFilters = (): FastDealListFilterState => ({
  number: '',
  client_inn: '',
  client_company_id: '',
  leasing_company_id: '',
  dealer_company_id: '',
  source_type: '',
  status: '',
})

const emptyFilterOptions = (): FilterOptions => ({ clients: [], leasing_companies: [], dealers: [] })

/**
 * State of the «Регистрация сделки» list: server-scoped page, filters (applied after the server
 * restricts the visible set), reset and pagination. The role decides which company filters make
 * sense: the leasing company filter is for dealers and administrators, the dealer filter for
 * leasing companies, distributors and administrators.
 */
export function useFastDealsList() {
  const config = useRuntimeConfig()
  const route = useRoute()
  const authStore = useAuthStore()

  const companyContext = computed<UUID | undefined>(() =>
    isUuid(route.query.notification_company_id) ? route.query.notification_company_id : undefined,
  )
  const api = createFastDealsApi(config, () => companyContext.value)

  const items = ref<FastDealListItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const loading = ref(true)
  const error = ref('')
  const forbidden = ref(false)
  const filterOptions = ref<FilterOptions>(emptyFilterOptions())
  const filterOptionsError = ref(false)
  const filters = reactive<FastDealListFilterState>(emptyFilters())

  const canCreate = computed(() => authStore.isDealer || authStore.isLeasingCompany)
  const showLeasingCompanyFilter = computed(() => authStore.isDealer || authStore.isCarCraftEmployee)
  const showDealerFilter = computed(
    () => authStore.isLeasingCompany || authStore.isDistributor || authStore.isCarCraftEmployee,
  )
  const pages = computed(() => Math.max(1, Math.ceil(total.value / FAST_DEALS_PAGE_SIZE)))
  const hasActiveFilters = computed(() => Object.values(filters).some(value => value !== ''))

  const buildQuery = (): FastDealFilters => {
    const query: FastDealFilters = { page: page.value, page_size: FAST_DEALS_PAGE_SIZE }
    const number = filters.number.trim()
    if (number) query.number = number
    const inn = filters.client_inn.replace(/\D+/g, '')
    if (inn) query.client_inn = inn
    if (filters.client_company_id) query.client_company_id = filters.client_company_id
    if (showLeasingCompanyFilter.value && filters.leasing_company_id) {
      query.leasing_company_id = filters.leasing_company_id
    }
    if (showDealerFilter.value && filters.dealer_company_id) query.dealer_company_id = filters.dealer_company_id
    if (filters.source_type) query.source_type = filters.source_type
    if (filters.status) query.status = filters.status
    return query
  }

  // Only the latest request may change the screen: a slow earlier answer must not overwrite it.
  let requestSeq = 0

  const fetchList = async (): Promise<void> => {
    const seq = ++requestSeq
    loading.value = true
    error.value = ''
    forbidden.value = false
    try {
      const response = await api.list(buildQuery())
      if (seq !== requestSeq) return
      items.value = response.items ?? []
      total.value = response.total ?? 0
      if (items.value.length === 0 && total.value > 0 && page.value > pages.value) {
        // The page vanished (deals were removed meanwhile): continue from the last existing one.
        page.value = pages.value
        return fetchList()
      }
    } catch (cause) {
      if (seq !== requestSeq) return
      const failure = parseFastDealError(cause)
      items.value = []
      total.value = 0
      if (failure.status === 401) {
        await authStore.checkAuth()
        error.value = 'Требуется авторизация. Войдите в систему и повторите попытку.'
      } else if (failure.status === 403) {
        forbidden.value = true
      } else {
        error.value = failure.detail
      }
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  const fetchFilterOptions = async (): Promise<void> => {
    filterOptionsError.value = false
    try {
      filterOptions.value = { ...emptyFilterOptions(), ...(await api.filterOptions()) }
    } catch {
      filterOptions.value = emptyFilterOptions()
      filterOptionsError.value = true
    }
  }

  const applyFilters = (): void => {
    page.value = 1
    void fetchList()
  }

  const resetFilters = (): void => {
    debouncedApply.cancel()
    Object.assign(filters, emptyFilters())
    applyFilters()
  }

  const changePage = (next: number): void => {
    if (next < 1 || next > pages.value || next === page.value) return
    page.value = next
    void fetchList()
  }

  // Text filters are applied while typing, selects immediately.
  let applyTimer: ReturnType<typeof setTimeout> | null = null
  const debouncedApply = Object.assign(
    () => {
      if (applyTimer) clearTimeout(applyTimer)
      applyTimer = setTimeout(() => {
        applyTimer = null
        applyFilters()
      }, 400)
    },
    {
      cancel: () => {
        if (applyTimer) clearTimeout(applyTimer)
        applyTimer = null
      },
    },
  )

  const load = async (): Promise<void> => {
    await Promise.all([fetchList(), fetchFilterOptions()])
  }

  // The set of visible deals depends on the active company (company switcher / notification link).
  watch([() => authStore.activeCompanyId, companyContext], () => {
    debouncedApply.cancel()
    Object.assign(filters, emptyFilters())
    page.value = 1
    void load()
  })

  onBeforeUnmount(() => {
    debouncedApply.cancel()
    requestSeq++
  })

  return {
    items,
    total,
    page,
    pages,
    loading,
    error,
    forbidden,
    filters,
    filterOptions,
    filterOptionsError,
    hasActiveFilters,
    canCreate,
    showLeasingCompanyFilter,
    showDealerFilter,
    load,
    fetchList,
    applyFilters,
    debouncedApply,
    resetFilters,
    changePage,
  }
}
