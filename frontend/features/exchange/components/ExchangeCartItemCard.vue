<template>
  <article class="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden">
    <div class="p-5 sm:p-6">
      <!-- Header -->
      <div class="flex items-start gap-4">

        <NuxtLink
          to="/special-equipment"
          class="w-28 h-20 sm:w-32 sm:h-24 rounded-xl overflow-hidden bg-white border border-gray-200 flex items-center justify-center shrink-0 hover:border-blue-400 hover:shadow-sm transition-all"
        >
          <img v-if="imageSrc" :src="imageSrc" :alt="vehicleTitle" class="w-full h-full object-contain">
          <svg v-else class="w-8 h-8 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </NuxtLink>

        <div class="flex-1 min-w-0">
          <h3 class="text-xl sm:text-2xl font-semibold text-gray-900 leading-tight">{{ vehicleTitle }}</h3>
          <p v-if="item.group_name" class="mt-1 text-gray-600">
            <span class="font-medium">Комплектация:</span> {{ item.group_name }}
          </p>
          <p v-if="item.color" class="text-gray-600">{{ item.color }}</p>
          <RotatingSupportBadge
            v-if="selectedSupportPrograms.length"
            class="mt-2"
            :programs="selectedSupportPrograms"
          />
        </div>

        <div class="shrink-0 text-right">
          <div  class="mt-1 text-lg text-gray-900" >Общая стоимость</div>
          <div
            v-if="hasSupportPriceDiscount"
            class="text-xs text-gray-400 line-through"
          >
            {{ formatPrice(supportPriceBase * quantity) }}
          </div>
          <div v-for="label in totalPriceLabel" class="text-sm font-semibold text-gray-700">{{ label }}</div>
          <div v-if="discountSummary" class="mt-2 space-y-0.5 text-xs text-blue-700">
            <div>Желаемая выгода <br>{{ formatPrice(discountSummary.rubles) }}, {{ formatPercent(discountSummary.percent) }}</div>
            <div>Желаемая цена <br> {{ formatPrice(discountSummary.fixed) }}</div>
          </div>
        </div>


        <button
          type="button"
          @click="$emit('remove', item.id)"
          class="shrink-0 text-gray-400 hover:text-red-500 transition-colors"
          aria-label="Удалить"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Row: quantity + catalog price -->
      <div class="mt-5 flex flex-wrap items-end gap-6">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">Количество</label>
          <input
            :value="item.quantity"
            type="number"
            min="1"
            class="w-28 rounded-xl border border-gray-300 px-4 py-2.5 text-lg text-center text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            @change="handleQuantityChange"
          >
        </div>
        <div>
          <div class="ml-2 text-lg text-gray-900" >Цена в каталоге</div>
          <div
            v-if="hasSupportPriceDiscount"
            class="ml-2 text-xs text-gray-400 line-through"
          >
            {{ formatPrice(supportPriceBase) }}
          </div>
          <div v-for="label in unitPriceLabel" class="text-sm font-medium text-gray-700 ml-2" >{{ label }}</div>
        </div>
      </div>

      <SupportProgramSelector
        v-if="item.eligible_support_programs.length"
        class="mt-5"
        :programs="item.eligible_support_programs"
        :selected-ids="item.selected_support_ids"
        :show-bulletins="true"
        :error-message="supportUpdateError"
        :api-base="String(config.public.apiBase || '')"
        @change="applySupportSelection"
      />

      <!-- Panels -->
      <div v-if="openPanel === 'file'" class="mt-4 rounded-2xl border border-gray-200 p-4">
        <label class="block text-sm font-medium text-gray-700 mb-2">Файл с деталями для дилера</label>
        <div v-if="item.file_name" class="mb-2 text-sm">
          <a v-if="item.file_url" :href="item.file_url" target="_blank" class="text-blue-600 hover:text-blue-800">{{ item.file_name }}</a>
          <span v-else class="text-gray-600">{{ item.file_name }}</span>
        </div>
        <input type="file" class="block w-full text-sm text-gray-600 file:mr-4 file:rounded-lg file:border-0 file:bg-gray-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-gray-200" @change="handleFileUpload">
      </div>

      <div v-if="openPanel === 'expiration'" class="mt-4 rounded-2xl border border-gray-200 p-4">
        <label class="block text-sm font-medium text-gray-700 mb-2">Срок заявки ({{ localTimeZone }})</label>
        <input :value="toDeadlineInput(item.expiration_at)" :min="minimumDeadline" type="datetime-local" aria-label="Дата и время окончания заявки" class="w-full sm:w-64 rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100" @change="handleExpirationChange">
      </div>

      <div v-if="openPanel === 'discount'" class="mt-4 rounded-2xl border border-gray-200 p-4">
        <label class="block text-sm font-medium text-gray-700 mb-2">Запрашиваемая выгода</label>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <input type="number" min="0" step="0.01" placeholder="Выгода в рублях"
            :value="rublesInput"
            class="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            @input="onDiscountInput('rubles_off', $event)"
            @change="persistDiscount">
          <input type="number" min="0" max="100" step="0.01" placeholder="Выгода в процентах"
            :value="percentInput"
            class="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            @input="onDiscountInput('percent_off', $event)"
            @change="persistDiscount">
          <input type="number" min="0" step="0.01" placeholder="Фиксированная цена"
            :value="fixedInput"
            class="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            @input="onDiscountInput('fixed_price', $event)"
            @change="persistDiscount">
        </div>
      </div>

      <div v-if="openPanel === 'options'" class="mt-4 rounded-2xl border border-gray-200 p-4">
        <div class="text-sm font-semibold text-gray-900 mb-3">Дилерские опции</div>
        <div v-if="dealerOptionsStore.options.length === 0" class="text-sm text-gray-400">Список опций пока пуст</div>
        <div v-else class="flex flex-wrap gap-2">
          <label v-for="option in dealerOptionsStore.options" :key="option.id"
            class="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm cursor-pointer transition-colors"
            :class="item.selected_option_ids.includes(option.id) ? 'border-blue-300 bg-blue-50 text-blue-900' : 'border-gray-200 text-gray-700 hover:bg-gray-50'">
            <input type="checkbox" :checked="item.selected_option_ids.includes(option.id)" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" @change="toggleOption(option.id)">
            <span>{{ option.name }}</span>
          </label>
        </div>
      </div>

      <div v-if="openPanel === 'comments'" class="mt-4 rounded-2xl border border-gray-200 p-4">
        <div class="text-sm font-semibold text-gray-900 mb-3">Комментарии дилерам</div>
        <div v-if="selectedDealers.length === 0" class="text-sm text-gray-400">Выберите склад, чтобы оставить комментарий дилеру</div>
        <div v-else class="space-y-3">
          <div v-for="dealer in selectedDealers" :key="dealer.dealer_id">
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ dealer.dealer_name || `Дилер #${dealer.dealer_id}` }}</label>
            <textarea :value="getDealerComment(dealer.dealer_id)" rows="2" class="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100" placeholder="Комментарий для дилера" @change="handleDealerCommentChange(dealer.dealer_id, $event)" />
          </div>
        </div>
      </div>

      <!-- Action chips + warehouses toggle -->
      <div class="mt-5 flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap gap-2">
          <button type="button" title="Вложения" aria-label="Вложения" @click="togglePanel('file')" :class="iconChipClass('file', !!item.file_name)">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.414a4 4 0 10-5.656-5.656l-6.415 6.414a6 6 0 108.486 8.486L20.5 13"/></svg>
            <span v-if="item.file_name" class="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-blue-600 text-white text-[10px] leading-[18px] text-center">1</span>
          </button>
          <button type="button" title="Срок заявки" aria-label="Срок заявки" @click="togglePanel('expiration')" :class="iconChipClass('expiration', !!item.expiration_at)">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
          </button>
          <button type="button" title="Запросить выгоду" aria-label="Запросить выгоду" @click="togglePanel('discount')" :class="iconChipClass('discount', !!item.discount_type)">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5a1.99 1.99 0 011.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.99 1.99 0 013 12V7a4 4 0 014-4z"/></svg>
            <span v-if="discountSummary" class="absolute -top-1 -right-1 min-w-[22px] h-[18px] px-1.5 rounded-full bg-blue-600 text-white text-[10px] leading-[18px] text-center">{{ formatPercent(discountSummary.percent) }}</span>
          </button>
          <button type="button" title="Выбрать опции" aria-label="Выбрать опции" @click="togglePanel('options')" :class="iconChipClass('options', item.selected_option_ids.length > 0)">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            <span v-if="item.selected_option_ids.length" class="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-blue-600 text-white text-[10px] leading-[18px] text-center">{{ item.selected_option_ids.length }}</span>
          </button>
          <button type="button" title="Комментарии" aria-label="Комментарии" @click="togglePanel('comments')" :class="iconChipClass('comments', dealerCommentsCount > 0)">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.3-3.8A7.96 7.96 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
            <span v-if="dealerCommentsCount" class="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-blue-600 text-white text-[10px] leading-[18px] text-center">{{ dealerCommentsCount }}</span>
          </button>
        </div>

        <button type="button" @click="warehousesOpen = !warehousesOpen"
          class="inline-flex items-center gap-2 rounded-2xl bg-blue-600 text-white px-5 py-3 font-semibold shadow-sm hover:bg-blue-700 transition-colors">
          Выбранные дилеры
          <span v-if="item.selected_warehouse_ids.length" class="inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5 rounded-full bg-white/20 text-xs">{{ item.selected_warehouse_ids.length }}</span>
          <svg class="w-4 h-4 transition-transform" :class="warehousesOpen ? 'rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
        </button>
      </div>

      <div v-if="warehousesOpen" class="mt-4">
        <div v-if="warehousesLoading" class="text-sm text-gray-400">Загрузка складов...</div>
        <div v-else-if="availableWarehouses.length === 0" class="rounded-xl border border-dashed border-gray-200 px-3 py-4 text-sm text-gray-400">
          Нет доступных складов для этого автомобиля
        </div>
        <div v-else class="space-y-3">
          <div v-for="warehouse in availableWarehouses" :key="warehouse.id"
            class="rounded-2xl border p-4 transition-colors"
            :class="isWarehouseSelected(warehouse.id) ? 'border-green-300 bg-green-50' : 'border-gray-200 bg-white'">
            <div class="flex items-start gap-4">
              <div class="flex flex-col items-center gap-2 shrink-0">
                <button type="button" @click="toggleWarehouse(warehouse.id)"
                  class="w-6 h-6 rounded-md border-2 flex items-center justify-center transition-colors"
                  :class="isWarehouseSelected(warehouse.id) ? 'bg-blue-600 border-blue-600 text-white' : 'border-gray-300 bg-white hover:border-blue-400'"
                  :aria-label="isWarehouseSelected(warehouse.id) ? 'Снять выбор' : 'Выбрать склад'">
                  <svg v-if="isWarehouseSelected(warehouse.id)" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                </button>
                <button v-if="isWarehouseSelected(warehouse.id)" type="button" @click="toggleWarehouse(warehouse.id)"
                  class="text-gray-400 hover:text-red-500 transition-colors" aria-label="Убрать склад">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3"/></svg>
                </button>
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-start gap-2 text-gray-800 font-medium">
                  <svg class="w-5 h-5 shrink-0 text-gray-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                  <span>Автомобиль на складе</span>
                </div>
                <div v-if="warehouse.city_name && warehouse.address" class="mt-1 text-sm text-gray-600 ml-7">{{ warehouse.city_name }}, {{ warehouse.address }}</div>
                <div v-if="warehouse.company_name" class="text-sm text-green-700 ml-7">{{ warehouse.company_name }}</div>
              </div>

              <div class="shrink-0 text-sm space-y-1 min-w-[180px]">
                <div class="flex justify-between gap-4"><span class="text-gray-600">Количество</span><span class="font-semibold text-gray-900">{{ warehouse.vehicle_count ?? 0 }} шт.</span></div>
                <div class="flex justify-between gap-4"><span class="text-gray-600">Цена</span><span class="font-semibold text-gray-900">{{ warehousePriceLabel(warehouse) }}</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { toDeadlineInput, fromDeadlineInput } from '../deadline'
