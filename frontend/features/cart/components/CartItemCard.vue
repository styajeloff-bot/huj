<template>
  <div data-storefront-block="client.cart" class="px-4 sm:px-6 py-5 sm:py-6" :data-testid="`cart-item-${item.cart_id}`">
    <div class="flex gap-3 sm:gap-4">
      <!-- Selection + image -->
      <div class="flex shrink-0 gap-3">
        <div class="pt-1">
          <input 
            :id="`item-${item.cart_id}`"
            type="checkbox" 
            :checked="item.is_selected"
            :aria-label="`Выбрать ${itemTitle}`"
            @change="$emit('update-selection', item.ref, ($event.target as HTMLInputElement).checked, item.cart_id)"
            class="storefront-control h-5 w-5 text-[color:var(--storefront-text-muted,#2563eb)] border-[color:var(--storefront-border,#d1d5db)] rounded focus:ring-[color:var(--storefront-focus,#3b82f6)] cursor-pointer"
          >
        </div>

        <div 
          @click="viewDetails"
          class="w-[88px] h-[60px] sm:w-28 sm:h-[72px] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden transition-opacity flex-shrink-0 flex items-center justify-center"
          :class="item.detail_url ? 'cursor-pointer hover:opacity-90' : ''"
        >
          <img
            v-if="item.image_url"
            :src="item.image_url"
            :alt="itemTitle"
            class="w-full h-full object-contain"
            onerror="this.src='/images/car-placeholder.png'"
          >
          <div v-else class="w-full h-full flex items-center justify-center text-[color:var(--storefront-text-muted,#9ca3af)]">
            <svg class="text-[color:var(--storefront-icon,inherit)] w-6 h-6 sm:w-8 sm:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
            </svg>
          </div>
        </div>
      </div>

      <!-- Main column -->
      <div class="min-w-0 flex-1 space-y-4">
        <div>
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <h3
                @click="viewDetails"
                class="text-base sm:text-lg font-semibold leading-snug"
                :class="[
                  unavailableStatus ? 'text-[color:var(--storefront-title,#9ca3af)]' : 'text-[color:var(--storefront-title,#111827)]',
                  item.detail_url ? 'cursor-pointer hover:text-[color:var(--storefront-title,#1d4ed8)]' : '',
                ]"
              >
                {{ item.mark_name }} {{ item.model_name }}
                <span v-if="isModelOrder" class="ml-2 inline-flex px-2 py-0.5 text-xs font-medium rounded-md bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)] border border-[color:var(--storefront-border,#dbeafe)]">
                  Заказ по модели
                </span>
                <span v-if="unavailableStatus === 'reserved'" class="ml-2 inline-flex px-2 py-0.5 text-xs font-medium rounded-md bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#92400e)] border border-[color:var(--storefront-warning-border,#fde68a)]">
                  Зарезервировано
                </span>
                <span v-else-if="unavailableStatus === 'sold'" class="ml-2 inline-flex px-2 py-0.5 text-xs font-medium rounded-md bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#b91c1c)] border border-[color:var(--storefront-error-border,#fecaca)]">
                  Продано
                </span>
                <span v-else-if="unavailableStatus === 'out_of_stock'" class="ml-2 inline-flex rounded-md border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] px-2 py-0.5 text-xs font-medium text-[color:var(--storefront-error-text,#b91c1c)]">
                  Недостаточно на складе
                </span>
                <span v-else-if="unavailableStatus === 'availability_unconfirmed'" class="ml-2 inline-flex rounded-md border border-[color:var(--storefront-warning-border,#fde68a)] bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] px-2 py-0.5 text-xs font-medium text-[color:var(--storefront-warning-text,#92400e)]">
                  Остаток уточняется
                </span>
                <span v-if="item.parent_cart_id" class="ml-2 inline-flex rounded-md border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] px-2 py-0.5 text-xs font-medium text-[color:var(--storefront-text,#1e40af)]">
                  Надстройка в комплекте
                </span>
              </h3>
              <p v-if="item.group_name" class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
                Комплектация: {{ item.group_name }}
              </p>
              <div v-if="item.parent_cart_id" class="mt-2 flex flex-wrap items-center gap-2 text-sm text-[color:var(--storefront-text,#1e3a8a)]">
                <span>Надстройка для: <strong>{{ item.parent_title || 'базовой техники' }}</strong></span>
                <button
                  type="button"
                  class="storefront-action-secondary min-h-9 rounded-md border border-[color:var(--storefront-primary-border,#bfdbfe)] bg-[color:rgb(var(--storefront-primary-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 text-xs font-semibold text-[color:var(--storefront-primary-foreground,#1e40af)] hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#2563eb)]"
                  @click="emit('detach', item.cart_id)"
                >
                  Отделить от комплекта
                </button>
              </div>
              <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                {{ colorYearLine }}
              </p>
