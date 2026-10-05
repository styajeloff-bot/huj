<template>
  <div data-storefront-block="client.cabinet" class="relative">
    <button
      @click="toggleDropdown"
      class="storefront-action-ghost group relative grid min-h-11 min-w-11 place-items-center rounded-lg p-2 transition-colors duration-200"
      :class="displayCount > 0 ? 'text-[color:var(--storefront-destructive-foreground,#ef4444)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))]' : 'text-[color:var(--storefront-destructive-foreground,#4b5563)] hover:text-[color:var(--storefront-destructive-hover-foreground,#ef4444)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))]'"
      title="Избранное"
      :aria-label="displayCount > 0 ? `Избранное, ${displayCount}` : 'Избранное'"
    >
      <svg
        class="h-5 w-5 transition-transform duration-200 group-hover:scale-110"
        :class="displayCount > 0 ? 'fill-current' : ''"
        :fill="displayCount > 0 ? 'currentColor' : 'none'"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
        />
      </svg>

      <!-- Count Badge -->
      <span
        v-if="displayCount > 0"
        key="badge"
        class="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-[color:rgb(var(--storefront-destructive-rgb,239_68_68)/var(--tw-bg-opacity,1))] px-1 text-xs font-medium leading-none text-[color:var(--storefront-destructive-foreground,#ffffff)]"
        aria-hidden="true"
      >
        {{ displayCount > 99 ? '99+' : displayCount }}
      </span>
    </button>

    <!-- Dropdown -->
    <transition name="dropdown">
      <div
        v-if="showDropdown"
        class="absolute right-0 md:right-0 right-[-120px] top-full mt-2 w-96 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-xl shadow-2xl border border-[color:var(--storefront-border,#e5e7eb)] z-50 max-h-106 overflow-hidden"
      >
        <!-- Header -->
        <div class="p-4 border-b border-[color:var(--storefront-border,#f3f4f6)] bg-gradient-to-r from-[var(--storefront-gradient-from,#fef2f2)] to-[var(--storefront-gradient-to,#fdf2f8)]">
          <div class="flex items-center justify-between">
            <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] flex items-center">
              <svg class="w-5 h-5 text-[color:var(--storefront-error-icon,#ef4444)] fill-current mr-2" viewBox="0 0 24 24">
                <path d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
              </svg>
              Избранное
            </h3>
            <button
              @click="showDropdown = false"
              class="storefront-action-ghost grid min-h-11 min-w-11 place-items-center rounded-full text-[color:var(--storefront-ghost-foreground,#9ca3af)] transition-colors duration-200 hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,229_231_235)/var(--tw-bg-opacity,1))] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--storefront-focus,#dc2626)]"
              aria-label="Закрыть избранное"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">
            {{ displayCount }} {{ getItemsText(displayCount) }}
          </p>
        </div>

        <!-- Items list -->
        <div class="max-h-64 overflow-y-auto overscroll-contain">
          <!-- Loading -->
          <div v-if="favoritesStore.loading || guestLoading" class="p-8 flex justify-center">
            <div class="animate-spin rounded-full h-7 w-7 border-b-2 border-[color:var(--storefront-error-border,#ef4444)]"></div>
          </div>

          <!-- Empty -->
          <div v-else-if="displayCount === 0" class="p-6 text-center">
            <svg class="w-12 h-12 mx-auto text-[color:var(--storefront-icon,#d1d5db)] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
            <p class="text-sm font-medium text-[color:var(--storefront-text-muted,#4b5563)]">Список избранного пуст</p>
            <p class="text-xs text-[color:var(--storefront-text-muted,#9ca3af)] mt-1">
              Нажмите сердце на карточке спецтехники
            </p>
            <NuxtLink
              :to="publicRoute('/special-equipment')"
              @click="showDropdown = false"
              class="inline-block mt-3 px-4 py-2 bg-[color:rgb(var(--storefront-error-rgb,239_68_68)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-link,#ffffff)] rounded-lg hover:bg-[color:rgb(var(--storefront-error-hover-rgb,220_38_38)/var(--tw-bg-opacity,1))] transition-colors duration-200 text-sm font-medium"
            >
              Каталог транспортных средств и специальной техники
            </NuxtLink>
          </div>

          <!-- List -->
          <div v-else class="divide-y divide-[color:var(--storefront-border,#f3f4f6)]">
            <div
              v-for="item in previewItems"
              :key="item.vehicle_id"
              class="p-4 hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] transition-colors duration-200"
            >
              <div class="flex items-start space-x-3">
                <!-- Image -->
                <NuxtLink
                  :to="publicRoute('/special-equipment')"
                  @click="showDropdown = false"
                  class="relative w-16 h-12 bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] rounded-lg overflow-hidden flex-shrink-0 hover:opacity-80 transition-opacity duration-200"
                >
                  <img
                    v-if="item.main_image"
                    :src="vehicleImageUrl(item.main_image)"
                    :alt="`${item.mark_name || item.brand_name || item.mark_id || ''} ${item.model_name || item.model_id || ''}`"
                    class="w-full h-full object-cover"
                    @error="handleImageError"
                  />
                  <div v-else class="w-full h-full flex items-center justify-center text-[color:var(--storefront-text-muted,#9ca3af)]">
                    <svg class="text-[color:var(--storefront-icon,inherit)] w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <span
                    v-if="item.year"
                    class="absolute top-0.5 right-0.5 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.6)] backdrop-blur-sm text-[color:var(--storefront-link,#ffffff)] text-[10px] px-1 py-0.5 rounded font-medium leading-none"
                  >
                    {{ item.year }} г.
                  </span>
                </NuxtLink>

                <!-- Info -->
                <div class="flex-1 min-w-0">
                  <NuxtLink
                    :to="publicRoute('/special-equipment')"
                    @click="showDropdown = false"
                    class="block hover:text-[color:var(--storefront-link-hover,#dc2626)] transition-colors duration-200"
                  >
                    <h4 class="text-sm font-medium text-[color:var(--storefront-title,#111827)] truncate hover:text-[color:var(--storefront-error-text,#dc2626)]">
                      {{ item.mark_name || item.brand_name || item.mark_id }} {{ item.model_name || item.model_id }}
                    </h4>
                  </NuxtLink>
                  <div class="flex items-center justify-between mt-2">
                    <div class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] truncate mr-2">
                      <span v-if="item.group_name">{{ item.group_name }}</span>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                      <span v-if="item.price || item.base_price" class="text-sm font-semibold text-[color:var(--storefront-text,#111827)]">
                        {{ formatPrice(item.price || item.base_price) }}
                      </span>
                      <button
                        @click="removeItem(item.vehicle_id)"
                        class="storefront-action-ghost text-[color:var(--storefront-destructive-foreground,#ef4444)] hover:text-[color:var(--storefront-destructive-hover-foreground,#b91c1c)] p-1 hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))] rounded transition-colors duration-200"
                        title="Удалить из избранного"
                      >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <NuxtLink
              v-if="isSpecialEquipmentCatalogVisible && additionalCount > 0"
              :to="authStore.isAuthenticated ? publicRoute('/cabinet?tab=favorites') : publicRoute('/special-equipment')"
              class="flex min-h-16 items-center justify-between gap-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-link,#450a0a)] hover:bg-[color:rgb(var(--storefront-error-hover-rgb,254_226_226)/var(--tw-bg-opacity,1))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--storefront-focus,#dc2626)]"
              @click="showDropdown = false"
            >
              <span>
                <strong>{{ additionalCount }}</strong>
                {{ getSpecialEquipmentText(additionalCount) }}
              </span>
              <span class="font-bold">Открыть →</span>
            </NuxtLink>

            <!-- Overflow hint -->
            <div v-if="vehicleDisplayCount > 4" class="px-4 py-2 text-center text-xs text-[color:var(--storefront-text-muted,#9ca3af)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
              + ещё {{ vehicleDisplayCount - 4 }} {{ getVehicleText(vehicleDisplayCount - 4) }}
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div v-if="displayCount > 0" class="p-4 border-t border-[color:var(--storefront-border,#f3f4f6)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
          <div class="flex space-x-2">
            <!-- Authenticated: link to cabinet -->
            <NuxtLink
              v-if="authStore.isAuthenticated"
              :to="publicRoute('/cabinet?tab=favorites')"
              @click="showDropdown = false"
              class="flex-1 px-3 py-2 text-sm font-medium text-[color:var(--storefront-link,#ffffff)] rounded-lg hover:bg-[color:rgb(var(--storefront-error-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] transition-colors duration-200 text-center"
              style="background-color: var(--storefront-destructive,#e84646);"
            >
              Все избранные
            </NuxtLink>
            <!-- Guest: open auth modal -->
            <button
              v-else
              @click="openAuthModal"
              class="storefront-action-destructive flex-1 px-3 py-2 text-sm font-medium text-[color:var(--storefront-destructive-foreground,#ffffff)] rounded-lg hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] transition-colors duration-200"
              style="background-color: var(--storefront-destructive,#e84646);"
            >
              Все избранные
            </button>
          </div>
        </div>
      </div>
    </transition>

  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'