import { useDealerOptionsStore } from '../store/dealerOptions'
import { useExchangeCartStore } from '../store/exchangeCart'
import type { EntityId, ExchangeCartItem, WarehouseInfo } from '../types'
import type { UUID } from '~/types/ids'
import RotatingSupportBadge from '~/components/support/RotatingSupportBadge.vue'
import SupportProgramSelector from '~/components/support/SupportProgramSelector.vue'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

const props = defineProps<{
  item: ExchangeCartItem
  isSelected?: boolean
}>()

defineEmits<{
  remove: [itemId: UUID]
  'toggle-select': [itemId: UUID]
}>()

const cartStore = useExchangeCartStore()
const dealerOptionsStore = useDealerOptionsStore()
const config = useRuntimeConfig()
const availableWarehouses = ref<WarehouseInfo[]>([])
const warehousesLoading = ref(false)
const warehousesOpen = ref(true)
const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
const minimumDeadline = toDeadlineInput(new Date().toISOString())
const openPanel = ref<'file' | 'expiration' | 'discount' | 'options' | 'comments' | null>(null)
const supportUpdateError = ref('')

const selectedSupportPrograms = computed(() => {
  const selectedIds = new Set(props.item.selected_support_ids)
  return props.item.eligible_support_programs.filter(program => selectedIds.has(program.id))
})

