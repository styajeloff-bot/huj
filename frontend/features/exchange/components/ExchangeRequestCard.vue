<template>
  <div
    @click="$emit('view')"
    class="group bg-white rounded-2xl border border-gray-200 hover:border-blue-300 hover:shadow-lg transition-all cursor-pointer overflow-hidden"
  >
    <div class="flex flex-col lg:flex-row">
      <!-- Image -->
      <div class="lg:w-56 h-40 lg:h-auto flex-shrink-0 bg-white border-b lg:border-b-0 lg:border-r border-gray-100 flex items-center justify-center p-3">
        <img
          v-if="firstImage"
          :src="firstImage"
          :alt="vehicleTitle"
          class="w-full h-full object-contain"
        />
        <div v-else class="text-gray-300">
          <svg class="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
      </div>

      <!-- Body -->
      <div class="flex-1 p-5 flex flex-col gap-3 min-w-0">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="text-base font-semibold text-gray-900 truncate group-hover:text-blue-600 transition-colors">
              <span class="text-gray-500 font-medium mr-1.5">№ {{ requestNumber }}</span>
              {{ vehicleTitle }}
            </h3>
            <p v-if="subtitle" class="text-sm text-gray-500 mt-0.5 truncate">{{ subtitle }}</p>
          </div>
          <div class="flex shrink-0 flex-col items-end gap-2">
            <span :class="statusBadgeClass">{{ statusLabel }}</span>
            <div
              v-if="selectedSupportPrograms.length"
              class="flex max-w-md flex-wrap justify-end gap-1.5"
            >
              <SupportBadge
                v-for="program in selectedSupportPrograms"
                :key="program.id"
                :program="program"
                shape="badge"
                tooltip-align="right"
              />
            </div>
          </div>
        </div>

        <!-- Meta tags -->
        <div class="flex flex-wrap items-center gap-1.5">
          <span class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-gray-100 text-gray-700">
            Кол-во: {{ request.quantity || 1 }}
          </span>
          <span v-if="optionsCount > 0" class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-blue-50 text-blue-700">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            Опции: {{ optionsCount }}
          </span>
          <span v-if="isLc && warehousesCount > 0" class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-emerald-50 text-emerald-700">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5"/></svg>
            Дилеров: {{ warehousesCount }}
          </span>
          <span v-if="request.expiration_at" class="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-amber-50 text-amber-700">
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            До {{ formatExchangeDeadline(request.expiration_at) }}
          </span>
        </div>

        <!-- Footer row -->
        <div class="flex flex-wrap items-end justify-between gap-3 pt-3 border-t border-gray-100 mt-auto">
          <div class="flex items-center gap-4 flex-wrap">
            <div>
              <div class="text-xs text-gray-500">Желаемая цена</div>
              <div class="text-base font-semibold" :class="hasDesiredDiscount ? 'text-blue-600' : 'text-gray-900'">
                {{ formatPrice(desiredUnitPrice) }}
              </div>
            </div>
            <div class="h-8 w-px bg-gray-200" />
            <div>
              <div class="text-xs text-gray-500">цена в каталоге</div>
              <div
                v-if="hasSupportPriceDiscount"
                class="text-xs text-gray-400 line-through"
              >
                {{ formatPrice(supportPriceBase) }}
              </div>
              <div class="text-base font-semibold text-gray-900">{{ formatPrice(actualUnitPrice) }}</div>
            </div>
            <div class="h-8 w-px bg-gray-200" />
            <div>
              <div class="text-xs text-gray-500">Лучшая ставка</div>
              <div class="text-base font-semibold" :class="bestBid ? 'text-emerald-600' : 'text-gray-400'">
                {{ bestBid ? formatPrice(bestBidTotalPrice) : '—' }}
              </div>
            </div>
            <div class="h-8 w-px bg-gray-200" />
            <div>
              <div class="text-xs text-gray-500">Соответствие опций</div>
              <div class="text-base font-semibold" :class="bestBidOptionMatchClass">
                {{ bestBidOptionMatchLabel }}
              </div>
            </div>
            <div class="h-8 w-px bg-gray-200" />
            <div>
              <div class="text-xs text-gray-500">Количество ставок</div>
              <div class="text-base font-semibold" :class="receivedBidCount > 0 ? 'text-blue-600' : 'text-gray-400'">
                {{ receivedBidCount }}/{{ possibleDealerCount }}
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-gray-400">{{ formattedCreated }}</span>
            <span class="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-gray-50 text-gray-500 group-hover:bg-blue-600 group-hover:text-white transition-colors">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatExchangeDeadline } from '../deadline'
import { computed } from 'vue'
import type { ExchangeRequest } from '../types'
import SupportBadge from '~/components/support/SupportBadge.vue'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

const props = defineProps<{
  request: ExchangeRequest
  isLc: boolean
}>()

defineEmits<{ view: [] }>()

