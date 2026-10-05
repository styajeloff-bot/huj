import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createExchangeApi } from '../api/exchangeApi'
import type { ExchangeRequest, ExchangeRequestId, ExchangeRequestStatus, ExchangeBid } from '../types'
import { useAuthStore } from '~/features/auth/store/auth'
import type { UUID } from '~/types/ids'

export const useExchangeRequestsStore = defineStore('exchangeRequests', () => {
  const requests = ref<ExchangeRequest[]>([])
  const currentRequest = ref<ExchangeRequest | null>(null)
  const loading = ref(false)
  const statusFilter = ref<ExchangeRequestStatus>('open')
  const pagination = ref({ page: 1, limit: 20, total: 0, pages: 0 })
  const statusCounts = ref<{ open: number; deal: number; archived: number }>({ open: 0, deal: 0, archived: 0 })
  const config = useRuntimeConfig()
  const api = createExchangeApi(config)
  const authStore = useAuthStore()
  let listVersion = 0

  // ---- LC actions ----

  async function fetchLcRequests(status?: ExchangeRequestStatus, page: number = 1, notificationCompanyId?: UUID) {
    const version = ++listVersion
    const contextualApi = createExchangeApi(config, () => notificationCompanyId)
    loading.value = true
    requests.value = []
    statusCounts.value = { open: 0, deal: 0, archived: 0 }
    try {
      const s = status || statusFilter.value
      const [data, counts] = await Promise.all([
        contextualApi.getLcRequests({ status: s, page, limit: pagination.value.limit }),
        contextualApi.getLcStatusCounts(),
      ])
      if (version !== listVersion) return
      requests.value = data.requests
      pagination.value = data.pagination
      statusCounts.value = counts.counts
    } catch (error: any) {
      console.error('Failed to fetch LC requests:', error)
      if (error?.statusCode === 401 || error?.statusCode === 403) {
        throw error
      }
    } finally {
      if (version === listVersion) loading.value = false
    }
  }

  async function fetchLcStatusCounts() {
    try {
      const data = await api.getLcStatusCounts()
      statusCounts.value = data.counts
    } catch (error) {
      console.error('Failed to fetch LC status counts:', error)
    }
  }

  async function fetchLcRequestDetail(id: ExchangeRequestId) {
    loading.value = true
    try {
      const data = await api.getLcRequestDetail(id)
      currentRequest.value = data.request
      return data.request
    } catch (error) {
      console.error('Failed to fetch LC request detail:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function archiveRequest(id: ExchangeRequestId) {
    try {
      await api.archiveRequest(id)
      // Update local state
      const req = requests.value.find(r => r.id === id)
      if (req) req.status = 'archived'
      if (currentRequest.value?.id === id) currentRequest.value.status = 'archived'
    } catch (error) {
      console.error('Failed to archive request:', error)
      throw error
    }
  }

  async function resubmitRequest(id: ExchangeRequestId) {
    try {
      const result = await api.resubmitRequest(id)
      return result
    } catch (error) {
      console.error('Failed to resubmit request:', error)
      throw error
    }
  }

  async function confirmDeal(requestId: ExchangeRequestId, bidId: UUID) {
    try {
      await api.confirmDeal(requestId, bidId)
      if (currentRequest.value?.id === requestId) {
        await fetchLcRequestDetail(requestId)
      }
    } catch (error) {
      console.error('Failed to confirm deal:', error)
      throw error
    }
  }

  async function uploadKpToBid(requestId: ExchangeRequestId, bidId: UUID, file: File) {
    try {
      const result = await api.uploadKpToBid(requestId, bidId, file)
      if (currentRequest.value?.id === requestId) {
        await fetchLcRequestDetail(requestId)
      }
      return result
    } catch (error) {
      console.error('Failed to upload KP:', error)
      throw error
    }
  }

  async function duplicateRequest(id: ExchangeRequestId) {
    try {
      const result = await api.duplicateRequest(id)
      return result
    } catch (error) {
      console.error('Failed to duplicate request:', error)
      throw error
    }
  }

  async function respondToKp(bidId: UUID, action: 'accepted' | 'rejected', comment?: string | null) {
    try {
      const result = await api.respondToKp(bidId, { action, comment })
      if (currentRequest.value) {
        await fetchDealerRequestDetail(currentRequest.value.id)
      }
      return result
    } catch (error) {
      console.error('Failed to respond to KP:', error)
      throw error
    }
  }

  async function commentOnBid(requestId: ExchangeRequestId, bidId: UUID, comment: string) {
    try {
      const result = await api.commentOnBid(requestId, bidId, comment)
      // Add comment to local state
      if (currentRequest.value?.id === requestId) {
        const bid = currentRequest.value.bids.find(b => b.id === bidId)
        if (bid && bid.lc_comments) {
          bid.lc_comments.push(result.comment)
        }
      }
      return result
    } catch (error) {
      console.error('Failed to comment on bid:', error)
      throw error
    }
  }

  async function sendCounterOffer(bidId: UUID, price: number, comment?: string) {
    try {
      const result = await api.counterOffer(bidId, { price, comment })
      if (currentRequest.value) {
        await fetchLcRequestDetail(currentRequest.value.id)
      }
      return result
    } catch (error) {
      console.error('Failed to send counter offer:', error)
      throw error
    }
  }

  // ---- Dealer actions ----

  async function fetchDealerRequests(status?: ExchangeRequestStatus, page: number = 1, notificationCompanyId?: UUID) {
    const version = ++listVersion
    const contextualApi = createExchangeApi(config, () => notificationCompanyId)
    loading.value = true
    requests.value = []
    statusCounts.value = { open: 0, deal: 0, archived: 0 }
    try {
      const s = status || statusFilter.value
      const [data, counts] = await Promise.all([
        contextualApi.getDealerRequests({ status: s, page, limit: pagination.value.limit }),
        contextualApi.getDealerStatusCounts(),
      ])
      if (version !== listVersion) return
      requests.value = data.requests
      pagination.value = data.pagination
      statusCounts.value = counts.counts
    } catch (error: any) {
      console.error('Failed to fetch dealer requests:', error)
      if (error?.statusCode === 401 || error?.statusCode === 403) {
        throw error
      }
    } finally {
      if (version === listVersion) loading.value = false
    }
  }

  async function fetchDealerStatusCounts() {
    try {
      const data = await api.getDealerStatusCounts()
      statusCounts.value = data.counts
    } catch (error) {
      console.error('Failed to fetch dealer status counts:', error)
    }
  }

  async function fetchDealerRequestDetail(id: ExchangeRequestId) {
    loading.value = true
    try {
      const data = await api.getDealerRequestDetail(id)
      currentRequest.value = data.request
      return data.request
    } catch (error) {
      console.error('Failed to fetch dealer request detail:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function createBid(data: {
    request_id: ExchangeRequestId
    price: number
    quantity?: number
    comment?: string
    option_ids?: UUID[]
  }) {
    try {
      const result = await api.createBid(data)
      // Refresh request detail to see updated bids
      if (currentRequest.value?.id === data.request_id) {
        await fetchDealerRequestDetail(data.request_id)
      }
      return result
    } catch (error) {
      console.error('Failed to create bid:', error)
      throw error
    }
  }

  async function updateBid(bidId: UUID, data: {
    price?: number
    quantity?: number
    comment?: string
    option_ids?: UUID[]
  }) {
    try {
      const result = await api.updateBid(bidId, data)
      // Refresh request detail
      if (currentRequest.value) {
        await fetchDealerRequestDetail(currentRequest.value.id)
      }
      return result
    } catch (error) {
      console.error('Failed to update bid:', error)
      throw error
    }
  }

  async function uploadBidFile(bidId: UUID, file: File) {
    try {
      const result = await api.uploadBidFile(bidId, file)
      if (currentRequest.value) {
        await fetchDealerRequestDetail(currentRequest.value.id)
      }
      return result
    } catch (error) {
      console.error('Failed to upload bid file:', error)
      throw error
    }
  }

  // ---- Common ----

  function setStatusFilter(status: ExchangeRequestStatus) {
    statusFilter.value = status
  }

  function clearCurrentRequest() {
    currentRequest.value = null
  }

  function reset() {
    listVersion++
    requests.value = []
    currentRequest.value = null
    pagination.value = { page: 1, limit: 20, total: 0, pages: 0 }
  }

  return {
    requests,
    currentRequest,
    loading,
    statusFilter,
    pagination,
    statusCounts,
    // LC
    fetchLcRequests,
    fetchLcStatusCounts,
    fetchLcRequestDetail,
    archiveRequest,
    resubmitRequest,
    duplicateRequest,
    confirmDeal,
    uploadKpToBid,
    commentOnBid,
    sendCounterOffer,
    // Dealer
    fetchDealerRequests,
    fetchDealerStatusCounts,
    fetchDealerRequestDetail,
    createBid,
    updateBid,
    uploadBidFile,
    respondToKp,
    // Common
    setStatusFilter,
    clearCurrentRequest,
    reset,
  }
})
