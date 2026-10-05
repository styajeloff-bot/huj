import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createExchangeApi } from '../api/exchangeApi'
import type { DealerOption } from '../types'

export const useDealerOptionsStore = defineStore('dealerOptions', () => {
  const options = ref<DealerOption[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const config = useRuntimeConfig()
  const api = createExchangeApi(config)

  async function fetchOptions() {
    if (loaded.value) return
    loading.value = true
    try {
      const data = await api.getDealerOptions()
      options.value = data.options
      loaded.value = true
    } catch (error) {
      console.error('Failed to fetch dealer options:', error)
    } finally {
      loading.value = false
    }
  }

  function reset() {
    options.value = []
    loaded.value = false
  }

  return {
    options,
    loading,
    loaded,
    fetchOptions,
    reset,
  }
})