const firstImage = computed(() => {
  const f = props.request.images?.[0]
  return f ? vehicleImageUrl(f) : null
})
const optionsCount = computed(() => props.request.options?.length || 0)
const warehousesCount = computed(() => props.request.warehouses?.length || 0)
const selectedSupportPrograms = computed(() => {
  const selectedIds = new Set(props.request.selected_support_ids)
  return props.request.support_program_details.filter(program => selectedIds.has(program.id))
})

const vehicleTitle = computed(() => {
  const parts = [props.request.mark_name, props.request.model_name].filter(Boolean)
  return parts.join(' ') || `Автомобиль #${props.request.vehicle_id}`
})

const requestNumber = computed(() => {
  const { batch_number, batch_index, id } = props.request
  if (batch_number && batch_index) return `${batch_number}-${batch_index}`
  return id
})
const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

const subtitle = computed(() => {
  const parts = [
    props.request.generation_name,
    props.request.group_name,
    props.request.color,
  ].filter(Boolean)
  return parts.join(' • ')
})

const formattedCreated = computed(() => {
  if (!props.request.created_at) return ''
  return formatSharedDate(props.request.created_at)
})

const quantity = computed(() => Number(props.request.quantity) || 1)
const supportPriceBase = computed(() => (
  Number(props.request.support_price_base ?? props.request.discount_price ?? props.request.base_price) || 0
))
const actualUnitPrice = computed(() => (
  Number(props.request.support_price_display ?? props.request.discount_price ?? props.request.base_price) || 0
))
const hasSupportPriceDiscount = computed(() => (
  Number(props.request.support_price_amount) > 0 && supportPriceBase.value > actualUnitPrice.value
))

const desiredUnitPrice = computed(() => {
  const base = actualUnitPrice.value
  const type = props.request.discount_type
  const value = Number(props.request.discount_value) || 0
  if (!base || !type || !value) return base
  if (type === 'rubles_off') return Math.max(base - value, 0)
  if (type === 'percent_off') return base * Math.max(1 - value / 100, 0)
  if (type === 'fixed_price') return value
  return base
})

const desiredTotalPrice = computed(() => desiredUnitPrice.value * quantity.value)

const hasDesiredDiscount = computed(() => {
  return !!props.request.discount_type
    && !!props.request.discount_value
    && desiredUnitPrice.value < actualUnitPrice.value
})

const possibleDealerCount = computed(() => {
  const dealerIds = new Set(
    (props.request.warehouses || [])
      .map((warehouse) => warehouse.dealer_id)
      .filter((dealerId) => dealerId != null)
  )
  return dealerIds.size
})

const receivedBidCount = computed(() => {
  const bidCount = Number(props.request.bid_count)
  if (Number.isFinite(bidCount) && bidCount >= 0) return bidCount
  return (props.request.bids || []).length
})

const bestBid = computed(() => {
  const bids = props.request.bids || []
  if (bids.length === 0) return null
  return bids.reduce((best, bid) => {
    return bidTotalPrice(bid) < bidTotalPrice(best) ? bid : best
  })
})

const bestBidTotalPrice = computed(() => {
  if (!bestBid.value) return null
  return bidTotalPrice(bestBid.value)
})

const bestBidOptionMatch = computed(() => {
  const requestOptionIds = new Set((props.request.options || []).map((option) => option.id))
  const bestBidOptionIds = new Set((bestBid.value?.options || []).map((option) => option.id))
  const matched = [...requestOptionIds].filter((optionId) => bestBidOptionIds.has(optionId)).length
  return {
    matched,
    total: requestOptionIds.size,
  }
})

const bestBidOptionMatchLabel = computed(() => {
  if (!bestBid.value) return '—'
  if (bestBidOptionMatch.value.total === 0) return 'Без опций'
  return `${bestBidOptionMatch.value.matched}/${bestBidOptionMatch.value.total}`
})

const bestBidOptionMatchClass = computed(() => {
  if (!bestBid.value) return 'text-gray-400'
  const { matched, total } = bestBidOptionMatch.value
  if (total === 0 || matched === total) return 'text-emerald-600'
  if (matched > 0) return 'text-amber-600'
  return 'text-red-600'
})

const statusLabel = computed(() => {
  const map: Record<string, string> = { open: 'Открыта', deal: 'Сделка', archived: 'Архив' }
  return map[props.request.status] || props.request.status
})

const statusBadgeClass = computed(() => {
  const base = 'inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap'
  const map: Record<string, string> = {
    open: `${base} bg-emerald-100 text-emerald-700`,
    deal: `${base} bg-blue-100 text-blue-700`,
    archived: `${base} bg-gray-100 text-gray-600`,
  }
  return map[props.request.status] || `${base} bg-gray-100 text-gray-600`
})

function formatPrice(price: number | null | undefined) {
  if (!price) return '—'
  return formatSharedPrice(price)
}

function bidTotalPrice(bid: ExchangeRequest['bids'][number]) {
  const bidQuantity = Math.max(1, Number(bid.quantity) || quantity.value)
  return (Number(bid.price) || 0) * bidQuantity
}

function formatDate(date: string) {
  return formatSharedDate(date)
}
</script>
