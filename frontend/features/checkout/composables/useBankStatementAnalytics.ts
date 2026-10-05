import { ref, watch, type Ref } from 'vue'
import type { BankStatementAnalytics } from '../types/bankStatementAnalytics'
import type { UUID } from '~/types/ids'

type AnalyticsStatus = 'idle' | 'loading' | 'success' | 'error'

export const useBankStatementAnalytics = (
  companyId: Ref<UUID | null | undefined>,
) => {
  const config = useRuntimeConfig()
  const status = ref<AnalyticsStatus>('idle')
  const data = ref<BankStatementAnalytics | null>(null)
  const errorMessage = ref('')

  const refresh = async () => {
    const id = companyId.value
    if (!id) {
      status.value = 'idle'
      data.value = null
      errorMessage.value = ''
      return
    }

    status.value = 'loading'
    errorMessage.value = ''

    try {
      data.value = await $fetch<BankStatementAnalytics>(
        `/api/v1/bank-statements/companies/${id}/analytics`,
        {
          baseURL: config.public.apiBase,
          credentials: 'include',
        },
      )
      status.value = 'success'
    } catch (err: any) {
      data.value = null
      status.value = 'error'
      errorMessage.value = err?.data?.detail || err?.message || 'Не удалось загрузить финансовые показатели'
    }
  }

  watch(companyId, () => { void refresh() }, { immediate: true })

  return {
    status,
    data,
    errorMessage,
    refresh,
  }
}