const applySupportSelection = async (selectedIds: UUID[]) => {
  supportUpdateError.value = ''
  try {
    await cartStore.setSupportPrograms(props.item.id, selectedIds)
  } catch {
    supportUpdateError.value = 'Не удалось сохранить выбранные программы'
  }
}

function togglePanel(name: typeof openPanel.value) {
  openPanel.value = openPanel.value === name ? null : name
}

function iconChipClass(name: string, active: boolean) {
  const base = 'relative inline-flex h-12 w-12 items-center justify-center rounded-xl border transition-colors'
  const open = openPanel.value === name
  if (open) return `${base} border-blue-500 bg-blue-50 text-blue-700`
  if (active) return `${base} border-blue-200 text-blue-700 hover:bg-blue-50`
  return `${base} border-gray-200 text-gray-600 hover:bg-gray-50`
}

const imageSrc = computed(() => {
  const filename = props.item.images?.[0]
  return filename ? vehicleImageUrl(filename) : ''
})

const vehicleTitle = computed(() => {
  const parts = [
    props.item.mark_name,
    props.item.model_name,
    props.item.generation_name,
  ].filter(Boolean)
  return parts.join(' ') || `Vehicle #${props.item.vehicle_id}`
})

const selectedDealers = computed<Array<{ dealer_id: UUID; dealer_name: string }>>(() => {
  const seen = new Set<UUID>()
  return availableWarehouses.value
    .filter((warehouse): warehouse is WarehouseInfo & { dealer_id: UUID } => (
      warehouse.dealer_id != null && isWarehouseSelected(warehouse.id)
    ))
    .filter((warehouse) => {
      if (seen.has(warehouse.dealer_id)) return false
      seen.add(warehouse.dealer_id)
      return true
    })
    .map((warehouse) => ({
      dealer_id: warehouse.dealer_id,
      dealer_name: warehouse.dealer_name || warehouse.city_name || '',
    }))
})