import { useSectionVisibilityStore } from '~/features/sectionVisibility/store/sectionVisibility'
import type { UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'
const emit = defineEmits(['openAuthModal'])

const props = withDefaults(defineProps<{
  additionalCount?: number
}>(), {
  additionalCount: 0,
})

const authStore = useAuthStore()
const favoritesStore = useFavoritesStore()
const visibilityStore = useSectionVisibilityStore()
const { formatPrice } = useFormatPrice()
const { publicRoute } = useStorefront()

const showDropdown = ref(false)
const guestLoading = ref(false)

const vehicleDisplayCount = computed(() =>
  authStore.isAuthenticated ? favoritesStore.count : favoritesStore.guestCount
)
const isSpecialEquipmentCatalogVisible = computed(() =>
  visibilityStore.isSectionVisible('public', 'special_equipment_catalog'),
)
const displayCount = computed(() => vehicleDisplayCount.value + (
  isSpecialEquipmentCatalogVisible.value ? Math.max(0, props.additionalCount) : 0
))

const previewItems = computed(() =>
  authStore.isAuthenticated
    ? favoritesStore.items.slice(0, 4)
    : favoritesStore.guestItems.slice(0, 4)
)

const openAuthModal = () => {
  showDropdown.value = false
  emit('openAuthModal')
}

const toggleDropdown = async () => {
  if (!showDropdown.value) {
    if (authStore.isAuthenticated && authStore.isClient) {
      await favoritesStore.fetchFavorites()
    } else if (!authStore.isAuthenticated) {
      guestLoading.value = true
      await favoritesStore.fetchGuestFavorites()
      guestLoading.value = false
    }
  }
  showDropdown.value = !showDropdown.value
}

const removeItem = async (vehicleId: UUID) => {
  if (authStore.isAuthenticated) {
    await favoritesStore.removeFromFavorites(vehicleId)
  } else {
    favoritesStore.removeFromGuestFavorites(vehicleId)
  }
}

const handleImageError = (event: Event) => {
  (event.target as HTMLImageElement).src = '/images/car-placeholder.png'
}

const getVehicleText = (count: number) => {
  if (count % 10 === 1 && count % 100 !== 11) return 'автомобиль'
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return 'автомобиля'
  return 'автомобилей'
}

const getItemsText = (count: number) => {
  if (!isSpecialEquipmentCatalogVisible.value) return getVehicleText(count)
  if (count % 10 === 1 && count % 100 !== 11) return 'позиция'
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return 'позиции'
  return 'позиций'
}

const getSpecialEquipmentText = (count: number) => {
  if (count % 10 === 1 && count % 100 !== 11) return 'единица спецтехники'
  if ([2, 3, 4].includes(count % 10) && ![12, 13, 14].includes(count % 100)) return 'единицы спецтехники'
  return 'единиц спецтехники'
}

// Watch for clicks outside
const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement | null
  if (showDropdown.value && !target?.closest('.relative')) {
    showDropdown.value = false
  }
}

