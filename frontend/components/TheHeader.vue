<template>
  <header
    class="fixed inset-x-0 top-0 z-50 bg-storefront-surface text-storefront-text"
  >
    <div data-storefront-block="header.contacts" class="block h-9 bg-[color:rgb(var(--storefront-background-rgb,2_6_23)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#ffffff)]">
      <div class="mx-auto flex h-full max-w-[1440px] items-center justify-end px-6 xl:px-8">
        <address class="flex h-full items-center gap-5 not-italic xl:gap-7" :aria-label="`Контакты ${storefrontLabel}`">
          <a
            :href="`tel:${contact_phone_href}`"
            class="inline-flex min-h-9 items-center gap-2 text-xs font-semibold text-[color:var(--storefront-link,#f1f5f9)] transition-colors duration-200 hover:text-[color:var(--storefront-link-hover,#ffffff)] focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#ffffff)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--storefront-focus,#020617)]"
            :aria-label="`Позвонить: ${contact_phone}`"
          >
            <svg class="text-[color:var(--storefront-icon,inherit)] h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M3 5a2 2 0 0 1 2-2h3.28a1 1 0 0 1 .95.68l1.5 4.5a1 1 0 0 1-.5 1.2l-2.26 1.14a11.04 11.04 0 0 0 5.51 5.51l1.14-2.26a1 1 0 0 1 1.2-.5l4.5 1.5a1 1 0 0 1 .68.95V19a2 2 0 0 1-2 2h-1C9.72 21 3 14.28 3 6V5Z" />
            </svg>
            <span>{{ contact_phone }}</span>
          </a>
          <a
            :href="`mailto:${contact_email}`"
            class="inline-flex min-h-9 items-center gap-2 text-xs font-semibold text-[color:var(--storefront-link,#f1f5f9)] transition-colors duration-200 hover:text-[color:var(--storefront-link-hover,#ffffff)] focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#ffffff)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--storefront-focus,#020617)]"
            :aria-label="`Написать на ${contact_email}`"
          >
            <svg class="text-[color:var(--storefront-icon,inherit)] h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="m3 7 7.9 5.26a2 2 0 0 0 2.2 0L21 7m-16 12h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2Z" />
            </svg>
            <span>{{ contact_email }}</span>
          </a>
        </address>
      </div>
    </div>

    <nav data-storefront-block="header.navigation" class="border-b border-storefront-border bg-storefront-surface shadow-[0_8px_24px_rgb(var(--storefront-shadow-rgb,15_23_42)/0.08)]" aria-label="Основная навигация">
      <div class="mx-auto grid h-[76px] max-w-[1440px] grid-cols-[minmax(9.5rem,1fr)_auto_minmax(9.5rem,1fr)] items-center gap-4 px-5 xl:grid-cols-[minmax(11.5rem,1fr)_auto_minmax(11.5rem,1fr)] xl:gap-6 xl:px-8">
        <NuxtLink
          :to="publicRoute('/')"
          class="flex h-[50px] w-[154px] shrink-0 items-center rounded-storefront-control focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 xl:w-[184px]"
          :aria-label="`${storefrontLabel} — ${pageTitle(public_ui.home_page_key)}`"
        >
          <img
            :src="logo_url"
            :alt="storefrontLabel"
            class="max-h-[50px] max-w-full h-auto w-auto object-contain"
          >
        </NuxtLink>

        <div class="flex min-w-0 items-center justify-center gap-1 xl:gap-2">
          <NuxtLink
            v-if="public_ui.home_page_key === 'home'"
            :to="publicRoute('/')"
            class="header-nav-link"
            :class="{ 'header-nav-link--active': route.path === publicRoute('/') }"
            :aria-current="route.path === publicRoute('/') ? 'page' : undefined"
          >
            {{ pageTitle('home') }}
          </NuxtLink>
          <NuxtLink
            v-if="visibilityStore.isSectionVisible('public', 'about')"
            :to="publicNavigationRoute('about', '/about')"
            class="header-nav-link"
            :class="{ 'header-nav-link--active': route.path === publicRoute('/about') }"
            :aria-current="route.path === publicRoute('/about') ? 'page' : undefined"
          >
            {{ pageTitle('about') }}
          </NuxtLink>
          <NuxtLink
            v-if="visibilityStore.isSectionVisible('public', 'special_equipment_catalog')"
            :to="publicNavigationRoute('special_equipment_catalog', '/special-equipment')"
            class="header-nav-link"
            :class="{ 'header-nav-link--active': route.path.startsWith(publicRoute('/special-equipment')) }"
            :aria-current="route.path.startsWith(publicRoute('/special-equipment')) ? 'page' : undefined"
            @click="trackGoal('main_application')"
          >
            {{ pageTitle('special_equipment_catalog') }}
          </NuxtLink>
          <NuxtLink
            v-if="authHydrationReady && authStore.isAuthenticated"
            :to="accountRoute"
            class="header-nav-link"
            :class="{ 'header-nav-link--active': route.path === accountPath }"
            :aria-current="route.path === accountPath ? 'page' : undefined"
          >
            Личный кабинет
          </NuxtLink>
        </div>

        <div class="flex shrink-0 items-center justify-self-end gap-2">
          <ClientOnly>
            <template v-if="authStore.isAuthenticated">
              <div v-if="canUseClientCommerce" class="block">
                <FavoritesComponentsFavoritesBell
                  :additional-count="specialEquipmentFavoriteCount"
                  @open-auth-modal="openAuthModal()"
                />
              </div>
              <CartComponentsCartBell
                v-if="canUseClientCommerce || authStore.isLeasingCompany"
                :items="headerCartItems"
                :count="cartCount"
                :load-items="loadHeaderCartItems"
                :remove-item="removeHeaderCartItem"
                :clear-cart="clearHeaderCart"
              />
              <div class="block">
                <NotificationBell />
              </div>
              <div class="block">
                <UserDropdown />
              </div>
            </template>
            <template v-else>
              <div class="block">
                <FavoritesComponentsFavoritesBell
                  :additional-count="specialEquipmentFavoriteCount"
                  @open-auth-modal="openAuthModal()"
                />
              </div>
              <CartComponentsCartBell
                :items="headerCartItems"
                :count="cartCount"
                :load-items="loadHeaderCartItems"
                :remove-item="removeHeaderCartItem"
                :clear-cart="clearHeaderCart"
              />
              <button
                type="button"
                class="storefront-action-primary inline-flex min-h-11 items-center justify-center whitespace-nowrap rounded-storefront-control bg-storefront-primary px-4 text-sm font-bold text-storefront-primary-foreground transition-colors duration-200 hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2"
                @click="openAuthModal(true); trackGoal('main_enter')"
              >
                Войти
              </button>
            </template>
          </ClientOnly>

        </div>
      </div>
    </nav>

    <AuthModal
      v-if="showAuthModal"
      :redirect-to-account="redirectToAccount"
      @close="closeAuthModal"
      @authenticated="handleAuthentication"
    />
  </header>
