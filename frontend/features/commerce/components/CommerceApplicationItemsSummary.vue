<template>
  <section data-storefront-block="client.order" v-if="items.length" class="mb-6 rounded-xl border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4" aria-labelledby="application-items-title">
    <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h2 id="application-items-title" class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">Техника в заявке</h2>
        <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">{{ positionCount }} {{ itemWord(positionCount) }} · {{ unitCount }} {{ unitWord(unitCount) }}</p>
      </div>
      <div v-if="total !== null && total !== undefined" class="relative flex items-center gap-1">
        <p class="text-base font-bold tabular-nums text-[color:var(--storefront-text,#030712)]">{{ formatCommerceMoney(total) }}</p>
        <div v-if="hasPriceAdjustments" class="group relative">
          <button type="button" class="storefront-action-ghost relative z-20 grid h-6 w-6 place-items-center rounded-full text-[color:var(--storefront-primary-foreground,#2563eb)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]" aria-label="Как рассчитана общая сумма" aria-describedby="application-total-price-tooltip">
            <InformationCircleIcon class="h-5 w-5" aria-hidden="true" />
          </button>
          <div data-storefront-block="shared.tooltip" id="application-total-price-tooltip" role="tooltip" class="pointer-events-none absolute right-0 top-full z-30 mt-1 hidden w-72 rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,3_7_18)/var(--tw-bg-opacity,1))] px-3 py-2 text-xs font-normal leading-relaxed text-[color:var(--storefront-text,#ffffff)] shadow-lg group-hover:block group-focus-within:block">
            В итоговой сумме учтены выгоды и надбавки по позициям заявки.
          </div>
        </div>
      </div>
    </div>
    <ul v-if="liveItems.length" class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="item in liveItems" :key="`${item.type}:${item.id}`" class="relative flex gap-3 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-3">
        <NuxtLink v-if="safeDetailUrl(item.detail_url)" :to="safeDetailUrl(item.detail_url) ?? '/'" class="absolute inset-0 z-10 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]" :aria-label="`Открыть ${item.title}`" />
        <div class="grid h-14 w-16 shrink-0 place-items-center overflow-hidden rounded-md bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]">
          <img v-if="safeProxyUrl(item.image_url)" :src="safeProxyUrl(item.image_url) ?? undefined" :alt="item.title" class="h-full w-full object-contain" width="128" height="112">
          <PhotoIcon v-else class="h-6 w-6 text-[color:var(--storefront-icon,#d1d5db)]" aria-hidden="true" />
        </div>
        <div class="min-w-0">
          <p class="line-clamp-2 text-sm font-semibold leading-snug text-[color:var(--storefront-text,#030712)]">{{ item.title }}</p>
          <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            {{ item.type === 'vehicle' ? 'Автомобиль' : `Спецтехника · ${specialEquipmentApplicationItemRoleLabel(item.item_role)}` }} · {{ item.quantity }} шт.
          </p>
          <CommerceApplicationItemComment :comment="item.comment" />
          <dl v-if="showPurposeRegions && hasItemPurposeOrRegions(item)" class="relative z-20 mt-2 space-y-1 text-xs text-[color:var(--storefront-text-muted,#4b5563)]">
            <div v-if="itemPurposeLabel(item)">
              <dt class="inline font-medium">Цель приобретения:</dt>
              <dd class="inline"> {{ itemPurposeLabel(item) }}</dd>
            </div>
            <div v-if="itemRegionLabels(item).length">
              <dt class="inline font-medium">Регион:</dt>
              <dd class="inline"> <VehicleRegionsDisplay :vehicle="item" empty-label="" /></dd>
            </div>
          </dl>
          <RotatingSupportBadge
            v-if="item.type === 'vehicle' && supportProgramsForItem(item).length"
            class="relative z-20 mt-2"
            :programs="supportProgramsForItem(item)"
          />
          <span v-if="item.status" class="mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium" :class="itemStatusPresentation(item).badgeClass">{{ itemStatusLabel(item) }}</span>
          <div v-if="item.type === 'vehicle' && hasItemAdjustment(item) && itemShowsCatalogPrice(item)" class="relative z-auto mt-2">
            <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Цена по каталогу</p>
            <p class="text-sm font-medium tabular-nums text-[color:var(--storefront-text,#374151)]">{{ formatCommerceMoney(itemCatalogPrice(item), item.currency_code) }}</p>
            <div class="mt-1 flex items-center gap-1">
              <div>
                <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Итоговая цена</p>
                <p class="text-sm font-semibold tabular-nums text-[color:var(--storefront-text,#030712)]">{{ formatCommerceMoney(itemFinalPrice(item), item.currency_code) }}</p>
              </div>
              <div class="group">
                <button type="button" class="storefront-action-ghost relative z-auto grid h-6 w-6 place-items-center rounded-full text-[color:var(--storefront-primary-foreground,#2563eb)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]" :aria-label="'Корректировка цены: ' + item.title" :aria-describedby="priceTooltipId(item)">
                  <InformationCircleIcon class="h-5 w-5" aria-hidden="true" />
                </button>
                <div data-storefront-block="shared.tooltip" :id="priceTooltipId(item)" role="tooltip" class="pointer-events-none absolute inset-x-3 top-3 z-auto hidden max-h-[calc(100%-1.5rem)] overflow-auto rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,3_7_18)/var(--tw-bg-opacity,1))] px-3 py-2 text-xs font-normal leading-relaxed text-[color:var(--storefront-text,#ffffff)] shadow-lg group-hover:block group-focus-within:block">
                  <p v-if="hasItemDiscount(item)"><span class="font-semibold">Дилер предоставил выгоду:</span> {{ itemAdjustmentText(item, 'discount') }}</p>
                  <p v-if="hasItemMarkup(item)"><span class="font-semibold">Дилер сделал надбавку:</span> {{ itemAdjustmentText(item, 'markup') }}</p>
                  <p v-if="item.dealer_comment" class="mt-1 border-t border-[color:rgb(var(--storefront-border-rgb,255_255_255)/0.2)] pt-1"><span class="font-semibold">Комментарий:</span> {{ item.dealer_comment }}</p>
                </div>
              </div>
            </div>
          </div>
          <div
            v-if="!authStore.isLeasingCompany && (item.overstock_requested_quantity ?? 0) > 0"
            class="relative z-20 mt-2 rounded-md border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs text-[color:var(--storefront-warning-text,#92400e)]"
          >
            Клиент запросил сверх наличия: <strong>{{ item.overstock_requested_quantity }} шт.</strong> — не включено в заявку.
          </div>
          <p v-else class="relative z-auto mt-1 text-sm font-medium tabular-nums text-[color:var(--storefront-text,#111827)]">{{ formatCommerceMoney(itemDisplayPrice(item), item.currency_code) }}</p>
        </div>
      </li>
    </ul>
    <details v-if="historicalItems.length" class="mt-4 border-t border-[color:var(--storefront-border,#e5e7eb)] pt-4">
      <summary class="cursor-pointer text-sm font-semibold text-[color:var(--storefront-text,#374151)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]">
        История состава · {{ historicalItems.length }}
      </summary>
      <ul class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <li v-for="item in historicalItems" :key="`${item.type}:${item.id}`" class="relative flex gap-3 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-3 opacity-75">
          <NuxtLink v-if="safeDetailUrl(item.detail_url)" :to="safeDetailUrl(item.detail_url) ?? '/'" class="absolute inset-0 z-10 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]" :aria-label="`Открыть ${item.title}`" />
          <div class="grid h-14 w-16 shrink-0 place-items-center overflow-hidden rounded-md bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]">
            <img v-if="safeProxyUrl(item.image_url)" :src="safeProxyUrl(item.image_url) ?? undefined" :alt="item.title" class="h-full w-full object-contain grayscale" width="128" height="112">
            <PhotoIcon v-else class="h-6 w-6 text-[color:var(--storefront-icon,#d1d5db)]" aria-hidden="true" />
          </div>
          <div class="min-w-0">
            <p class="line-clamp-2 text-sm font-semibold leading-snug text-[color:var(--storefront-text,#1f2937)]">{{ item.title }}</p>
            <span class="mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-medium" :class="historicalStatusPresentation(item).badgeClass">{{ historicalStatusPresentation(item).label }}</span>
            <CommerceApplicationItemComment :comment="item.comment" />
            <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ item.type === 'vehicle' ? 'Автомобиль' : `Спецтехника · ${specialEquipmentApplicationItemRoleLabel(item.item_role)}` }} · {{ item.quantity }} шт.
            </p>
            <div
              v-if="!authStore.isLeasingCompany && (item.overstock_requested_quantity ?? 0) > 0"
              class="relative z-20 mt-2 rounded-md border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs text-[color:var(--storefront-warning-text,#92400e)]"
            >
              Клиент запросил сверх наличия: <strong>{{ item.overstock_requested_quantity }} шт.</strong> — не включено в заявку.
            </div>
          </div>
        </li>
      </ul>
    </details>
  </section>