<!--              TODO вспомнить надо убрать или добавить этот вин-->
<!--              <p v-if="item.vin" class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)] font-mono">-->
<!--                VIN: {{ item.vin }}-->
<!--              </p>-->
            </div>
          </div>

          <div v-if="discountSummary" class="mt-3 rounded-lg border border-[color:var(--storefront-success-border,#bbf7d0)] bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/0.8)] px-3 py-2">
            <p class="text-sm font-medium text-[color:var(--storefront-success-text,#14532d)]">
              Выгода: −{{ formatPrice(discountSummary.amount) }}
              <span class="text-[color:var(--storefront-success-text,#15803d)]">({{ discountSummary.percent }}%)</span>
            </p>
            <p class="mt-0.5 text-xs text-[color:var(--storefront-success-text,#166534)]">
              Цена в каталоге: {{ formatPrice(discountSummary.basePrice) }}
            </p>
          </div>

          <div v-if="seDiscountSummary" class="mt-3 rounded-lg border border-[color:var(--storefront-success-border,#bbf7d0)] bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/0.8)] px-3 py-2">
            <p class="text-sm font-medium text-[color:var(--storefront-success-text,#14532d)]">
              Выгода: −{{ formatPrice(seDiscountSummary.amount) }}
              <span class="text-[color:var(--storefront-success-text,#15803d)]">({{ seDiscountSummary.percent }}%)</span>
            </p>
            <p class="mt-0.5 text-xs text-[color:var(--storefront-success-text,#166534)]">
              Цена с выгодой: {{ formatPrice(seDiscountSummary.discountedPrice) }}
            </p>
          </div>
        </div>

        <!-- Количество и цена -->
        <div class="cart-quantity-price-grid">
          <div>
            <label :for="`cart-quantity-${item.cart_id}`" class="mb-2 block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Количество ТС</label>
            <div class="cart-quantity-control">
            <input
              :id="`cart-quantity-${item.cart_id}`"
              :data-testid="`cart-item-${item.cart_id}-quantity`"
              :aria-describedby="item.quantity_editable ? `cart-stock-${item.cart_id}` : undefined"
              type="number"
              inputmode="numeric"
              :value="localQuantity"
              @input="onQuantityInput"
              @change="updateQuantity"
              min="1"
              step="1"
              :max="quantityMax"
              :disabled="overstockPending || !item.quantity_editable || (!item.allow_overstock && (maxQuantity === undefined || maxQuantity === 0))"
              class="storefront-control cart-quantity-input"
            >
            <span class="cart-quantity-unit" aria-hidden="true">шт.</span>
            <span :id="`cart-stock-${item.cart_id}`" v-if="item.quantity_editable" class="cart-quantity-stock">
              <template v-if="maxQuantity !== undefined">На складе: <span class="font-medium tabular-nums">{{ maxQuantity }} шт.</span></template>
              <template v-else>Остаток уточняется</template>
            </span>
            </div>
            <button v-if="canToggleOverstock" type="button"
              class="mt-2 block whitespace-nowrap text-left text-sm font-medium underline underline-offset-4 text-[color:var(--storefront-text,#1d4ed8)] focus-visible:outline focus-visible:outline-2"
              :aria-pressed="Boolean(item.allow_overstock)" :disabled="overstockPending" :aria-busy="overstockPending" @click="toggleOverstock">
              {{ item.allow_overstock ? 'Ограничить наличием' : 'Указать больше доступного' }}
            </button>
            <p v-if="item.ref.type === 'vehicle' && item.allow_overstock" class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">Количество сверх наличия согласует поставщик</p>
            <p v-else-if="item.ref.type === 'special_equipment' && item.allow_overstock && item.quantity > (item.available_count ?? 0)" class="mt-1 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
              Сверх наличия: {{ item.quantity - (item.available_count ?? 0) }} шт. — дилер увидит запрос, в расчёт и заявку эти единицы не входят.
            </p>
          </div>
          <div>
            <label :for="`cart-price-${item.cart_id}`" class="mb-2 block text-sm font-medium text-[color:var(--storefront-label,#374151)]" v-if="item.price_editable">Ваша цена, шт. ₽</label>
            <label :for="`cart-price-${item.cart_id}`" class="mb-2 block text-sm font-medium text-[color:var(--storefront-label,#374151)]" v-else>{{ priceFieldLabel }}</label>
            <input 
              :id="`cart-price-${item.cart_id}`"
              :data-testid="`cart-item-${item.cart_id}-price`"
              type="text"
              :value="formattedPrice"
              @input="onPriceInput"
              @blur="updatePrice"
              :disabled="!item.price_editable"
              placeholder="0"
              class="storefront-control h-12 w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg text-sm text-[color:var(--storefront-text,#111827)] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] disabled:bg-[color:rgb(var(--storefront-disabled-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
            >
          </div>
        </div>

        <!-- Расчёт и доп. опции -->
        <div class="max-w-md space-y-2">
          <button
            type="button"
            @click="$emit('open-calculation')"
            class="storefront-action-ghost inline-flex w-full sm:w-auto justify-center py-2.5 px-4 text-sm font-medium rounded-lg bg-[color:rgb(var(--storefront-secondary-rgb,240_249_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-secondary-foreground,#1d4ed8)] border border-[color:var(--storefront-secondary-border,#bae6fd)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,224_242_254)/var(--tw-bg-opacity,1))] hover:border-[color:var(--storefront-secondary-hover-border,#7dd3fc)] transition-colors"
          >
            {{ calculationButtonLabel }}
          </button>

          <div class="relative" :data-testid="`cart-item-${item.cart_id}-equipment-dropdown`">
            <SearchableDropdown
              v-model="selectedEquipmentCodes"
              :items="equipmentDropdownItems"
              label-key="equipment_display_name"
              value-key="equipment_code"
              placeholder="Выберите доп. оборудование"
              multiple
              show-select-all
              :searchable="false"
              :allow-clear="false"
            />
            <span v-if="selectedEquipmentCount > 0" class="absolute -right-2 -top-2 z-10 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-1.5 text-xs font-semibold text-[color:var(--storefront-text,#ffffff)]">
              {{ selectedEquipmentCount }}
            </span>
          </div>

          <div class="relative" :data-testid="`cart-item-${item.cart_id}-service-dropdown`">
            <SearchableDropdown
              v-model="selectedServiceCodes"
              :items="serviceDropdownItems"
              label-key="service_display_name"
              value-key="service_code"
              placeholder="Выберите доп. услуги"
              multiple
              show-select-all
              :searchable="false"
              :allow-clear="false"
            />
            <span v-if="selectedServiceCount > 0" class="absolute -right-2 -top-2 z-10 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-1.5 text-xs font-semibold text-[color:var(--storefront-text,#ffffff)]">
              {{ selectedServiceCount }}
            </span>
          </div>
        </div>

        <!-- Комментарий -->
        <div>
          <textarea 
            :data-testid="`cart-item-${item.cart_id}-comment`"
            v-model="localComment"
            @blur="updateComment"
            placeholder="Комментарий к транспортному средству..."
            rows="2"
            class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg text-sm text-[color:var(--storefront-text,#111827)] focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)] resize-none placeholder-[var(--storefront-placeholder,#9ca3af)]"
          />
        </div>

        <!-- Подробнее | Удалить -->
        <div class="flex items-center justify-between pt-1 border-t border-[color:var(--storefront-border,#f3f4f6)]">
          <button 
            v-if="item.detail_url"
            type="button"
            @click="viewDetails"
            class="storefront-action-ghost text-sm font-medium text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
          >
            Подробнее
          </button>
          <button 
            type="button"
            @click="removeItem"
            class="storefront-action-ghost text-sm font-medium text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)]"
          >
            Удалить
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CommerceCartLine } from '~/features/commerce/cartProjection'
import { formatCommerceRequestPrice } from '~/features/commerce/requestPrice'
import type { CommerceItemRef } from '~/features/commerce/types'
import { selectedSupportProgramsForVehicle } from '~/features/cart/supportProgramCatalog'
import type { CartSupportProgramDetail } from '~/features/cart/types'
import type { UUID } from '~/types/ids'
import { useCartSupportSelection } from '~/features/cart/composables/useCartSupportSelection'
import { getVehicleDiscountSummary, getCommerceLineDiscountSummary } from '~/utils/vehicleDiscount'
import type {
  AdditionalEquipmentCatalogItem,
  AdditionalServiceCatalogItem,
} from '~/utils/additionalOptionsApi'

const props = withDefaults(defineProps<{
  item: CommerceCartLine
  unavailableStatus?: string
  maxQuantity?: number
  equipmentCatalog?: AdditionalEquipmentCatalogItem[]
  serviceCatalog?: AdditionalServiceCatalogItem[]
  calculationSupportPrograms?: readonly CartSupportProgramDetail[]
}>(), {
  unavailableStatus: '',
  equipmentCatalog: () => [],
  serviceCatalog: () => [],
  calculationSupportPrograms: () => [],
})

const emit = defineEmits<{
  (e: 'update-selection', item: CommerceItemRef, isSelected: boolean, cartItemId: UUID): void
  (e: 'remove', item: CommerceItemRef, cartItemId: UUID): void
  (e: 'detach', cartItemId: UUID): void
  (e: 'update-quantity', item: CommerceItemRef, quantity: number, cartItemId: UUID, allowOverstock?: boolean, onSettled?: () => void): void
  (e: 'update-price', item: CommerceItemRef, price: number | null, cartItemId: UUID): void
  (e: 'update-comment', item: CommerceItemRef, comment: string, cartItemId: UUID): void
  (e: 'update-additional-options', item: CommerceItemRef, payload: {
    equipments: Array<{ equipment_code: string; price?: number | null }>
    services: Array<{ service_code: string; price?: number | null }>
  }, cartItemId: UUID): void
  (e: 'open-calculation'): void
}>()

const router = useRouter()
const { formatPrice } = useFormatPrice()
const supportSelection = useCartSupportSelection()
const itemTitle = computed(() => `${props.item.mark_name} ${props.item.model_name}`.trim())
const quantityMax = computed(() => {
  if (props.item.ref.type === 'vehicle' && props.item.allow_overstock) {
    return 2147483647
  }
  if (props.item.ref.type === 'special_equipment' && props.item.allow_overstock) {
    return 1000
  }
  return props.maxQuantity === undefined ? undefined : Math.max(1, props.maxQuantity)
})
const canToggleOverstock = computed(() => {
  if (props.item.ref.type === 'vehicle') return props.item.quantity_editable
  if (props.item.ref.type === 'special_equipment') {
    return !props.item.parent_cart_id
      && props.item.quantity_editable
      && (props.item.available_count ?? 0) >= 1
  }
  return false
})
const discountSummary = computed(() => {
  if (props.item.ref.type !== 'vehicle') return null
  if (props.item.price_on_request) return null
  return getVehicleDiscountSummary(props.item.base_price, props.item.discount_price)
})
const seDiscountSummary = computed(() => {
  if (props.item.ref.type !== 'special_equipment') return null
  return getCommerceLineDiscountSummary(props.item)
})
const selectedSupportPrograms = computed(() => {
  if (props.item.ref.type !== 'vehicle') return []
  return selectedSupportProgramsForVehicle(
    props.item.ref.id,
    supportSelection.getSelectionForVehicle(props.item.ref.id).selected_support_ids,
    props.item.applicable_support_programs || [],
    props.calculationSupportPrograms,
  )
})
const selectedSupportProgramNames = computed(() =>
  selectedSupportPrograms.value.map(program => program.name).filter(Boolean),
)

const calculationButtonLabel = computed(() => {
  return selectedSupportProgramNames.value.length
    ? `Посмотреть расчет с поддержкой: ${selectedSupportProgramNames.value.join(', ')}`
    : 'Посмотреть расчет'
})

const vehicleColorName = computed(() => {
  return props.item.color || ''
})

const isModelOrder = computed(() => {
  return Boolean(props.item.is_model_order)
})

const colorYearLine = computed(() => {
  const color = vehicleColorName.value
  const y = props.item.year
  if (props.item.ref.type === 'special_equipment') {
    if (y && color) return `${y} | ${color}`
    if (y) return String(y)
    if (color) return color
    return 'Спецтехника'
  }
  if (color && y) return `${color} | ${y}`
  if (y) return String(y)
  return color || (props.item.ref.type === 'vehicle' ? 'Не указан' : 'Спецтехника')
})

const viewDetails = () => {
  if (props.item.detail_url) router.push(props.item.detail_url)
}

const removeItem = () => {
  if (confirm('Удалить транспортное средство из корзины?')) {
    emit('remove', props.item.ref, props.item.cart_id)
  }
}

const localQuantity = ref(props.item.quantity || 1)
const overstockPending = ref(false)
const getInitialPrice = () => {
  if (props.item.custom_price !== null && props.item.custom_price !== undefined) {
    return props.item.custom_price
  }
  if (props.item.base_price && props.item.base_price > 0) {
    return props.item.base_price
  }
  return 0
}
const localPrice = ref<number>(getInitialPrice())
const localComment = ref<string>(props.item.comment || '')

type EquipmentSelection = { equipment_code: string; price?: number | null }
type ServiceSelection = { service_code: string; price?: number | null }

const selectedEquipments = computed<EquipmentSelection[]>(() =>
  (props.item.equipments || []).filter(
    (option): option is EquipmentSelection => typeof option.equipment_code === 'string'
  )
)
const selectedServices = computed<ServiceSelection[]>(() =>
  (props.item.services || []).filter(
    (option): option is ServiceSelection => typeof option.service_code === 'string'
  )
)
const selectedEquipmentCount = computed(() => selectedEquipments.value.length)
const selectedServiceCount = computed(() => selectedServices.value.length)
const equipmentDropdownItems = computed(() => props.equipmentCatalog as Array<{ equipment_code: string; equipment_display_name: string }>)
const serviceDropdownItems = computed(() => props.serviceCatalog as Array<{ service_code: string; service_display_name: string }>)

const selectedEquipmentCodes = computed<string[]>({
  get: () => selectedEquipments.value.map(option => option.equipment_code),
  set: (codes) => {
    emitAdditionalOptions(
      codes.map(code => selectedEquipments.value.find(option => option.equipment_code === code) || { equipment_code: code, price: 0 }),
      selectedServices.value
    )
  }
})

const selectedServiceCodes = computed<string[]>({
  get: () => selectedServices.value.map(option => option.service_code),
  set: (codes) => {
    emitAdditionalOptions(
      selectedEquipments.value,
      codes.map(code => selectedServices.value.find(option => option.service_code === code) || { service_code: code, price: 0 })
    )
  }
})

const formattedPrice = computed(() => {
  if (props.item.price_on_request) {
    return formatCommerceRequestPrice({
      price: props.item.price_known === false ? null : props.item.base_price,
      price_from: props.item.price_from ?? null,
      price_on_request: true,
    })
  }
  if (localPrice.value === null || localPrice.value === undefined) {
    return '0'
  }
  return new Intl.NumberFormat('ru-RU').format(localPrice.value)
})
const priceFieldLabel = computed(() => {
  if (!props.item.price_on_request) return 'Цена, шт. ₽'
  return props.item.price_known === false ? 'Цена по запросу' : 'Цена от, шт.'
})

const onPriceInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  const rawValue = input.value.replace(/\s/g, '').replace(/[^\d]/g, '')
  const numValue = rawValue ? parseInt(rawValue, 10) : 0
  localPrice.value = numValue
  input.value = new Intl.NumberFormat('ru-RU').format(numValue)
}