</template>

<script setup lang="ts">
import AuthModal from '~/features/auth/components/AuthModal.vue'
import UserDropdown from '~/features/auth/components/UserDropdown.vue'
import { useAuthStore } from '~/features/auth/store/auth'
import { useHydrationReady } from '~/composables/useHydrationReady'
import { vehicleCommerceCartLine } from '~/features/cart/adapters/vehicleCommerceCartLine'
import type { CommerceCartLine } from '~/features/commerce/cartProjection'
import type { CommerceItemRef } from '~/features/commerce/types'
import type { UUID } from '~/types/ids'
import type { ExchangeCartItem } from '~/features/exchange/types'
import { specialEquipmentCommerceCartLine } from '~/features/specialEquipment/adapters/specialEquipmentCommerceCartLine'
import { totalCommerceShellCount } from '~/features/specialEquipment/composables/commerceShellAdapter'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import { useSpecialEquipmentCommerceShellStore } from '~/features/specialEquipment/store/commerceShell'
import NotificationBell from '~/components/ui/NotificationBell.vue'
import { useStorefront } from '~/features/storefront'
import { buildWorkspaceLocation } from '~/features/workspace/returnContext'

const authStore = useAuthStore()
const cartStore = useCartStore()
const exchangeCartStore = useExchangeCartStore()
const favoritesStore = useFavoritesStore()
const visibilityStore = useSectionVisibilityStore()
const specialEquipmentShell = useSpecialEquipmentCommerceShellStore()
const toast = useToast()
const route = useRoute()
const authHydrationReady = useHydrationReady()
const showAuthModal = ref(false)
const redirectToAccount = ref(false)
const vehicleCartCount = ref(0)
const canUseClientCommerce = computed(() =>
  !authStore.isAuthenticated || authStore.isClient || authStore.isDealer,
)
const {
  contact_email,
  contact_phone,
  contact_phone_href,
  logo_url,
  pageTitle,
  public_ui,
  publicRoute,
  slug,
} = useStorefront()
const storefrontLabel = computed(() => slug.value ? `Витрина ${slug.value}` : 'CarCraft Multileasing')
const publicNavigationRoute = (key: Parameters<typeof pageTitle>[0], path: string): string => (
  public_ui.value.home_page_key === key ? publicRoute('/') : publicRoute(path)
)
const accountRoute = computed(() => authStore.homeRoute.startsWith('/workspace')
  ? buildWorkspaceLocation(authStore.homeRoute, slug.value)
  : publicRoute(authStore.homeRoute))
