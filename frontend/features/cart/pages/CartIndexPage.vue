<template>
  <!-- LC: show exchange cart -->
  <ExchangeCartPage v-if="authStore.isLeasingCompany" />
  <div data-storefront-block="client.cart" v-else class="min-h-screen bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-[color:var(--storefront-title,#111827)]">Корзина</h1>
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Выберите автомобили для оформления заявки</p>
      </div>

      <!-- Loading State -->
      <div v-if="cartStore.loading" class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      </div>

      <!-- Empty Cart -->
      <div v-else-if="cartStore.isEmpty" class="text-center py-12">
        <div class="max-w-md mx-auto">
          <svg class="h-24 w-24 text-[color:var(--storefront-icon,#9ca3af)] mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" data-v-f42ebefd=""><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6h13.5l-1.5 9H8.5L6 6z" data-v-f42ebefd=""></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 6L4 4H2" data-v-f42ebefd=""></path><circle cx="9" cy="20" r="1.5" stroke-width="2" data-v-f42ebefd=""></circle><circle cx="18" cy="20" r="1.5" stroke-width="2" data-v-f42ebefd=""></circle></svg>
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-2">Корзина пуста</h3>
          <p class="text-[color:var(--storefront-text-muted,#4b5563)] mb-6">Добавьте спецтехнику из каталога для создания заявки</p>
          <NuxtLink to="/special-equipment" class="storefront-action-primary inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-[color:var(--storefront-primary-foreground,#ffffff)]  hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]">
            Перейти к каталогу
          </NuxtLink>
        </div>
      </div>

      <!-- Cart Content -->
      <div v-else class="grid grid-cols-1 lg:grid-cols-4 gap-6 lg:gap-8">
        <!-- Cart Items -->
        <div class="lg:col-span-1">
          <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-sm">
            <!-- Cart Header -->
            <div class="p-4 sm:p-6 border-b border-[color:var(--storefront-border,#e5e7eb)]">
              <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <h2 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">
                  Автомобили ({{ cartStore.totalItems }})
                </h2>
                <div class="flex items-center gap-2 sm:gap-4 flex-wrap">
                  <button 
                    @click="selectAll" 
                    :disabled="allSelected"
                    class="storefront-action-ghost text-xs sm:text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1d4ed8)] disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)] whitespace-nowrap"
                  >
                    Выбрать все
                  </button>
                  <span class="inline text-[color:var(--storefront-text,#d1d5db)]">|</span>
                  <button 
                    @click="unselectAll"
                    :disabled="!cartStore.hasSelectedItems"
                    class="storefront-action-ghost text-xs sm:text-sm text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1d4ed8)] disabled:text-[color:var(--storefront-ghost-disabled-foreground,#9ca3af)] whitespace-nowrap"
                  >
                    Снять выбор
                  </button>
                  <span class="inline text-[color:var(--storefront-text,#d1d5db)]">|</span>
                  <button 
                    @click="clearCart"
                    class="storefront-action-ghost text-xs sm:text-sm text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#b91c1c)] whitespace-nowrap ml-auto sm:ml-0"
                  >
                    Очистить
                  </button>
                </div>
              </div>
            </div>

            <!-- Cart Items List -->
            <div class="divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
              <CartComponentsCartItemCard 
                v-for="item in cartStore.items" 
                :key="item.cart_id"
                :item="vehicleCommerceCartLine(item)"
                :equipment-catalog="equipmentCatalog"
                :service-catalog="serviceCatalog"
                @update-selection="updateSelection"
                @update-quantity="updateItemQuantity"
                @update-price="updateItemPrice"
                @update-comment="updateItemComment"
                @update-additional-options="updateAdditionalOptions"
                @remove="removeItem"
                @open-calculation="openCalculationModal(item)"
              />
            </div>
          </div>
        </div>

        <!-- Cart Summary & Calculator -->
        <div class="lg:col-span-5">
          <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-sm sticky top-8">
            <!-- Summary -->
            <div class="p-6 border-b border-[color:var(--storefront-border,#e5e7eb)]">
              <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)] mb-4">Итого</h3>
              
              <div class="space-y-3">
                <div class="flex justify-between text-sm">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Выбрано автомобилей:</span>
                  <span class="font-medium">{{ cartStore.selectedCount }}</span>
                </div>
              </div>
            </div>

            <!-- Leasing Calculator -->
            <div class="p-6 border-b border-[color:var(--storefront-border,#e5e7eb)]">
              <CartCalculatorCartLeasingCalculator 
                ref="calculatorRef"
                :total-amount="cartStore.totalAmount"
                :total-discount="cartStore.totalDiscount"
                :support-display-mode="cartStore.supportDisplayMode"
                :selected-vehicles="cartStore.selectedVehicleIds"
                @calculation-change="onCalculationChange"
              />
            </div>

            <!-- Поддержка по программе (на выбранные ТС) -->
            <div v-if="cartStore.totalDiscount > 0" class="p-6 border-b border-[color:var(--storefront-border,#e5e7eb)]">
              <h3 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)] mb-2 flex items-center">
                <svg class="w-4 h-4 mr-1.5 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                Поддержка по программе (на выбранные ТС)
              </h3>
              <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-1">Поддержка по выбранным автомобилям</p>
              <p class="text-lg font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(cartStore.totalDiscount) }}</p>
            </div>

            <!-- Action Buttons -->
            <div class="p-6">
              <button class="storefront-action-primary"
                @click="handleCheckoutClick"
                :disabled="!cartStore.hasSelectedItems"
                :class="[
                  'block w-full text-center py-3 px-4 rounded-md font-medium',
                  cartStore.hasSelectedItems
                    ? 'bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))]'
                    : 'bg-[color:rgb(var(--storefront-primary-rgb,209_213_219)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#6b7280)] cursor-not-allowed pointer-events-none'
                ]"
              >
                Получить специальное предложение
              </button>
              
              <NuxtLink 
                to="/special-equipment" 
                class="block w-full mt-3 text-center py-3 px-4 border border-[color:var(--storefront-border,#d1d5db)] rounded-md text-[color:var(--storefront-link,#374151)] font-medium hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
              >
                Продолжить выбор
              </NuxtLink>

              <button
                type="button"
                :disabled="!cartStore.hasSelectedItems || generatingCartPdf"
                class="storefront-action-ghost block w-full mt-3 text-center py-3 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-md text-[color:var(--storefront-secondary-foreground,#374151)] font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                @click="downloadCartPdf"
              >
                {{ generatingCartPdf ? 'Формирование PDF...' : 'Скачать PDF' }}
              </button>

              <div v-if="showCartEmailForm" class="mt-3 p-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] space-y-2">
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Email для отправки</label>
                <input
                  v-model="cartEmailToSend"
                  type="email"
                  placeholder="email@example.com"
                  class="storefront-control block w-full rounded-md border border-[color:var(--storefront-border,#d1d5db)] py-2 px-3 text-sm focus:border-[color:var(--storefront-border,#3b82f6)] focus:outline-none focus:ring-1 focus:ring-[color:var(--storefront-focus,#3b82f6)]"
                />
                <div class="flex gap-2">
                  <button
                    type="button"
                    class="storefront-action-ghost flex-1 py-2 px-3 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-md text-sm font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
                    @click="showCartEmailForm = false; cartEmailToSend = ''"
                  >
                    Отмена
                  </button>
                  <button
                    type="button"
                    :disabled="sendingCartEmail || !cartEmailToSend"
                    class="storefront-action-primary flex-1 py-2 px-3 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] rounded-md text-sm font-medium hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                    @click="sendCartByEmail"
                  >
                    {{ sendingCartEmail ? 'Отправка...' : 'Отправить' }}
                  </button>
                </div>
              </div>
              <button
                v-else
                type="button"
                :disabled="!cartStore.hasSelectedItems || sendingCartEmail"
                class="storefront-action-ghost block w-full mt-3 text-center py-3 px-4 border border-[color:var(--storefront-secondary-border,#d1d5db)] rounded-md text-[color:var(--storefront-secondary-foreground,#374151)] font-medium hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:opacity-50 disabled:cursor-not-allowed"
                @click="showCartEmailForm = true"
              >
                Отправить на почту
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <AuthModal 
      v-if="showAuthModal"
      @close="showAuthModal = false"
      @authenticated="handleAuthenticated"
    />

    <CartComponentsCartItemCalculationModal
      :show="showCalculationModal"
      :item="calculationModalItem"
      :calculator-params="calculationModalParams"
      :vehicle-calculation-data="calculationModalVehicleData"
      @close="handleCalculationModalClose"
      @support-change="handleSupportChange"
    />
  </div>