const normalizeQuantity = (value: number) =>
  Math.min(quantityMax.value ?? Number.MAX_SAFE_INTEGER, Math.max(1, Number.isFinite(value) ? Math.trunc(value) : 1))

const onQuantityInput = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (overstockPending.value) { input.value = String(localQuantity.value); return }
  localQuantity.value = normalizeQuantity(input.valueAsNumber)
  // Rewrite even when the normalized value is unchanged, so invalid text never remains visible.
  input.value = String(localQuantity.value)
}

const updateQuantity = () => {
  if (overstockPending.value || !props.item.quantity_editable) return
  localQuantity.value = normalizeQuantity(localQuantity.value)
  overstockPending.value = true
  emit('update-quantity', props.item.ref, localQuantity.value, props.item.cart_id, props.item.allow_overstock === true, () => {
    overstockPending.value = false
    localQuantity.value = props.item.quantity
  })
}

const toggleOverstock = () => {
  if (overstockPending.value) return
  const allow = !props.item.allow_overstock
  if (!allow && (props.maxQuantity === undefined || props.maxQuantity === 0)) return
  const maxAvailable = props.item.ref.type === 'special_equipment'
    ? (props.item.available_count ?? props.maxQuantity ?? 1)
    : (props.maxQuantity ?? 1)
  const quantity = allow ? localQuantity.value : Math.min(localQuantity.value, Math.max(1, maxAvailable))
  localQuantity.value = quantity
  overstockPending.value = true
  emit('update-quantity', props.item.ref, quantity, props.item.cart_id, allow, () => {
    overstockPending.value = false
    localQuantity.value = props.item.quantity
  })
}
watch(() => props.item.quantity, (quantity) => { localQuantity.value = quantity })