const dealerCommentsCount = computed(() => props.item.dealer_comments.filter(c => c.comment?.trim()).length)

const supportPriceBase = computed(() => (
  Number(props.item.support_price_base ?? props.item.discount_price ?? props.item.base_price) || 0
))
const unitPrice = computed(() => (
  Number(props.item.support_price_display ?? props.item.discount_price ?? props.item.base_price) || 0
))
const supportPriceAmount = computed(() => Math.max(Number(props.item.support_price_amount) || 0, 0))
const hasSupportPriceDiscount = computed(() => (
  supportPriceAmount.value > 0 && supportPriceBase.value > unitPrice.value
))
const quantity = computed(() => Number(props.item.quantity) || 1)

const priceRange = computed(() => {
  const prices: number[] = []
  for (const w of availableWarehouses.value) {
    if (w.min_price != null) prices.push(Math.max(Number(w.min_price) - supportPriceAmount.value, 0))
    if (w.max_price != null) prices.push(Math.max(Number(w.max_price) - supportPriceAmount.value, 0))
  }
  if (prices.length === 0) {
    return { min: unitPrice.value, max: unitPrice.value }
  }
  return { min: Math.min(...prices), max: Math.max(...prices) }
})

const unitPriceLabel = computed(() => {
  const { min, max } = priceRange.value
  return min === max ? [formatPrice(min)] : [`От ${formatPrice(min)}`, `До ${formatPrice(max)}`]
})

