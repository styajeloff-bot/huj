<template>
  <div class="bg-blue-50 rounded-lg p-4 border border-blue-200">
    <h4 class="text-sm font-semibold text-blue-900 mb-3">
      {{ existingBid ? 'Обновить ставку' : 'Сделать ставку' }}
    </h4>
    <form @submit.prevent="handleSubmit">
      <fieldset :disabled="!canWrite || submitting" class="space-y-3">
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">Цена за единицу, ₽ *</label>
          <input
            :value="priceDisplay"
            @input="onPriceInput"
            type="text"
            inputmode="numeric"
            required
            class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
            placeholder="Введите цену"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">
            Количество, шт.<span v-if="maxQuantity > 1" class="text-gray-400"> (до {{ maxQuantity }})</span>
          </label>
          <input
            v-model.number="form.quantity"
            type="number"
            min="1"
            :max="maxQuantity"
            class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">Общая сумма</label>
          <div class="w-full px-3 py-2 border border-gray-200 bg-gray-50 rounded-md text-sm font-semibold text-gray-900">
            {{ formatPrice(totalPrice) }}
          </div>
        </div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">Комментарий</label>
        <textarea
          v-model="form.comment"
          rows="2"
          class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
          placeholder="Дополнительная информация..."
        />
      </div>

      <!-- Dealer options -->
      <div v-if="dealerOptions.length > 0">
        <label class="block text-xs font-medium text-gray-700 mb-1">Включенные опции</label>
        <div class="flex flex-wrap gap-2">
          <label
            v-for="opt in dealerOptions"
            :key="opt.id"
            class="flex items-center gap-1.5 text-xs bg-white px-2.5 py-1.5 rounded border cursor-pointer hover:bg-gray-50"
            :class="form.option_ids.includes(opt.id) ? 'border-blue-400 bg-blue-50' : 'border-gray-200'"
          >
            <input
              type="checkbox"
              :value="opt.id"
              v-model="form.option_ids"
              class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            {{ opt.name }}
          </label>
        </div>
      </div>

      <!-- File attachment -->
      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">Файл к ставке</label>
        <div class="flex items-center gap-3">
          <label class="inline-flex items-center gap-2 px-3 py-2 text-xs font-medium rounded border border-gray-300 bg-white text-gray-700 cursor-pointer hover:bg-gray-50">
            <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.414a4 4 0 10-5.656-5.656l-6.415 6.414a6 6 0 108.486 8.486L20.5 13"/>
            </svg>
            Выбрать файл
            <input type="file" class="hidden" @change="onFileChange" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png" />
          </label>
          <span v-if="pendingFile" class="text-xs text-gray-700 truncate">
            {{ pendingFile.name }}
            <button type="button" class="ml-1 text-gray-400 hover:text-red-500" @click="pendingFile = null">×</button>
          </span>
          <a
            v-else-if="existingBid?.bid_file_url"
            :href="api.downloadUrl(existingBid.bid_file_url)"
            target="_blank"
            class="text-xs text-blue-600 hover:underline truncate"
          >{{ existingBid.bid_file_name || 'Текущий файл' }}</a>
          <span v-else class="text-xs text-gray-400">Файл не прикреплён</span>
        </div>
      </div>

      <div v-if="error" class="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-2">{{ error }}</div>

      <div class="flex justify-end">
        <button
          type="submit"
          :disabled="!canWrite || submitting || !form.price"
          class="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ submitting ? 'Отправка...' : existingBid ? 'Обновить ставку' : 'Отправить ставку' }}
        </button>
      </div>
      </fieldset>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { createExchangeApi } from '../api/exchangeApi'
import { useNotificationCompanyContext } from '~/features/notifications'
import type { DealerOption, ExchangeBid, ExchangeRequestId } from '../types'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  canWrite: boolean
  requestId: ExchangeRequestId
  existingBid: ExchangeBid | null
  requestQuantity?: number
}>()

const emit = defineEmits<{ submitted: []; failed: [] }>()

const companyContext = useNotificationCompanyContext()
const api = createExchangeApi(useRuntimeConfig(), companyContext)
const dealerOptions = ref<DealerOption[]>([])
const submitting = ref(false)
const error = ref<string | null>(null)
const pendingFile = ref<File | null>(null)
let formVersion = 0
let disposed = false
onBeforeUnmount(() => { disposed = true; formVersion++ })
watch(() => [props.requestId, companyContext(), props.canWrite] as const, () => {
  formVersion++
  pendingFile.value = null
}, { flush: 'sync' })

const maxQuantity = computed(() => Math.max(1, Number(props.requestQuantity) || 1))

const form = reactive({
  price: props.existingBid?.price || null as number | null,
  quantity: props.existingBid?.quantity || maxQuantity.value,
  comment: props.existingBid?.comment || '',
  option_ids: (props.existingBid?.options || []).map(o => o.id),
})

function formatThousands(n: number | null): string {
  if (n == null || Number.isNaN(n)) return ''
  return n.toLocaleString('ru-RU')
}

const { formatPrice: formatSharedPrice } = useFormatPrice()

function formatPrice(n: number) {
  return formatSharedPrice(n || 0)
}

const priceDisplay = ref(formatThousands(form.price))

const totalPrice = computed(() => {
  const p = Number(form.price) || 0
  const q = Math.max(1, Math.min(maxQuantity.value, Number(form.quantity) || 1))
  return p * q
})

function onPriceInput(event: Event) {
  const input = event.target as HTMLInputElement
  const digits = input.value.replace(/\D/g, '')
  if (!digits) {
    form.price = null
    priceDisplay.value = ''
    input.value = ''
    return
  }
  const n = Number(digits)
  form.price = n
  const formatted = formatThousands(n)
  priceDisplay.value = formatted
  input.value = formatted
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const f = input.files?.[0] || null
  pendingFile.value = f
  input.value = ''
}

async function handleSubmit() {
  if (disposed || !props.canWrite || submitting.value || !form.price) return
  const version = formVersion
  const existingBidId = props.existingBid?.id
  submitting.value = true
  error.value = null
  try {
    const clampedQty = Math.max(1, Math.min(maxQuantity.value, Number(form.quantity) || 1))
    let bidId: UUID | undefined
    if (existingBidId) {
      await api.updateBid(existingBidId, {
        price: form.price,
        quantity: clampedQty,
        comment: form.comment || undefined,
        option_ids: form.option_ids,
      })
      bidId = existingBidId
    } else {
      const result = await api.createBid({
        request_id: props.requestId,
        price: form.price,
        quantity: clampedQty,
        comment: form.comment || undefined,
        option_ids: form.option_ids,
      })
      bidId = result.bid.id
    }
    if (version !== formVersion || !props.canWrite) return
    if (pendingFile.value && bidId) {
      await api.uploadBidFile(bidId, pendingFile.value)
      if (version !== formVersion || !props.canWrite) return
      pendingFile.value = null
    }
    emit('submitted')
  } catch (e: unknown) {
    if (version !== formVersion) return
    const err = e as { data?: { message?: string }; message?: string }
    error.value = err?.data?.message || err?.message || 'Ошибка отправки'
    emit('failed')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try { dealerOptions.value = (await api.getDealerOptions()).options }
  catch { error.value = 'Не удалось загрузить дополнительные опции дилера' }
})
</script>