</template>

<script setup lang="ts">
import AuthModal from '~/features/auth/components/AuthModal.vue'
import ExchangeCartPage from "~/features/exchange/pages/ExchangeCartPage.vue"
import { vehicleCommerceCartLine } from '~/features/cart/adapters/vehicleCommerceCartLine'
import type { CommerceCartLine } from '~/features/commerce/cartProjection'
import type { CommerceItemRef } from '~/features/commerce/types'
import { useCompanySelectHistory } from '~/features/auth/composables/useCompanySelectHistory'
import { useAuthStore } from '~/features/auth/store/auth'
import { imageBlobToPdfSafeDataUrl } from '~/features/cart/utils/pdfImage'
import { createAdditionalOptionsApi, type AdditionalEquipmentCatalogItem, type AdditionalServiceCatalogItem } from '~/utils/additionalOptionsApi'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'
import type {
  CalculatorParams,
  CartCalculationData,
  CartItemLike,
  LeasingCalculationResult,
  SupportBreakdown,
} from '~/features/cart/types'
import type { CartEmailData } from '~/types/domains'
import type { UUID } from '~/types/ids'

// Cart page available for all users (authenticated and guests)

const cartStore = useCartStore()
const authStore = useAuthStore()
const favoritesStore = useFavoritesStore()
const { formatPrice } = useFormatPrice()
const checkoutStore = useCheckoutStore()
const router = useRouter()
const companySelect = useCompanySelectHistory()
const companySelectDisabled = computed(() => companySelect.loadingCompanies.value || companySelect.loadingSelected.value || companySelect.savingSelected.value)
const companyList = computed(() => companySelect.companies.value)
const config = useRuntimeConfig()
const toast = useToast()
const additionalOptionsApi = createAdditionalOptionsApi(config)