const totalPriceLabel = computed(() => {
  const { min, max } = priceRange.value
  return min === max
    ? [formatPrice(min * quantity.value)]
    : [`От ${formatPrice(min * quantity.value)}`, `До ${formatPrice(max * quantity.value)}`]
})

type DiscountType = NonNullable<ExchangeCartItem['discount_type']>

const rublesInput = ref('')
const percentInput = ref('')
const fixedInput = ref('')
const discountTypeLocal = ref<ExchangeCartItem['discount_type']>(null)

const discountSummary = computed(() => {
  if (!discountTypeLocal.value) return null
  return {
    rubles: Number(rublesInput.value) || 0,
    percent: Number(percentInput.value) || 0,
    fixed: Number(fixedInput.value) || 0,
  }
})

function round2(n: number) {
  return Math.round(n * 100) / 100
}

function recomputeFrom(type: DiscountType, raw: string) {
  const p = unitPrice.value
  const v = Number(raw) || 0
  if (type === 'rubles_off') {
    rublesInput.value = raw
    percentInput.value = p > 0 ? String(round2((v / p) * 100)) : ''
    fixedInput.value = String(round2(Math.max(p - v, 0)))
  } else if (type === 'percent_off') {
    percentInput.value = raw
    rublesInput.value = String(round2((p * v) / 100))
    fixedInput.value = String(round2(p * Math.max(1 - v / 100, 0)))
  } else if (type === 'fixed_price') {
    fixedInput.value = raw
    rublesInput.value = String(round2(Math.max(p - v, 0)))
    percentInput.value = p > 0 ? String(round2(((p - v) / p) * 100)) : ''
  }
  discountTypeLocal.value = type
}

function clearDiscount() {
  rublesInput.value = ''
  percentInput.value = ''
  fixedInput.value = ''
  discountTypeLocal.value = null
}

function syncFromItem() {
  const type = props.item.discount_type
  const val = props.item.discount_value
  if (!type || val == null) { clearDiscount(); return }
  recomputeFrom(type, String(val))
}

watch(
  () => [props.item.id, props.item.discount_type, props.item.discount_value, unitPrice.value] as const,
  () => syncFromItem(),
  { immediate: true }
)

const { formatPrice: formatSharedPrice } = useFormatPrice()

function formatPrice(price: number | string) {
  return formatSharedPrice(price)
}