const accountPath = computed(() => authStore.homeRoute.startsWith('/workspace')
  ? authStore.homeRoute
  : publicRoute(authStore.homeRoute))

const isSpecialEquipmentCatalogVisible = computed(() =>
  visibilityStore.isSectionVisible('public', 'special_equipment_catalog'),
)
const specialEquipmentFavoriteCount = computed(() =>
  isSpecialEquipmentCatalogVisible.value && canUseClientCommerce.value ? specialEquipmentShell.favoriteCount : 0,
)
const specialEquipmentCartCount = computed(() =>
  isSpecialEquipmentCatalogVisible.value && canUseClientCommerce.value
    ? specialEquipmentShell.cartCount
    : 0,
)
const cartCount = computed(() => totalCommerceShellCount([
  { kind: 'vehicle', count: vehicleCartCount.value },
  { kind: 'special_equipment', count: specialEquipmentCartCount.value },
]))

const exchangeCommerceCartLine = (item: ExchangeCartItem): CommerceCartLine =>
  vehicleCommerceCartLine({
    cart_id: item.id,
    vehicle_id: item.vehicle_id,
    mark_name: item.mark_name,
    model_name: item.model_name,
    base_price: item.base_price,
    discount_price: item.discount_price,
    is_selected: true,
    added_at: '',
    quantity: item.quantity,
    year: item.vehicle_year,
    color: item.color,
    images: item.images,
    configuration_name: item.configuration_name,
    group_name: item.group_name,
  })

const headerCartItems = computed<CommerceCartLine[]>(() => {
  const vehicleItems = authStore.isLeasingCompany
    ? exchangeCartStore.items.map(exchangeCommerceCartLine)
    : cartStore.items.map(vehicleCommerceCartLine)

  return [
    ...vehicleItems,
    ...(isSpecialEquipmentCatalogVisible.value && !authStore.isLeasingCompany
      ? specialEquipmentShell.cartItems.map(item => specialEquipmentCommerceCartLine(item, publicRoute))
      : []),
  ]
})

const openAuthModal = (toAccount = false) => {
  redirectToAccount.value = toAccount
  showAuthModal.value = true
}

const closeAuthModal = () => {
  showAuthModal.value = false
  redirectToAccount.value = false
}

const handleAuthentication = async () => {
  const destination = redirectToAccount.value ? accountRoute.value : null
  closeAuthModal()
  if (destination) sessionStorage.removeItem('redirectAfterLogin')
  try {
    if (canUseClientCommerce.value) {
      await Promise.all([
        favoritesStore.mergeGuestFavorites(),
        ...(isSpecialEquipmentCatalogVisible.value ? [specialEquipmentShell.mergeGuestState()] : []),
      ])
    }
  } finally {
    if (destination) await navigateTo(destination)
  }
}

const trackGoal = (goalName: string) => {
  if (typeof window !== 'undefined' && window.ym) {
    window.ym(103750838, 'reachGoal', goalName)
  }
}

const updateCartCount = async () => {
  if (authStore.isAuthenticated && authStore.isLeasingCompany) {
    vehicleCartCount.value = await exchangeCartStore.getCount()
  } else if (authStore.isAuthenticated && canUseClientCommerce.value && authStore.canCreateApplications) {
    vehicleCartCount.value = await cartStore.getCartCount()
  } else {
    vehicleCartCount.value = canUseClientCommerce.value ? cartStore.totalItems : 0
  }
}

const loadHeaderCartItems = async () => {
  if (!canUseClientCommerce.value && !authStore.isLeasingCompany) return
  const vehicleRequest = authStore.isLeasingCompany
    ? exchangeCartStore.fetchCart()
    : cartStore.fetchCart()

  const [vehicleResult] = await Promise.all([
    vehicleRequest,
    isSpecialEquipmentCatalogVisible.value && !authStore.isLeasingCompany
      ? specialEquipmentShell.loadCart({ force: true, resolveGuestProducts: true })
      : Promise.resolve(),
  ])

  if (
    vehicleResult
    && typeof vehicleResult === 'object'
    && 'success' in vehicleResult
    && vehicleResult.success === false
  ) {
    throw new Error('Не удалось загрузить корзину транспортных средств')
  }
  if (
    isSpecialEquipmentCatalogVisible.value
    && !authStore.isLeasingCompany
    && specialEquipmentShell.cartError
  ) {
    throw new Error(specialEquipmentShell.cartError)
  }

  vehicleCartCount.value = authStore.isLeasingCompany
    ? exchangeCartStore.count
    : cartStore.totalItems
}

