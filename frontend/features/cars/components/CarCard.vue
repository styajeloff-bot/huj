<template>
  <div data-storefront-block="cars.card" class="card storefront-shadow-md bg-storefront-surface text-storefront-text hover:storefront-shadow-lg transition-shadow duration-200 relative flex flex-col h-full">
    <!-- Clickable overlay covering the entire card except action buttons -->
    <NuxtLink :to="publicRoute('/special-equipment')"
      class="absolute inset-0 z-10 cursor-pointer" aria-label="Открыть детали"></NuxtLink>

    <!-- Image section -->
    <div class="relative flex-shrink-0 bg-storefront-image">
      <img :src="getCarImage(car)" :alt="`${car.mark_name} ${car.model_name}`"
        class="w-full h-48 object-contain rounded-lg" onerror="this.src='/images/car-placeholder.png'">
      <div v-if="car.is_restyle"
        class="absolute top-2 left-2 bg-storefront-success text-storefront-success-text px-2 py-1 rounded text-xs font-medium z-20">
        {{ car.generation_name ?? ' ' }}
      </div>
      <div v-if="myOrderStatus"
        class="absolute top-2 left-2 px-2 py-1 rounded text-xs font-semibold z-20 storefront-shadow-sm"
        :class="myOrderStatus === 'reserved'
          ? 'bg-storefront-warning text-storefront-warning-text'
          : 'bg-storefront-success text-storefront-success-text'"
      >
        {{ myOrderStatus === 'reserved' ? 'У вас в резерве' : 'Ваша покупка' }}
      </div>

      <!-- Special offer and distributor support badges -->
      <div
        v-if="hasSpecialOffer || carSupportPrograms.length"
        class="absolute inset-x-2 top-10 z-20 flex flex-col items-end gap-1"
      >
        <div
          v-if="hasSpecialOffer"
          class="bg-storefront-success text-storefront-success-text px-2 py-1 rounded text-xs font-medium"
        >
          Спецпредложение
        </div>
        <RotatingSupportBadge
          v-if="carSupportPrograms.length"
          :programs="carSupportPrograms"
          shape="badge"
          tooltip-align="right"
          :rotation-ms="5_000"
        />
      </div>

      <!-- Favorite button -->
      <button
        v-if="!authStore.isDealer"
        @click.stop.prevent="toggleFavorite"
        :disabled="favoriteLoading"
        :aria-pressed="inFavorites"
        class="absolute top-2 right-2 z-20 p-1.5 rounded-full transition-all duration-200 storefront-shadow-sm"
        :class="inFavorites
          ? 'storefront-favorite bg-storefront-favorite text-storefront-favorite-icon hover:bg-storefront-favorite-hover'
          : 'storefront-action-ghost bg-storefront-surface/80 text-storefront-text-muted hover:bg-storefront-secondary-hover hover:text-storefront-favorite-icon'"
        :title="inFavorites ? 'Убрать из избранного' : 'Добавить в избранное'"
      >
        <svg
          v-if="favoriteLoading"
          class="w-4 h-4 animate-spin text-storefront-icon"
          xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
        >
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <svg
          v-else
          class="w-4 h-4 transition-all duration-200 text-storefront-icon"
          :fill="inFavorites ? 'currentColor' : 'none'"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
        </svg>
      </button>
    </div>

    <!-- Content section -->
    <div class="flex flex-col flex-grow pt-4">
      <!-- Title -->
      <div class="mb-3">
        <h3 class="text-lg font-semibold text-storefront-title leading-tight">
          {{ car.mark_name }} {{ car.model_name }}
        </h3>
        <p class="text-sm text-storefront-text-muted mt-0.5 line-clamp-1">
          {{ displaySubtitle }}
        </p>
      </div>

      <!-- Specs grid - compact 2-column layout -->
      <div class="grid grid-cols-2 gap-x-3 gap-y-1.5 bg-storefront-surface-muted text-xs text-storefront-value mb-3">
        <div v-if="car.horse_power" class="flex items-center gap-1.5 min-w-0">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-storefront-icon-muted flex-shrink-0">
            <path d="M7.996 5C12 4.99 14.333 4.99 15 5v3h-2v1h2l1 2h1l1-2h2v10h-1.983L17 17h-1l-1 2H7.996L7 17H4v-7h3V9h3.001V8H7.996V5Z"/>
          </svg>
          <span class="truncate">{{ car.horse_power }} л.с.</span>
        </div>
        <div v-if="car.category" class="flex items-center gap-1.5 min-w-0">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-storefront-icon-muted flex-shrink-0">
            <path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v3H4V5Zm0 5h16v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-9Zm4 3v2h8v-2H8Z"/>
          </svg>
          <span class="truncate">{{ car.category }}</span>
        </div>
        <div v-if="car.fuel_type || car.engine_type" class="flex items-center gap-1.5 min-w-0">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-storefront-icon-muted flex-shrink-0">
            <path d="M19 22V4c0-1.1-.9-2-2-2H7c-1.1 0-2 .9-2 2v18h14zM9 12V6h6v6H9z"/>
          </svg>
          <span class="truncate">{{ car.fuel_type || car.engine_type }}</span>
        </div>
        <div v-if="car.drive" class="flex items-center gap-1.5 min-w-0">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-storefront-icon-muted flex-shrink-0">
            <path d="M18.696 8.825V3h-4.41v2.326H9.41V3H5v5.825h4.409V6.499h1.852v11.002H9.409v-2.326H5V21h4.409v-2.326h4.878V21h4.409v-5.825h-4.41V17.5h-1.851v-11h1.852v2.325h4.409Z"/>
          </svg>
          <span class="truncate">{{ formatDrive(car.drive) }}</span>
        </div>
        <div v-if="car.transmission" class="flex items-center gap-1.5 min-w-0">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-storefront-icon-muted flex-shrink-0">
            <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM7 7h3.8v1H9.6v2h1.2v1H9.6v2h1.2v1H9.6v2h1.2v1H7v-1h1.2v-2H7v-1h1.2v-2H7v-1h1.2V8H7V7Z"/>
          </svg>
          <span class="truncate">{{ formatTransmission(car.transmission) }}</span>
        </div>
        <div v-if="car.engine_capacity" class="flex items-center gap-1.5 min-w-0">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-storefront-icon-muted flex-shrink-0">
            <path d="M5 21V3h14v18H5zm2-2h10V5H7v14zm3-4h4v-4h-4v4z"/>
          </svg>
          <span class="truncate">{{ car.engine_capacity }} л</span>
        </div>
        <div v-if="car.configuration_name" class="flex items-center gap-1.5 min-w-0">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-3.5 h-3.5 text-storefront-icon-muted flex-shrink-0">
            <path d="M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z"/>
          </svg>
          <span class="truncate">{{ car.configuration_name }}</span>
        </div>
      </div>

      <!-- Color -->
      <div v-if="car.color" class="flex items-center gap-2 text-xs text-storefront-text-muted mb-3">
        <span
          class="w-4 h-4 rounded-full border border-storefront-border flex-shrink-0"
          :style="colorCode ? { backgroundColor: colorCode } : undefined"
        ></span>
        <span class="truncate">{{ car.color }}</span>
      </div>

      <!-- Warehouse info - full display -->
      <div v-if="hasWarehouseInfo" class="bg-storefront-surface-muted rounded-lg p-2.5 mb-3 text-xs">
        <div class="flex items-start gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-4 h-4 text-storefront-icon-muted flex-shrink-0 mt-0.5">
            <path fill-rule="evenodd" d="M11.54 22.351l.07.04.028.016a.76.76 0 00.723 0l.028-.015.071-.041a16.975 16.975 0 001.144-.742 19.58 19.58 0 002.683-2.282c1.944-1.99 3.963-4.98 3.963-8.827a8.25 8.25 0 00-16.5 0c0 3.846 2.02 6.837 3.963 8.827a19.58 19.58 0 002.682 2.282 16.975 16.975 0 001.145.742zM12 13.5a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd" />
          </svg>
          <div class="min-w-0 flex-1">
            <div v-if="car.warehouse_address && car.warehouse_city_name" class="text-storefront-text truncate">
              {{ car.warehouse_city_name }}, {{ car.warehouse_address }}
            </div>
            <div v-if="car.warehouse_company_name" class="text-storefront-text-muted truncate">
              {{ car.warehouse_company_name }}
            </div>
          </div>
        </div>
      </div>

      <!-- Spacer to push buttons to bottom -->
      <div class="flex-grow"></div>

      <!-- Price (left) + Stock count (right) -->
      <div class="flex items-end justify-between mb-3">
        <div v-if="hasVehicleSupportPreview">
          <p class="text-sm text-storefront-text-muted line-through">
            {{ formatPrice(supportPreviewBasePrice) }}
          </p>
          <p class="text-lg font-bold text-storefront-price">
            {{ formatPrice(supportPreviewDisplayPrice) }}
          </p>
        </div>
        <div v-else-if="hasSpecialOffer">
          <p class="text-sm text-storefront-text-muted line-through">
            {{ formatPrice(car.base_price || car.price_from) }}
          </p>
          <p class="text-lg font-bold text-storefront-price">
            {{ formatPrice(car.discount_price) }}
          </p>
        </div>
        <div v-else-if="car.base_price || car.price_from">
          <p class="text-lg font-bold text-storefront-price">
            {{ formatPrice(car.base_price || car.price_from) }}
          </p>
        </div>
        <div v-if="showStockCount && car.available_count" class="flex items-center gap-1 text-sm text-storefront-text-muted">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-4 h-4 text-storefront-icon-muted">
            <path d="M2 20V8l10-6 10 6v12H14v-6h-4v6H2zm2-2h4v-6h8v6h4V9l-8-4.8L4 9v9z"/>
          </svg>
          <span class="font-medium">{{ car.available_count }} шт.</span>
        </div>
      </div>

      <!-- Action buttons - always at bottom -->
      <div class="pt-3 border-t border-storefront-border relative z-20">
        <div class="grid grid-cols-2 gap-2">
          <NuxtLink :to="publicRoute('/special-equipment')"
            class="btn-secondary text-center text-sm py-2">
            Подробнее
          </NuxtLink>

          <button v-if="showCartButton" @click.stop="toggleCart" :disabled="cartLoading || !canUseCart"
            :class="[cartButtonClass, 'text-sm py-2']" :title="!canUseCart ? 'Войдите в систему для добавления в корзину' : ''">
            <span v-if="cartLoading">...</span>
            <span v-else-if="!canUseCart">Войти</span>
            <span v-else-if="inCart">Убрать</span>
            <span v-else>В корзину</span>
          </button>

          <button v-else @click.stop="$emit('apply', car)" class="btn-primary text-sm py-2">
            Оформить
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'
import { getColorCode } from '~/utils/colorCode'
import type { UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'
import RotatingSupportBadge from '~/components/support/RotatingSupportBadge.vue'
import { normalizeSupportPrograms } from '~/types/support'
const props = defineProps({
  car: {
    type: Object,
    required: true
  },
  showCartButton: {
    type: Boolean,
    default: true
  },
  showCalculator: {
    type: Boolean,
    default: true
  },
  showStockCount: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['apply', 'calculator'])

const authStore = useAuthStore()
const cartStore = useCartStore()
const exchangeCartStore = useExchangeCartStore()
const favoritesStore = useFavoritesStore()
const purchasesStore = usePurchasesStore()
const toast = useToast()
const { publicRoute } = useStorefront()

// Reactive state
const cartLoading = ref(false)
const inCart = ref(false)
const favoriteLoading = ref(false)
const inFavorites = ref(false)

// Check if current user has an active order for this vehicle
const myOrderStatus = computed(() => {
  if (!authStore.isAuthenticated) return ''
  const vehicleId = props.car.vehicle_id as UUID | undefined
  if (!vehicleId) return ''
  return purchasesStore.isMyReservedVehicle(vehicleId)
})

// Computed
const hasWarehouseInfo = computed(() => {
  return props.car?.warehouse_address || props.car?.warehouse_city_name || props.car?.warehouse_brand || props.car?.warehouse_company_name
})

const canUseCart = computed(() => {
  // Allow cart for all users (authenticated and guests)
  return true
})

const cartButtonClass = computed(() => {
  const baseClass = 'btn text-sm font-medium transition-colors duration-200'
  if (!canUseCart.value) {
    return `${baseClass} bg-storefront-disabled text-storefront-disabled-foreground border border-storefront-disabled-border cursor-not-allowed`
  }
  if (inCart.value) {
    return `${baseClass} storefront-action-destructive bg-storefront-error text-storefront-error-text border border-storefront-error-border hover:bg-storefront-error-hover`
  }
  return `${baseClass} btn-primary`
})

// Methods
const { formatPrice } = useFormatPrice()

const carSupportPrograms = computed(() => normalizeSupportPrograms(props.car.applicable_support_programs))
const supportPreviewBasePrice = computed(() => Number(
  props.car.support_preview_base_price ?? props.car.base_price ?? props.car.price_from ?? 0,
))
const supportPreviewDisplayPrice = computed(() => Number(
  props.car.support_preview_display_price ?? supportPreviewBasePrice.value,
))
const hasVehicleSupportPreview = computed(() => (
  supportPreviewBasePrice.value > 0
  && supportPreviewDisplayPrice.value > 0
  && supportPreviewDisplayPrice.value < supportPreviewBasePrice.value
))

const hasSpecialOffer = computed(() => {
  const base = props.car.base_price || props.car.price_from
  const discount = props.car.discount_price
  if (!base || !discount) return false
  return Number(discount) < Number(base)
})

const displaySubtitle = computed(() => {
  const parts: string[] = []
  if (props.car.group_name) {
    parts.push(props.car.group_name)
  } else {
    const engine = `${props.car.engine_capacity || ''} ${props.car.transmission || ''} ${props.car.horse_power || ''}`.trim()
    if (engine) parts.push(engine)
  }
  if (props.car.configuration_name) parts.push(props.car.configuration_name)
  const year = props.car.vehicle_year || props.car.year
  if (year) parts.push(String(year))
  return parts.join(', ')
})

const formatDrive = (drive: string) => {
  if (!drive) return null
  const driveMap: Record<string, string> = {
    'FWD': 'Передний (FWD)',
    'RWD': 'Задний (RWD)',
    'AWD': 'Полный (AWD)',
    '4WD': 'Полный (4WD)',
    'передний': 'Передний (FWD)',
    'задний': 'Задний (RWD)',
    'полный': 'Полный (4WD)'
  }
  return driveMap[drive] || drive
}

const formatTransmission = (transmission: string) => {
  if (!transmission) return null
  const transMap: Record<string, string> = {
    'MT': 'МКПП',
    'AT': 'АКПП',
    'AMT': 'AMT',
    'CVT': 'Вариатор',
    'DCT': 'Робот',
    'механика': 'МКПП',
    'автомат': 'АКПП',
    'вариатор': 'Вариатор',
    'робот': 'Робот'
  }
  return transMap[transmission] || transmission
}

const getCarImage = (car: Record<string, unknown>) => {
  if (car.images && Array.isArray(car.images) && car.images.length > 0) {
    return vehicleImageUrl(car.images[0])
  }
  if (car.main_image) {
    return vehicleImageUrl(car.main_image)
  }
  return vehicleImageUrl(null)
}

const colorCode = computed(() => getColorCode(props.car.color))

const checkCartStatus = async () => {
  const vehicleId = props.car.vehicle_id as UUID | undefined
  if (!vehicleId) return

  try {
    if (authStore.isLeasingCompany) {
      inCart.value = exchangeCartStore.isInCart(vehicleId)
    } else if (authStore.isAuthenticated) {
      await cartStore.initialize()
      inCart.value = cartStore.isInCart(vehicleId)
    } else {
      // For guests, check local cart
      inCart.value = cartStore.isInCart(vehicleId)
    }
  } catch (error) {
    console.error('Error checking cart status:', error)
  }
}

const toggleCart = async () => {
  const vehicleId = props.car.vehicle_id as UUID | undefined
  if (cartLoading.value || !vehicleId) return

  cartLoading.value = true

  try {
    let result

    if (inCart.value) {
      if (authStore.isLeasingCompany) {
        await exchangeCartStore.removeByVehicleId(vehicleId)
        inCart.value = false
        return
      }
      result = await cartStore.removeFromCart(vehicleId)
      if (result.success) {
        inCart.value = false
      }
    } else {
      trackGoal('main_shopping_cart_enter')
      // Create car data for guest cart
      const carData = {
        modification_id: props.car.modification_id,
        vehicle_id: props.car.vehicle_id,
        configuration_id: props.car.configuration_id,
        mark_name: props.car.mark_name,
        mark_cyrillic: props.car.mark_cyrillic,
        model_name: props.car.model_name || props.car.model_cyrillic,
        model_cyrillic: props.car.model_cyrillic,
        configuration_name: props.car.configuration_name,
        group_name: props.car.group_name,
        body_type: props.car.body_type,
        engine_capacity: props.car.engine_capacity,
        fuel_type: props.car.fuel_type,
        base_price: props.car.base_price || props.car.price_from || 0,
        discount_price: props.car.discount_price,
        color: props.car.color,
        images: props.car.images,
        is_selected: true
      }

      if (authStore.isLeasingCompany) {
        const warehouseId = props.car.warehouse_id as UUID | undefined
        await exchangeCartStore.addItem(vehicleId, 1, warehouseId ?? null)
        inCart.value = true
        return
      }
      result = await cartStore.addToCart(vehicleId, carData)
      if (result.success) {
        inCart.value = true
      }
    }

  } catch (error) {
    console.error('Error toggling cart:', error)
    toast.error('Не удалось обновить корзину. Попробуйте ещё раз.')
  } finally {
    cartLoading.value = false
  }
}

const openCalculator = () => {
  emit('calculator', props.car)
}

const trackGoal = (goalName: string) => {
  if (typeof window !== 'undefined' && window.ym) {
    window.ym(103750838, 'reachGoal', goalName)
  }
}

// Favorites methods
const resolveCarId = (): string | undefined => {
  return props.car.vehicle_id as UUID | undefined
}

const checkFavoriteStatus = () => {
  const carId = resolveCarId()
  if (!carId) return
  if (authStore.isAuthenticated) {
    inFavorites.value = favoritesStore.isInFavorites(carId)
  } else {
    inFavorites.value = favoritesStore.isInGuestFavorites(carId)
  }
}

const toggleFavorite = async () => {
  if (favoriteLoading.value) return
  const carId = resolveCarId()
  if (!carId) return

  if (!authStore.isAuthenticated) {
    if (inFavorites.value) {
      favoritesStore.removeFromGuestFavorites(carId)
      inFavorites.value = false
    } else {
      favoritesStore.addToGuestFavorites(carId)
      inFavorites.value = true
    }
    return
  }

  favoriteLoading.value = true
  try {
    if (inFavorites.value) {
      const result = await favoritesStore.removeFromFavorites(carId)
      if (result.success) inFavorites.value = false
    } else {
      const result = await favoritesStore.addToFavorites(carId)
      if (result.success) inFavorites.value = true
    }
  } finally {
    favoriteLoading.value = false
  }
}

// Initialize cart status on mount
onMounted(() => {
  checkCartStatus()
  checkFavoriteStatus()
})

// Watch for auth changes
watch(() => authStore.isAuthenticated, () => {
  checkCartStatus()
  checkFavoriteStatus()
})

// Watch for cart changes
watch(() => cartStore.items, () => {
  checkCartStatus()
}, { deep: true })

// Sync favorites state with store
watch(() => favoritesStore.items, () => {
  checkFavoriteStatus()
}, { deep: true })

watch(() => favoritesStore.guestIds, () => {
  if (!authStore.isAuthenticated) {
    checkFavoriteStatus()
  }
}, { deep: true })
</script>