</template>

<script setup lang="ts">
import CommerceApplicationItemComment from './CommerceApplicationItemComment.vue'
import { InformationCircleIcon, PhotoIcon } from '@heroicons/vue/24/outline'
import { useAuthStore } from '~/features/auth/store/auth'
import { useStorefront } from '~/features/storefront'
import { toStorefrontInternalRoute } from '~/utils/storefrontRoute'
import { specialEquipmentApplicationItemRoleLabel } from '../applicationItemPresentation'
import { applicationVehicleStatusPresentation } from '../applicationVehicleStatusPresentation'
import { formatCommerceMoney, sumMoney } from '../money'
import type { CommerceApplicationItem, CommerceMoney } from '../types'
import RotatingSupportBadge from '~/components/support/RotatingSupportBadge.vue'
import { normalizeSupportPrograms, supportProgramsFromSnapshot } from '~/types/support'
import VehicleRegionsDisplay from '~/features/applications/components/VehicleRegionsDisplay.vue'
import { formatLeasingPurpose, getVehicleRegionLabels, hasPurposeOrRegion } from '~/features/applications/utils/applicationVehicleDisplay'

const props = defineProps<{
  items: CommerceApplicationItem[]
  itemsCount?: number | null
  totalItemsPrice?: CommerceMoney | null
  vehicleStatusOverrides?: ReadonlyMap<CommerceApplicationItem['id'], ItemStatusPresentation>
  showPurposeRegions?: boolean
}>()
const authStore = useAuthStore()
const { publicRoute } = useStorefront()
const historicalStatuses = new Set(['removed', 'replaced', 'rejected'])
const showPurposeRegions = computed(() => props.showPurposeRegions === true)
const liveItems = computed(() => props.items.filter((item) => !item.status || !historicalStatuses.has(item.status)))
const historicalItems = computed(() => props.items.filter((item) => item.status && historicalStatuses.has(item.status)))
const supportProgramsForItem = (item: CommerceApplicationItem) => {
  const direct = normalizeSupportPrograms(item.support_program_details)
  return direct.length ? direct : supportProgramsFromSnapshot(item.snapshot)
}
const hasItemPurposeOrRegions = (item: CommerceApplicationItem): boolean => hasPurposeOrRegion(item)
const itemPurposeLabel = (item: CommerceApplicationItem): string => formatLeasingPurpose(item, '')
const itemRegionLabels = (item: CommerceApplicationItem): string[] => getVehicleRegionLabels(item)
const hasAdjustmentValue = (value: CommerceMoney | null | undefined): boolean => Number(value || 0) > 0
const hasItemDiscount = (item: CommerceApplicationItem): boolean => Boolean(item.discount_type && (hasAdjustmentValue(item.discount_amount) || hasAdjustmentValue(item.discount_value)))
const hasItemMarkup = (item: CommerceApplicationItem): boolean => Boolean(item.markup_type && (hasAdjustmentValue(item.markup_amount) || hasAdjustmentValue(item.markup_value)))
const priceTooltipId = (item: CommerceApplicationItem): string => `application-price-tooltip-${item.type}-${item.id}`
const hasItemAdjustment = (item: CommerceApplicationItem): boolean => hasItemDiscount(item) || hasItemMarkup(item)
const itemShowsCatalogPrice = (item: CommerceApplicationItem): boolean => item.show_catalog_price !== false
const hasPriceAdjustments = computed(() => liveItems.value.some(hasItemAdjustment))
const itemCatalogPrice = (item: CommerceApplicationItem): CommerceMoney | null => item.catalog_price ?? item.unit_price
const itemFinalPrice = (item: CommerceApplicationItem): CommerceMoney | null => item.final_price ?? item.unit_price
const itemDisplayPrice = (item: CommerceApplicationItem): CommerceMoney | null =>
  item.type === 'vehicle' && hasItemAdjustment(item) ? itemFinalPrice(item) : item.total_price