const updatePrice = () => {
  if (!props.item.price_editable) return
  emit('update-price', props.item.ref, localPrice.value, props.item.cart_id)
}

const updateComment = () => {
  emit('update-comment', props.item.ref, localComment.value, props.item.cart_id)
}

const emitAdditionalOptions = (
  equipments = selectedEquipments.value,
  services = selectedServices.value
) => {
  emit('update-additional-options', props.item.ref, {
    equipments,
    services,
  }, props.item.cart_id)
}

// Clamp quantity when maxQuantity changes (e.g. after available counts loaded)
watch(() => props.maxQuantity, (max) => {
  if (!props.item.allow_overstock && max !== undefined && localQuantity.value > Math.max(1, max)) {
    localQuantity.value = normalizeQuantity(localQuantity.value)
    updateQuantity()
  }
}, { immediate: true })

</script>

<style scoped>
.cart-quantity-price-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: 16px;
  max-width: 640px;
}

.cart-quantity-control {
  display: flex;
  align-items: center;
  height: 48px;
  border: 1px solid var(--storefront-input-border, var(--storefront-border, #d1d5db));
  border-radius: 8px;
  background: var(--storefront-input, rgb(var(--storefront-surface-rgb, 255 255 255)));
}

.cart-quantity-control:focus-within {
  outline: 2px solid var(--storefront-focus, #3b82f6);
  outline-offset: 1px;
}

.cart-quantity-control .cart-quantity-input:focus {
  outline: none;
}

.cart-quantity-input {
  flex: 1;
  min-width: 0;
  width: 100%;
  height: 100%;
  padding: 0 12px;
  border: 0;
  border-radius: 8px 0 0 8px;
  background: transparent;
  color: var(--storefront-text, #111827);
  font-size: 16px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  appearance: textfield;
  -moz-appearance: textfield;
}

.cart-quantity-input::-webkit-inner-spin-button,
.cart-quantity-input::-webkit-outer-spin-button {
  margin: 0;
  -webkit-appearance: none;
}

.cart-quantity-input:disabled {
  background: rgb(var(--storefront-disabled-rgb, 249 250 251));
}

.cart-quantity-unit,
.cart-quantity-stock {
  flex-shrink: 0;
  color: var(--storefront-text-muted, #6b7280);
  font-size: 14px;
  white-space: nowrap;
}

.cart-quantity-unit {
  padding-right: 12px;
}

.cart-quantity-stock {
  padding: 0 12px;
  border-left: 1px solid var(--storefront-border, #d1d5db);
}
</style>
