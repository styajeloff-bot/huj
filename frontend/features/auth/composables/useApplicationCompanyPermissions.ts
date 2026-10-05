import { computed, onScopeDispose, ref, watch } from 'vue'
import { isUuid } from '~/types/ids'

interface CompanyPermissions {
  id: string
  can_create_applications: boolean
}

/** Local capability projection for an explicit target; never changes active auth. */
export const useApplicationCompanyPermissions = (
  selectedCompany: () => unknown,
  primaryCanCreate: () => boolean,
) => {
  const config = useRuntimeConfig()
  const loading = ref(false)
  const error = ref('')
  const resolvedCompany = ref<string | null>(null)
  const createAllowed = ref(false)
  let generation = 0
  let disposed = false
  const hasSelection = computed(() => selectedCompany() !== undefined && selectedCompany() !== null)

  const canCreate = computed(() => {
    if (!hasSelection.value) return primaryCanCreate()
    const selected = selectedCompany()
    return isUuid(selected) && resolvedCompany.value === selected && !loading.value && createAllowed.value
  })

  const refresh = async () => {
    const request = ++generation
    const selected = selectedCompany()
    resolvedCompany.value = null
    createAllowed.value = false
    error.value = ''
    loading.value = false
    if (!isUuid(selected)) return
    loading.value = true
    try {
      const response = await $fetch<{ companies: CompanyPermissions[] }>('/api/v1/users/me/companies', {
        baseURL: config.public.apiBase,
        credentials: 'include',
      })
      if (disposed || generation !== request || selectedCompany() !== selected) return
      const membership = response.companies.find(company => company.id === selected)
      resolvedCompany.value = selected
      createAllowed.value = membership?.can_create_applications === true
    } catch {
      if (!disposed && generation === request) error.value = 'Не удалось проверить права выбранной компании.'
    } finally {
      if (!disposed && generation === request) loading.value = false
    }
  }

  // Invalidate synchronously, before a click can use the previous selection.
  watch(selectedCompany, refresh, { immediate: true, flush: 'sync' })
  onScopeDispose(() => { disposed = true; generation++ })
  return { canCreate, hasSelection, loading, error, refresh }
}