const adjustmentPercentText = (item: CommerceApplicationItem, amount: CommerceMoney | null | undefined): string | null => {
  const catalogPrice = Number(item.catalog_price || 0)
  const adjustment = Number(amount || 0)
  if (!Number.isFinite(catalogPrice) || catalogPrice <= 0 || !Number.isFinite(adjustment) || adjustment <= 0) return null
  return (adjustment / catalogPrice * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) + '%'
}
const itemAdjustmentText = (item: CommerceApplicationItem, direction: 'discount' | 'markup'): string => {
  const type = direction === 'discount' ? item.discount_type : item.markup_type
  const value = direction === 'discount' ? item.discount_value : item.markup_value
  const normalizedAmount = direction === 'discount' ? item.discount_amount : item.markup_amount
  const catalogPrice = Number(item.catalog_price || 0)
  const percentValue = Number(value || 0)
  const amountFromPercent = (type === 'percent_off' || type === 'percent_up')
    && Number.isFinite(catalogPrice) && catalogPrice > 0
    && Number.isFinite(percentValue) && percentValue > 0
    ? (catalogPrice * percentValue / 100).toFixed(2)
    : null
  const amount = normalizedAmount
    ?? ((type === 'rubles_off' || type === 'rubles_up') ? value : amountFromPercent)
  const percent = (type === 'percent_off' || type === 'percent_up') && value
    ? String(value) + '%'
    : adjustmentPercentText(item, amount)
  const amountText = amount ? formatCommerceMoney(amount, item.currency_code) : null
  return [amountText, percent].filter(Boolean).join(', ') || 'Не указано'
}
const positionCount = computed(() => liveItems.value.length)
const unitCount = computed(() => {
  const reportedCount = Number(props.itemsCount)
  return Number.isFinite(reportedCount) && reportedCount >= 0
    ? reportedCount
    : liveItems.value.reduce((sum, item) => sum + item.quantity, 0)
})
const total = computed(() => props.totalItemsPrice ?? sumMoney(liveItems.value.map((item) => item.total_price)))
const safeProxyUrl = (value: string | null): string | null => value?.startsWith('/api/v1/') ? value : null
const safeDetailUrl = (value: string | null): string | null =>
  toStorefrontInternalRoute(value, publicRoute)