type CheckoutCalculationPayload = Omit<CartCalculationData, 'calculation'> & {
  calculation?: LeasingCalculationResult
}

const setCheckoutCalculation = (calculation: CartCalculationData) => {
  const payload: CheckoutCalculationPayload = {
    ...calculation,
    calculation: calculation.calculation ?? undefined,
  }
  const writeCalculation = checkoutStore.setCalculation as unknown as (
    value: CheckoutCalculationPayload
  ) => void
  writeCalculation(payload)
}

const calculationData = ref<CartCalculationData | null>(null)
const calculatorRef = ref<{ recalculate: () => Promise<boolean> } | null>(null)
const equipmentCatalog = ref<AdditionalEquipmentCatalogItem[]>([])
const serviceCatalog = ref<AdditionalServiceCatalogItem[]>([])
const generatingCartPdf = ref(false)
const showCartEmailForm = ref(false)
const cartEmailToSend = ref('')
const sendingCartEmail = ref(false)
const showAuthModal = ref(false)
const showCalculationModal = ref(false)
const calculationModalItem = ref<CommerceCartLine | null>(null)
const calculationModalParams = computed<CalculatorParams | null>(() => {
  if (!calculationData.value) return null
  const d = calculationData.value
  return {
    down_payment_percent: d.down_payment_percent ?? 20,
    lease_term_months: d.lease_term_months ?? 36,
    buyout_percent: d.buyout_percent ?? 0
  }
})

const calculationModalVehicleData = computed(() => {
  if (!calculationModalItem.value || !calculationData.value) return null
  if (calculationModalItem.value.ref.type !== 'vehicle') return null
  const vid = calculationModalItem.value.ref.id
  const perVehicle = calculationData.value.calculations_per_vehicle.find((row) => row.vehicle_id === vid)
  const eligibleRow = calculationData.value.eligible_support_program_ids_by_vehicle.find((row) => row.vehicle_id === vid)
  return {
    calculation: perVehicle?.calculation ?? null,
    calculation_without_support: perVehicle?.calculation_without_support ?? null,
    support_breakdown: perVehicle?.support_breakdown ?? null,
    support_per_program: calculationData.value.support_per_program ?? [],
    support_program_details: calculationData.value.support_program_details ?? [],
    eligible_program_ids: eligibleRow?.program_ids ?? []
  }
})

async function getItemImageDataUrl(item: CartItemLike) {
  if (!item?.images?.length) return null
  const path = vehicleImageUrl(item.images[0])
  const apiBase = String(config.public?.apiBase || '').replace(/\/$/, '')
  const imageUrl = apiBase ? `${apiBase}${path}` : (typeof window !== 'undefined' ? `${window.location.origin}${path}` : path)
  try {
    const response = await fetch(imageUrl, { credentials: 'include' })
    if (!response.ok) return null
    const blob = await response.blob()
    return await imageBlobToPdfSafeDataUrl(blob)
  } catch {
    return null
  }
}