function formatPercent(percent: number) {
  const rounded = round2(percent)
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(2).replace(/\.?0+$/, '')}%`
}

function warehousePriceLabel(warehouse: WarehouseInfo) {
  const min = warehouse.min_price != null
    ? Math.max(Number(warehouse.min_price) - supportPriceAmount.value, 0)
    : null
  const max = warehouse.max_price != null
    ? Math.max(Number(warehouse.max_price) - supportPriceAmount.value, 0)
    : null
  if (min == null && max == null) return formatPrice(unitPrice.value)
  const lo = min ?? max!
  const hi = max ?? min!
  return lo === hi ? formatPrice(lo) : `От ${formatPrice(lo)} до ${formatPrice(hi)}`
}

function updateField(field: 'quantity' | 'expiration_at' | 'discount_type' | 'discount_value', value: number | string | null) {
  cartStore.updateItem(props.item.id, { [field]: value })
}

function handleQuantityChange(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  updateField('quantity', Math.max(1, value || 1))
}
function handleExpirationChange(event: Event) {
  const input = event.target as HTMLInputElement
  input.setCustomValidity('')
  try {
    const value = fromDeadlineInput(input.value)
    if (value && new Date(value).getTime() <= Date.now()) throw new Error('Срок должен быть в будущем')
    updateField('expiration_at', value)
  } catch (error) {
    input.setCustomValidity(error instanceof Error ? error.message : 'Проверьте срок заявки')
    input.reportValidity()
  }
}
function onDiscountInput(type: DiscountType, event: Event) {
  const input = event.target as HTMLInputElement
  const raw = input.value
  if (!raw) { clearDiscount(); return }
  const n = Number(raw)
  if (Number.isNaN(n)) return
  const clamped = type === 'percent_off'
    ? Math.min(100, Math.max(0, n))
    : Math.max(0, n)
  const display = clamped === n ? raw : String(clamped)
  if (display !== raw) input.value = display
  recomputeFrom(type, display)
}
function persistDiscount() {
  if (!discountTypeLocal.value) {
    cartStore.updateItem(props.item.id, { discount_type: null, discount_value: null })
    return
  }
  const raw = discountTypeLocal.value === 'rubles_off' ? rublesInput.value
    : discountTypeLocal.value === 'percent_off' ? percentInput.value
    : fixedInput.value
  cartStore.updateItem(props.item.id, {
    discount_type: discountTypeLocal.value,
    discount_value: raw ? Number(raw) : null,
  })
}
function isWarehouseSelected(warehouseId: EntityId) {
  return props.item.selected_warehouse_ids.includes(warehouseId)
}

function toggleWarehouse(warehouseId: EntityId) {
  const next = [...props.item.selected_warehouse_ids]
  const index = next.indexOf(warehouseId)
  if (index >= 0) next.splice(index, 1); else next.push(warehouseId)
  cartStore.setWarehouses(props.item.id, next)
}
function toggleOption(optionId: UUID) {
  const next = [...props.item.selected_option_ids]
  const index = next.indexOf(optionId)
  if (index >= 0) next.splice(index, 1); else next.push(optionId)
  cartStore.setOptions(props.item.id, next)
}
function getDealerComment(dealerId: UUID) {
  return props.item.dealer_comments.find(c => c.dealer_id === dealerId)?.comment || ''
}
function handleDealerCommentChange(dealerId: UUID, event: Event) {
  const comment = (event.target as HTMLTextAreaElement).value
  cartStore.setDealerComment(props.item.id, dealerId, comment)
}
function handleFileUpload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) cartStore.uploadFile(props.item.id, file)
}

async function loadWarehouses() {
  warehousesLoading.value = true
  try {
    availableWarehouses.value = await cartStore.getAvailableWarehouses(props.item.vehicle_id)
  } finally {
    warehousesLoading.value = false
  }
}

onMounted(() => {
  loadWarehouses()
  dealerOptionsStore.fetchOptions()
})
</script>