const specialEquipmentStatusLabel = (status: string): string => ({
  active: 'Активна',
  reserved: 'Зарезервирована',
  pending: 'Ожидает обработки',
  approved: 'Подтверждена',
})[status] ?? status
type ItemStatusPresentation = Readonly<{
  label: string
  badgeClass: string
}>
const itemStatusPresentation = (item: CommerceApplicationItem): ItemStatusPresentation => {
  if (item.type === 'vehicle') {
    const override = props.vehicleStatusOverrides?.get(item.id)
    if (override) return override
  }
  return item.type === 'vehicle'
    ? applicationVehicleStatusPresentation(item.status)
    : {
        label: specialEquipmentStatusLabel(item.status ?? ''),
        badgeClass: 'bg-[color:rgb(var(--storefront-info-rgb,239_246_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-info-text,#1e40af)]',
      }
}
const itemStatusLabel = (item: CommerceApplicationItem): string =>
  itemStatusPresentation(item).label
const historicalStatusPresentation = (item: CommerceApplicationItem): ItemStatusPresentation => {
  if (item.type === 'vehicle' && item.status === 'rejected') {
    return applicationVehicleStatusPresentation(item.status)
  }
  return {
    label: ({
      removed: 'Удалена',
      replaced: 'Заменена',
      rejected: 'Отклонена',
    })[item.status ?? ''] ?? 'Историческая позиция',
    badgeClass: 'bg-[color:rgb(var(--storefront-neutral-rgb,229_231_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-neutral-text,#374151)]',
  }
}
const itemWord = (count: number): string => {
  if (count % 10 === 1 && count % 100 !== 11) return 'позиция'
  if (count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 10 || count % 100 >= 20)) return 'позиции'
  return 'позиций'
}
const unitWord = (count: number): string => {
  if (count % 10 === 1 && count % 100 !== 11) return 'единица'
  if (count % 10 >= 2 && count % 10 <= 4 && (count % 100 < 10 || count % 100 >= 20)) return 'единицы'
  return 'единиц'
}
</script>