async function downloadCartPdf() {
  if (!cartStore.hasSelectedItems) return
  generatingCartPdf.value = true
  try {
    const pdfMake = await import('pdfmake/build/pdfmake')
    const pdfFonts = await import('pdfmake/build/vfs_fonts')
    const pdfMakeInstance = pdfMake.default || pdfMake
    if (pdfFonts.pdfMake?.vfs) pdfMakeInstance.vfs = pdfFonts.pdfMake.vfs
    else if (pdfFonts.default) pdfMakeInstance.vfs = pdfFonts.default
    else throw new Error('Шрифты PDF не загружены')

    const params = calculationModalParams.value
    const downPercent = params?.down_payment_percent ?? 20
    const termMonths = params?.lease_term_months ?? 36
    const buyoutPct = params?.buyout_percent ?? 0
    const content = []

    content.push({ text: 'Расчет лизинга — выбранные ТС и общий расчет', style: 'header', alignment: 'center' })
    content.push({ text: '\n' })

    function addSupportBlock(content: unknown[], support: SupportBreakdown | null | undefined, styles?: { subheader?: string }) {
      if (!support) return
      const dp = Number(support.down_payment_support) || 0
      const vd = Number(support.vehicle_discount_support) || 0
      const in_ = Number(support.interest_support) || 0
      if (dp === 0 && vd === 0 && in_ === 0) return
      content.push({ text: 'Учтено в расчёте:', style: styles?.subheader || 'subheader' })
      if (dp > 0) {
        content.push({
          columns: [
            { text: 'Поддержка первого взноса', style: 'label' },
            { text: formatPrice(dp), style: 'value', alignment: 'right' }
          ],
          margin: [0, 0, 0, 4]
        })
      }
      if (vd > 0) {
        content.push({
          columns: [
            { text: 'Поддержка на ТС', style: 'label' },
            { text: formatPrice(vd), style: 'value', alignment: 'right' }
          ],
          margin: [0, 0, 0, 4]
        })
      }
      if (in_ > 0) {
        content.push({
          columns: [
            { text: 'Поддержка процентов', style: 'label' },
            { text: formatPrice(in_), style: 'value', alignment: 'right' }
          ],
          margin: [0, 0, 0, 4]
        })
      }
      content.push({ text: '\n' })
    }

    const selectedItems = cartStore.selectedItems
    const perVehicleCalcs = calculationData.value?.calculations_per_vehicle || []
    for (let idx = 0; idx < selectedItems.length; idx++) {
      const item = selectedItems[idx]
      if (idx > 0) {
        content.push({ text: '', margin: [0, 12, 0, 0] })
        content.push({
          table: { body: [['']], widths: ['*'] },
          layout: { hLineWidth: (i: number) => (i === 1 ? 0.5 : 0), vLineWidth: () => 0 },
          margin: [0, 4, 0, 12]
        })
      }
      const quantity = Math.max(1, Number(item.quantity) || 1)
      const pricePerUnit = Number(item.custom_price) || Number(item.base_price) || 0
      let calcResult = null
      let itemSupport = null
      const perVehicle = perVehicleCalcs.find((row) => row.vehicle_id === item.vehicle_id)
      if (perVehicle) {
        calcResult = perVehicle.calculation ?? null
        itemSupport = perVehicle.support_breakdown ?? null
      }

      const vehicleTitle = `${item.mark_name || ''} ${item.model_name || ''}`.trim() || 'Автомобиль'
      const imageDataUrl = await getItemImageDataUrl(item as CartItem)

      content.push({ text: vehicleTitle, style: 'sectionHeader' })
      content.push({
        columns: [
          imageDataUrl ? { image: imageDataUrl, fit: [140, 90], margin: [0, 0, 12, 0] } : { text: '', width: 0 },
          {
            width: '*',
            stack: [
              { text: `Цена за 1 ТС: ${formatPrice(pricePerUnit)}`, style: 'normal' },
              { text: `Количество: ${quantity}`, style: 'normal' },
              { text: `Срок договора: ${termMonths} мес.`, style: 'normal' },
              { text: `Выкупная стоимость: ${buyoutPct}%`, style: 'normal' }
            ]
          }
        ]
      })
      content.push({ text: '\n' })

      const blockTitle = quantity > 1 ? `Расчет на ${quantity} ТС` : 'Расчет на 1 ТС'
      content.push({ text: blockTitle, style: 'subheader' })
      const calcRows = calcResult
        ? [
            { label: 'Ежемесячный платёж', value: formatPrice(calcResult.monthlyPayment) },
            { label: 'Первоначальный взнос', value: `${downPercent}%` },
            { label: 'Сумма договора', value: formatPrice(calcResult.totalCost) }
          ]
        : [{ label: 'Статус', value: 'Нет данных расчета' }]
      for (const row of calcRows) {
        content.push({
          columns: [
            { text: row.label, style: 'label' },
            { text: row.value, style: 'value', alignment: 'right' }
          ],
          margin: [0, 0, 0, 4]
        })
      }
      addSupportBlock(content, itemSupport as SupportBreakdown | null)
      content.push({ text: 'Подробные характеристики', style: 'subheader' })
      const details = []
      if (item.mark_name) details.push({ label: 'Марка', value: String(item.mark_name) })
      if (item.model_name) details.push({ label: 'Модель', value: String(item.model_name) })
      if ((item as CartItem).group_name) details.push({ label: 'Комплектация', value: String((item as CartItem).group_name) })
      if (item.vin) details.push({ label: 'VIN', value: String(item.vin) })
      if (item.color) details.push({ label: 'Цвет', value: String(item.color) })
      if (item.year) details.push({ label: 'Год', value: String(item.year) })
      details.push({ label: 'Базовая цена', value: formatPrice(item.base_price || 0) })
      if (item.comment) details.push({ label: 'Комментарий', value: String(item.comment) })
      for (const row of details) {
        content.push({
          columns: [
            { text: row.label, style: 'label' },
            { text: row.value, style: 'value', alignment: 'right' }
          ],
          margin: [0, 0, 0, 4]
        })
      }
      content.push({ text: '\n' })
    }

    content.push({ text: 'Общий расчет (все выбранные ТС)', style: 'header', alignment: 'center' })
    content.push({ text: '\n' })
    const totalAmount = cartStore.totalAmount
    const overallCalc: LeasingCalculationResult | null = calculationData.value?.calculation ?? null
    const overallSupport: SupportBreakdown | null = calculationData.value?.support ?? null
    content.push({ text: `Стоимость имущества: ${formatPrice(totalAmount)}`, style: 'subheader' })
    content.push({ text: `Срок договора: ${termMonths} мес.`, style: 'normal' })
    content.push({ text: `Первоначальный взнос: ${downPercent}%`, style: 'normal' })
    content.push({ text: `Выкупная стоимость: ${buyoutPct}%`, style: 'normal' })
    content.push({ text: '\n' })
    if (overallCalc) {
      content.push({
        columns: [
          { text: 'Ежемесячный платёж', style: 'label' },
          { text: formatPrice(overallCalc.monthlyPayment), style: 'value', alignment: 'right' }
        ],
        margin: [0, 0, 0, 4]
      })
      content.push({
        columns: [
          { text: 'Сумма договора', style: 'label' },
          { text: formatPrice(overallCalc.totalCost), style: 'value', alignment: 'right' }
        ],
        margin: [0, 0, 0, 4]
      })
    } else {
      content.push({ text: 'Выполните расчет в калькуляторе выше для отображения общего ежемесячного платежа и суммы договора.', style: 'normal' })
    }
    addSupportBlock(content, overallSupport as SupportBreakdown | null)

    const doc = pdfMakeInstance.createPdf({
      pageSize: 'A4',
      pageMargins: [36, 36, 36, 36],
      content,
      styles: {
        header: { fontSize: 18, bold: true, margin: [0, 0, 0, 10] },
        subheader: { fontSize: 13, bold: true, margin: [0, 0, 0, 6] },
        sectionHeader: { fontSize: 12, bold: true, margin: [0, 8, 0, 6] },
        normal: { fontSize: 10, margin: [0, 0, 0, 3] },
        label: { fontSize: 10, color: '#374151' },
        value: { fontSize: 10, bold: true, color: '#111827' }
      },
      defaultStyle: { fontSize: 10 }
    })
    doc.getBlob((blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `raschet-korzina-${Date.now()}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    })
    toast?.success?.('PDF сформирован')
  } catch (e) {
    console.error('PDF error:', e)
    toast?.error?.('Не удалось сформировать PDF')
  } finally {
    generatingCartPdf.value = false
  }
}

function escapeHtml(value: unknown) {
  if (value == null) return ''
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

async function getCartEmailData() {
  const params = calculationModalParams.value
  const downPercent = params?.down_payment_percent ?? 20
  const termMonths = params?.lease_term_months ?? 36
  const buyoutPct = params?.buyout_percent ?? 0
  const items = []
  const selectedItems = cartStore.selectedItems
  const perVehicleCalcs = calculationData.value?.calculations_per_vehicle || []
  for (const item of selectedItems) {
    const quantity = Math.max(1, Number(item.quantity) || 1)
    const pricePerUnit = Number(item.custom_price) || Number(item.base_price) || 0
    let calcResult = null
    let itemSupport = null
    const perVehicle = perVehicleCalcs.find((row) => row.vehicle_id === item.vehicle_id)
    if (perVehicle) {
      calcResult = perVehicle.calculation ?? null
      itemSupport = perVehicle.support_breakdown ?? null
    }
    const vehicleTitle = `${item.mark_name || ''} ${item.model_name || ''}`.trim() || 'Автомобиль'
    const priceLine = `Цена за 1 ТС: ${formatPrice(pricePerUnit)}`
    const calcRows = calcResult
      ? [
          { label: 'Ежемесячный платёж', value: formatPrice(calcResult.monthlyPayment) },
          { label: 'Первоначальный взнос', value: `${downPercent}%` },
          { label: 'Сумма договора', value: formatPrice(calcResult.totalCost) }
        ]
      : [{ label: 'Статус', value: 'Нет данных расчета' }]
    const details = []
    if (item.mark_name) details.push({ label: 'Марка', value: String(item.mark_name) })
    if (item.model_name) details.push({ label: 'Модель', value: String(item.model_name) })
    if (item.group_name) details.push({ label: 'Комплектация', value: String(item.group_name) })
    if (item.vin) details.push({ label: 'VIN', value: String(item.vin) })
    if (item.color) details.push({ label: 'Цвет', value: String(item.color) })
    if (item.year) details.push({ label: 'Год', value: String(item.year) })
    details.push({ label: 'Базовая цена', value: formatPrice(item.base_price || 0) })
    if (item.comment) details.push({ label: 'Комментарий', value: String(item.comment) })
    const supportRow = (() => {
      if (!itemSupport) return null
      const dp = Number(itemSupport.down_payment_support) || 0
      const vd = Number(itemSupport.vehicle_discount_support) || 0
      const in_ = Number(itemSupport.interest_support) || 0
      if (dp === 0 && vd === 0 && in_ === 0) return null
      const parts = []
      if (dp > 0) parts.push(`Поддержка первого взноса: ${formatPrice(dp)}`)
      if (vd > 0) parts.push(`Поддержка на ТС: ${formatPrice(vd)}`)
      if (in_ > 0) parts.push(`Поддержка процентов: ${formatPrice(in_)}`)
      return parts.join('; ')
    })()
    items.push({
      vehicleTitle,
      quantity,
      priceLine,
      termMonths,
      buyoutPct,
      calcRows,
      supportRow,
      details
    })
  }
  const totalAmount = cartStore.totalAmount
  const overallCalc = calculationData.value?.calculation ?? null
  const overallSupport = calculationData.value?.support ?? null
  return {
    downPercent,
    termMonths,
    buyoutPct,
    items,
    totalAmount,
    overallCalc,
    overallSupport
  }
}

function buildCartEmailText(data: CartEmailData) {
  const lines = [
    'Расчет лизинга — выбранные ТС и общий расчет',
    '',
    ''
  ]
  for (let i = 0; i < data.items.length; i++) {
    const it = data.items[i]
    if (i > 0) lines.push('---', '')
    lines.push(it.vehicleTitle, '')
    lines.push(it.priceLine)
    lines.push(`Количество: ${it.quantity}`)
    lines.push(`Срок договора: ${it.termMonths} мес.`)
    lines.push(`Выкупная стоимость: ${it.buyoutPct}%`, '')
    for (const row of it.calcRows) {
      lines.push(`${row.label}: ${row.value}`)
    }
    if (it.supportRow) lines.push(`Учтено в расчёте: ${it.supportRow}`, '')
    lines.push('Подробные характеристики:')
    for (const row of it.details) {
      lines.push(`${row.label}: ${row.value}`)
    }
    lines.push('')
  }
  lines.push('Общий расчет (все выбранные ТС)', '')
  lines.push(`Стоимость имущества: ${formatPrice(data.totalAmount)}`)
  lines.push(`Срок договора: ${data.termMonths} мес.`)
  lines.push(`Первоначальный взнос: ${data.downPercent}%`)
  lines.push(`Выкупная стоимость: ${data.buyoutPct}%`, '')
  if (data.overallCalc) {
    lines.push(`Ежемесячный платёж: ${formatPrice(data.overallCalc.monthlyPayment)}`)
    lines.push(`Сумма договора: ${formatPrice(data.overallCalc.totalCost)}`)
  } else {
    lines.push('Выполните расчет в калькуляторе на странице корзины для отображения общего ежемесячного платежа.')
  }
  if (data.overallSupport) {
    const dp = Number(data.overallSupport.down_payment_support) || 0
    const vd = Number(data.overallSupport.vehicle_discount_support) || 0
    const in_ = Number(data.overallSupport.interest_support) || 0
    if (dp > 0 || vd > 0 || in_ > 0) {
      const parts = []
      if (dp > 0) parts.push(`Поддержка первого взноса: ${formatPrice(dp)}`)
      if (vd > 0) parts.push(`Поддержка на ТС: ${formatPrice(vd)}`)
      if (in_ > 0) parts.push(`Поддержка процентов: ${formatPrice(in_)}`)
      lines.push('', `Учтено в расчёте: ${parts.join('; ')}`)
    }
  }
  return lines.join('\n')
}

function buildCartEmailHtml(data: CartEmailData) {
  const itemBlocks = data.items.map((it) => {
    const calcRows = it.calcRows
      .map((row) => `
        <tr>
          <td style="padding: 6px 0; color: #4b5563;">${escapeHtml(row.label)}</td>
          <td style="padding: 6px 0; color: #111827; font-weight: 600; text-align: right;">${escapeHtml(row.value)}</td>
        </tr>
      `)
      .join('')
    const detailsRows = it.details
      .map((row) => `
        <tr>
          <td style="padding: 6px 0; color: #4b5563;">${escapeHtml(row.label)}</td>
          <td style="padding: 6px 0; color: #111827; font-weight: 600; text-align: right;">${escapeHtml(row.value)}</td>
        </tr>
      `)
      .join('')
    const supportBlock = it.supportRow
      ? `<div style="font-size: 12px; color: #059669; margin: 6px 0;">Учтено в расчёте: ${escapeHtml(it.supportRow)}</div>`
      : ''
    return `
      <div style="margin: 0 0 20px 0; padding: 14px; border: 1px solid #e5e7eb; border-radius: 10px;">
        <div style="font-size: 16px; font-weight: 600; color: #111827; margin-bottom: 8px;">${escapeHtml(it.vehicleTitle)}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">${escapeHtml(it.priceLine)}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">Количество: ${it.quantity}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">Срок договора: ${it.termMonths} мес.</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 10px;">Выкупная стоимость: ${it.buyoutPct}%</div>
        <table style="width: 100%; border-collapse: collapse;">${calcRows}</table>
        ${supportBlock}
        <div style="margin-top: 10px; font-size: 13px; font-weight: 600;">Подробные характеристики</div>
        <table style="width: 100%; border-collapse: collapse;">${detailsRows}</table>
      </div>
    `
  }).join('')

  let overallBlock = `
    <div style="margin-top: 16px; padding: 14px; border: 1px solid #d1d5db; border-radius: 10px; background: #f9fafb;">
      <div style="font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 8px;">Общий расчет (все выбранные ТС)</div>
      <div style="font-size: 14px; color: #374151;">Стоимость имущества: ${escapeHtml(formatPrice(data.totalAmount))}</div>
      <div style="font-size: 14px; color: #374151;">Срок договора: ${data.termMonths} мес.</div>
      <div style="font-size: 14px; color: #374151;">Первоначальный взнос: ${data.downPercent}%</div>
      <div style="font-size: 14px; color: #374151; margin-bottom: 8px;">Выкупная стоимость: ${data.buyoutPct}%</div>
  `
  if (data.overallCalc) {
    overallBlock += `
      <div style="font-size: 14px; font-weight: 600;">Ежемесячный платёж: ${escapeHtml(formatPrice(data.overallCalc.monthlyPayment))}</div>
      <div style="font-size: 14px; font-weight: 600;">Сумма договора: ${escapeHtml(formatPrice(data.overallCalc.totalCost))}</div>
    `
  } else {
    overallBlock += `<div style="font-size: 14px; color: #6b7280;">Выполните расчет в калькуляторе на странице корзины для отображения общего платежа.</div>`
  }
  if (data.overallSupport) {
    const dp = Number(data.overallSupport.down_payment_support) || 0
    const vd = Number(data.overallSupport.vehicle_discount_support) || 0
    const in_ = Number(data.overallSupport.interest_support) || 0
    if (dp > 0 || vd > 0 || in_ > 0) {
      const parts = []
      if (dp > 0) parts.push(`Поддержка первого взноса: ${formatPrice(dp)}`)
      if (vd > 0) parts.push(`Поддержка на ТС: ${formatPrice(vd)}`)
      if (in_ > 0) parts.push(`Поддержка процентов: ${formatPrice(in_)}`)
      overallBlock += `<div style="font-size: 12px; color: #059669; margin-top: 6px;">Учтено в расчёте: ${escapeHtml(parts.join('; '))}</div>`
    }
  }
  overallBlock += '</div>'

  return `
    <div style="font-family: Arial, sans-serif; max-width: 680px; margin: 0 auto; color: #111827; background: #ffffff;">
      <div style="padding: 18px; border: 1px solid #e5e7eb; border-radius: 12px;">
        <h2 style="margin: 0 0 14px 0; font-size: 20px; text-align: center;">Расчет лизинга — выбранные ТС и общий расчет</h2>
        ${itemBlocks}
        ${overallBlock}
      </div>
    </div>
  `
}

async function sendCartByEmail() {
  if (!cartEmailToSend.value || !cartStore.hasSelectedItems) return
  sendingCartEmail.value = true
  try {
    const data = await getCartEmailData()
    const text = buildCartEmailText(data)
    const html = buildCartEmailHtml(data)
    await $fetch('/api/v1/calculator/send-calculation-email', {
      method: 'POST',
      body: {
        to: cartEmailToSend.value,
        subject: 'Расчет лизинга — корзина',
        text,
        html
      },
      baseURL: config.public?.apiBase,
      credentials: 'include'
    })
    showCartEmailForm.value = false
    cartEmailToSend.value = ''
    toast?.success?.('Расчет отправлен на указанный email')
  } catch (e) {
    console.error('Send cart email error:', e)
    toast?.error?.((e as { data?: { error?: string } })?.data?.error || 'Не удалось отправить письмо')
  } finally {
    sendingCartEmail.value = false
  }
}

function openCalculationModal(item: CartItemLike) {
  calculationModalItem.value = vehicleCommerceCartLine(item)
  showCalculationModal.value = true
}

const showCompanyDropdown = computed(() => companySelect.companies.value.length >= 2)

const allSelected = computed(() => {
  return cartStore.totalItems > 0 && cartStore.selectedCount === cartStore.totalItems
})

const updateSelection = async (item: CommerceItemRef, isSelected: boolean) => {
  if (item.type !== 'vehicle') return
  const result = await cartStore.updateSelection(item.id, isSelected)
  if (!result.success) {
    // Show error notification
    console.error(result.error)
    return
  }
  recalculateCart()
}

const removeItem = async (item: CommerceItemRef) => {
  if (item.type !== 'vehicle') return
  const result = await cartStore.removeFromCart(item.id)
  if (result.success) {
    // Show success notification
    recalculateCart()
  } else {
    // Show error notification
    console.error(result.error)
  }
}

const selectAll = async () => {
  const result = await cartStore.selectAll()
  if (!result.success) {
    console.error(result.error)
    return
  }
  recalculateCart()
}

const unselectAll = async () => {
  const result = await cartStore.unselectAll()
  if (!result.success) {
    console.error(result.error)
    return
  }
  recalculateCart()
}

const clearCart = async () => {
  if (confirm('Вы уверены, что хотите очистить корзину?')) {
    const result = await cartStore.clearCart()
    if (!result.success) {
      console.error(result.error)
    }
  }
}

const onCalculationChange = (calculation: CartCalculationData | null) => {
  calculationData.value = calculation
  if (!calculation) checkoutStore.setCalculation(null)
}

const recalculateCart = async (): Promise<boolean> => {
  if (calculatorRef.value && typeof calculatorRef.value.recalculate === 'function') {
    return calculatorRef.value.recalculate()
  }
  calculationData.value = null
  checkoutStore.setCalculation(null)
  return false
}

const requireFreshCheckoutCalculation = async (): Promise<boolean> => {
  checkoutStore.setCalculation(null)
  const calculated = await recalculateCart()
  if (!calculated || !calculationData.value?.calculation) {
    toast.error('Не удалось получить актуальный расчёт. Проверьте параметры и повторите.')
    return false
  }
  setCheckoutCalculation(calculationData.value)
  return true
}

const handleCalculationModalClose = () => {
  showCalculationModal.value = false
}

const handleSupportChange = () => {
  // Пересчитать общий калькулятор при изменении поддержки, не закрывая модалку
  void recalculateCart()
}

const handleCheckoutClick = async () => {
  if (!authStore.isAuthenticated) {
    showAuthModal.value = true
    return
  }

  if (!await requireFreshCheckoutCalculation()) return

  router.push('/cart/conditions')
}

const handleAuthenticated = async () => {
  showAuthModal.value = false
  await favoritesStore.mergeGuestFavorites()
  if (!await requireFreshCheckoutCalculation()) return

  router.push('/cart/conditions')
}

const updateItemQuantity = async (item: CommerceItemRef, quantity: number, _cartItemId?: UUID, allowOverstock?: boolean, onSettled?: () => void) => {
  try {
    if (item.type !== 'vehicle') return
    const result = await cartStore.updateQuantity(item.id, quantity, allowOverstock)
    if (!result.success) {
      console.error(result.error)
      return
    }
    await recalculateCart()
  } finally {
    onSettled?.()
  }
}

const updateItemPrice = async (item: CommerceItemRef, price: number | null) => {
  if (item.type !== 'vehicle') return
  const result = await cartStore.updatePrice(item.id, price)
  if (!result.success) {
    console.error(result.error)
    return
  }
  await recalculateCart()
}

const updateItemComment = async (item: CommerceItemRef, comment: string) => {
  if (item.type !== 'vehicle') return
  await cartStore.updateComment(item.id, comment)
}

const updateAdditionalOptions = async (
  item: CommerceItemRef,
  payload: {
    equipments?: Array<{ equipment_code: string; price?: number | null }>
    services?: Array<{ service_code: string; price?: number | null }>
  }
) => {
  if (item.type !== 'vehicle') return
  const result = await cartStore.updateAdditionalOptions(item.id, payload)
  if (!result.success) {
    console.error(result.error)
    return
  }
  await recalculateCart()
}

const loadAdditionalOptionsCatalog = async () => {
  try {
    const equipments = await additionalOptionsApi.getEquipments()
    equipmentCatalog.value = Array.isArray(equipments.items) ? equipments.items : []

    const services = await additionalOptionsApi.getServices()
    serviceCatalog.value = Array.isArray(services.items) ? services.items : []
  } catch (error) {
    console.error('Error loading additional options catalogs:', error)
  }
}

const onCompanyChange = async (event: Event) => {
  const target = event.target as HTMLSelectElement
  const id = target.value || null
  if (id != null) await companySelect.selectCompany(id)
}

// Initialize cart and company selection on mount
onMounted(async () => {
  await cartStore.initialize()
  await loadAdditionalOptionsCatalog()
  if (authStore.isAuthenticated) {
    try {
      await companySelect.loadCompanies()
      await companySelect.loadSelectedCompany()
    } catch {
      // ignore: user may have no companies
    }
  }
})

// Meta
useSeoMeta({
  title: 'Корзина - CarCraft Multileasing',
  description: 'Управление выбранными автомобилями и создание заявки на лизинг'
})
</script>

<style scoped>
/* Custom styles for cart page */
</style>