const removeHeaderCartItem = async (item: CommerceItemRef, cartItemId?: UUID) => {
  if (item.type === 'special_equipment') {
    if (!cartItemId) throw new Error('Не удалось определить позицию корзины')
    await specialEquipmentShell.removeCartItem(cartItemId)
    return
  }

  if (authStore.isLeasingCompany) {
    await exchangeCartStore.removeByVehicleId(item.id)
    vehicleCartCount.value = exchangeCartStore.count
    return
  }

  const result = await cartStore.removeFromCart(item.id)
  if (!result.success) throw new Error(result.error || 'Не удалось удалить позицию из корзины')
  vehicleCartCount.value = cartStore.totalItems
}

const clearHeaderCart = async () => {
  const vehicleRequest = vehicleCartCount.value > 0
    ? authStore.isLeasingCompany
      ? exchangeCartStore.clearCart()
      : cartStore.clearCart()
    : Promise.resolve({ success: true } as const)
  const specialEquipmentRequest = isSpecialEquipmentCatalogVisible.value
    && !authStore.isLeasingCompany
    && specialEquipmentShell.cartCount > 0
    ? specialEquipmentShell.clearCart()
    : Promise.resolve()

  const [vehicleResult] = await Promise.all([
    vehicleRequest,
    specialEquipmentRequest,
  ])

  if (
    vehicleResult
    && typeof vehicleResult === 'object'
    && 'success' in vehicleResult
    && vehicleResult.success === false
  ) {
    throw new Error(vehicleResult.error || 'Не удалось очистить корзину транспортных средств')
  }

  vehicleCartCount.value = 0
}

const syncVisibleSpecialEquipmentShell = async (
  isAuthenticated: boolean,
  reset: boolean,
): Promise<void> => {
  if (!isSpecialEquipmentCatalogVisible.value || !canUseClientCommerce.value) return
  if (reset) specialEquipmentShell.reset()

  if (isAuthenticated) {
    const hasMergeFailure = await specialEquipmentShell.mergeGuestState()
    if (hasMergeFailure) {
      toast.warning('Часть сохранённой спецтехники не удалось перенести в аккаунт')
    }
    return
  }

  await specialEquipmentShell.loadAll({ resolveGuestProducts: true })
}

watch(() => authStore.isAuthenticated, async (isAuth) => {
  if (isAuth) {
    await Promise.all([
      updateCartCount(),
      syncVisibleSpecialEquipmentShell(true, true),
    ])
  } else {
    vehicleCartCount.value = cartStore.totalItems
    await syncVisibleSpecialEquipmentShell(false, true)
  }
})

watch(() => cartStore.totalItems, (newCount) => {
  if (!authStore.isLeasingCompany) {
    vehicleCartCount.value = newCount
  }
})

watch(() => exchangeCartStore.count, (newCount) => {
  if (authStore.isLeasingCompany) {
    vehicleCartCount.value = newCount
  }
})

onMounted(async () => {
  if (authStore.isAuthenticated) {
    await Promise.all([
      updateCartCount(),
      syncVisibleSpecialEquipmentShell(true, false),
    ])
  } else {
    vehicleCartCount.value = cartStore.totalItems
    await syncVisibleSpecialEquipmentShell(false, false)
  }
})
</script>

<style scoped>
.header-nav-link {
  @apply relative inline-flex min-h-11 items-center rounded-storefront-control px-3 text-sm font-bold text-storefront-link transition-colors duration-200 hover:bg-storefront-surface-muted hover:text-storefront-link-hover active:text-storefront-link-active visited:text-storefront-link-visited focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2;
}

.header-nav-link::after {
  content: '';
  @apply absolute inset-x-3 bottom-0 h-0.5 origin-center scale-x-0 rounded-full bg-storefront-indicator transition-transform duration-200;
}

.header-nav-link--active {
  @apply text-storefront-selected-foreground;
}

.header-nav-link--active::after {
  @apply scale-x-100;
}

@media (prefers-reduced-motion: reduce) {
  .header-nav-link,
  .header-nav-link::after {
    transition-duration: 0.01ms;
  }
}
</style>