// Prevent body scroll when dropdown reaches scroll boundaries
const preventBodyScroll = (event: WheelEvent) => {
  if (!showDropdown.value) return

  const target = event.target as HTMLElement | null
  const scrollContainer = target?.closest('.max-h-64.overflow-y-auto') as HTMLElement | null
  if (!scrollContainer) return

  const { scrollTop, scrollHeight, clientHeight } = scrollContainer
  const isAtTop = scrollTop === 0
  const isAtBottom = scrollTop + clientHeight >= scrollHeight
  const isScrollingUp = event.deltaY < 0
  const isScrollingDown = event.deltaY > 0

  if ((isAtTop && isScrollingUp) || (isAtBottom && isScrollingDown)) {
    event.preventDefault()
  }
}

onMounted(async () => {
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('wheel', preventBodyScroll, { passive: false })
  if (authStore.isAuthenticated && authStore.isClient) {
    await favoritesStore.fetchFavorites()
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('wheel', preventBodyScroll)
})

watch(
  () => authStore.isAuthenticated && authStore.isClient,
  async (canLoadFavorites) => {
    if (canLoadFavorites) {
      await favoritesStore.fetchFavorites()
    }
  }
)
</script>

<style scoped>
.badge-enter-active,
.badge-leave-active {
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.badge-enter-from,
.badge-leave-to {
  transform: scale(0);
  opacity: 0;
}

.dropdown-enter-active {
  transition: all 0.18s ease-out;
}
.dropdown-leave-active {
  transition: all 0.15s ease-in;
}
.dropdown-enter-from,
.dropdown-leave-to {
  transform: translateY(-6px);
  opacity: 0;
}
</style>
