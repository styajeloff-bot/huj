<template>
  <div data-storefront-block="client.cabinet" class="card p-6">
    <div class="flex justify-between items-center mb-6">
      <h3 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">Мои избранные</h3>
      <div class="flex space-x-2">
        <button
          v-if="selectedItems.length > 0"
          @click="bulkRemove"
          class="storefront-action-destructive bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-destructive-foreground,#ffffff)] px-4 py-2 rounded-lg transition-colors text-sm"
        >
          Удалить выбранные ({{ selectedItems.length }})
        </button>
        <button
          v-if="favoritesStore.count > 0"
          @click="clearAll"
          class="storefront-action-ghost bg-[color:rgb(var(--storefront-ghost-rgb,75_85_99)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,55_65_81)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-ghost-foreground,#ffffff)] px-4 py-2 rounded-lg transition-colors text-sm"
        >
          Очистить все
        </button>
      </div>
    </div>

    <!-- Фильтры -->
    <div v-if="brands.length > 0" class="flex flex-col md:flex-row gap-4 mb-6">
      <div class="flex-1">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Поиск по бренду или модели..."
          class="storefront-control w-full px-4 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-transparent"
        >
      </div>
      <select
        v-model="selectedBrand"
        class="storefront-control px-4 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)]"
      >
        <option value="">Все бренды</option>
        <option v-for="brand in brands" :key="brand.id" :value="brand.id">
          {{ brand.name }}
        </option>
      </select>
      <select
        v-model="sortBy"
        class="storefront-control px-4 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)]"
      >
        <option value="added_at">По дате добавления</option>
        <option value="price_asc">По цене (возрастание)</option>
        <option value="price_desc">По цене (убывание)</option>
        <option value="year_desc">По году (новые)</option>
        <option value="year_asc">По году (старые)</option>
      </select>
    </div>

    <!-- Loading -->
    <div v-if="favoritesStore.loading" class="text-center py-8">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-[color:var(--storefront-border,#2563eb)] mx-auto"></div>
      <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загрузка избранного...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-center py-8">
      <div class="text-[color:var(--storefront-error-text,#dc2626)] mb-2">{{ error }}</div>
      <button
        @click="loadFavorites"
        class="storefront-action-primary bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] px-4 py-2 rounded-lg"
      >
        Попробовать снова
      </button>
    </div>

    <!-- Empty -->
    <div v-else-if="favoritesStore.isEmpty" class="text-center py-8">
      <svg class="mx-auto h-24 w-24 text-[color:var(--storefront-icon,#9ca3af)] mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
      </svg>
      <div class="text-[color:var(--storefront-text-muted,#4b5563)] mb-4">У вас пока нет избранной техники</div>
      <NuxtLink :to="publicRoute('/special-equipment')" class="storefront-action-primary bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] px-6 py-3 rounded-lg inline-block transition-colors">
        Перейти к каталогу
      </NuxtLink>
    </div>

    <!-- No results after filter -->
    <div v-else-if="filteredFavorites.length === 0" class="text-center py-8">
      <div class="text-[color:var(--storefront-text-muted,#4b5563)] mb-4">По вашему запросу ничего не найдено</div>
      <button @click="clearFilters" class="storefront-action-primary bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] px-4 py-2 rounded-lg">
        Сбросить фильтры
      </button>
    </div>

    <!-- List -->
    <div v-else>
      <!-- Bulk select bar -->
      <div class="flex items-center mb-4 p-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg">
        <input
          v-model="selectAll"
          @change="toggleSelectAll"
          type="checkbox"
          class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded"
        >
        <label class="ml-2 text-sm text-[color:var(--storefront-label,#374151)]">
          Выбрать все ({{ filteredFavorites.length }})
        </label>
        <div class="ml-auto text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
          Всего: {{ favoritesStore.count }}
        </div>
      </div>

      <!-- Cards grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div
          v-for="car in filteredFavorites"
          :key="car.vehicle_id"
          class="relative"
          :class="{ 'ring-2 ring-[color:var(--storefront-border,#3b82f6)] rounded-xl': selectedItems.includes(car.vehicle_id) }"
        >
          <!-- Selection checkbox overlay -->
          <div class="absolute top-3 left-3 z-30">
            <input
              v-model="selectedItems"
              :value="car.vehicle_id"
              type="checkbox"
              class="storefront-control h-4 w-4 text-[color:var(--storefront-text-muted,#2563eb)] focus:ring-[color:var(--storefront-focus,#3b82f6)] border-[color:var(--storefront-border,#d1d5db)] rounded bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow"
            >
          </div>

          <CarCard :car="car" :show-cart-button="true" :show-calculator="false" />
        </div>
      </div>

      <!-- Compare button -->
      <div v-if="selectedItems.length >= 2" class="mt-6 text-center">
        <button
          @click="compareVehicles"
          class="storefront-action-ghost bg-[color:rgb(var(--storefront-ghost-rgb,147_51_234)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,126_34_206)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-ghost-foreground,#ffffff)] px-6 py-3 rounded-lg transition-colors"
        >
          Сравнить выбранные ({{ selectedItems.length }})
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useToast } from '@/composables/useToast'
import { useLogger } from '@/composables/useLogger'
import CarCard from '~/features/cars/components/CarCard.vue'
import type { FavoriteBrand } from '~/types/features'
import type { FavoriteItem } from '~/features/favorites/api/favoritesApi'
import type { UUID } from '~/types/ids'
import { useStorefront } from '~/features/storefront'

const favoritesStore = useFavoritesStore()
const { showToast } = useToast()
const logger = useLogger()
const { publicRoute } = useStorefront()

const error = ref('')
const selectedItems = ref<UUID[]>([])
const selectAll = ref(false)

const searchQuery = ref('')
const selectedBrand = ref('')
const sortBy = ref('added_at')

const brands = computed<FavoriteBrand[]>(() => {
  const uniqueBrands = new Map<string, FavoriteBrand>()

  for (const favorite of favoritesStore.items) {
    const brandName = favorite.mark_name || favorite.brand_name || favorite.mark_id
    const brandId = favorite.brand_id ?? favorite.mark_id ?? brandName

    if (!brandName || brandId === undefined || brandId === null) {
      continue
    }

    const key = String(brandId)
    if (!uniqueBrands.has(key)) {
      uniqueBrands.set(key, {
        id: key,
        name: brandName,
      })
    }
  }

  return Array.from(uniqueBrands.values()).sort((a, b) => a.name.localeCompare(b.name))
})

const filteredFavorites = computed(() => {
  let result = [...favoritesStore.items] as FavoriteItem[]

  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter((favorite) =>
      (favorite.mark_name || '').toLowerCase().includes(q) ||
      (favorite.model_name || '').toLowerCase().includes(q)
    )
  }

  if (selectedBrand.value) {
    result = result.filter((favorite) => {
      const brandId = favorite.brand_id ?? favorite.mark_id ?? favorite.mark_name ?? favorite.brand_name
      return String(brandId) === selectedBrand.value
    })
  }

  // A vehicle can only occur once in favorites; keep the UI stable if a stale
  // response still contains duplicate rows.
  const seenVehicleIds = new Set<UUID>()
  result = result.filter((item) => {
    if (seenVehicleIds.has(item.vehicle_id)) return false
    seenVehicleIds.add(item.vehicle_id)
    return true
  })

  result = [...result].sort((a, b) => {
    switch (sortBy.value) {
      case 'price_asc': return (a.base_price || 0) - (b.base_price || 0)
      case 'price_desc': return (b.base_price || 0) - (a.base_price || 0)
      case 'year_desc': return (b.year || 0) - (a.year || 0)
      case 'year_asc': return (a.year || 0) - (b.year || 0)
      default: return new Date(String(b.added_at || 0)).getTime() - new Date(String(a.added_at || 0)).getTime()
    }
  })

  return result
})

const loadFavorites = async () => {
  try {
    error.value = ''
    await favoritesStore.fetchFavorites()
  } catch (err: unknown) {
    logger.error('Error fetching favorites:', err)
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке избранного'
  }
}

const clearFilters = () => {
  searchQuery.value = ''
  selectedBrand.value = ''
  sortBy.value = 'added_at'
  selectedItems.value = []
  selectAll.value = false
}

const toggleSelectAll = () => {
  selectedItems.value = selectAll.value
    ? filteredFavorites.value.map((favorite) => favorite.vehicle_id)
    : []
}

const bulkRemove = async () => {
  if (selectedItems.value.length === 0) return
  try {
    await favoritesStore.bulkRemoveFavorites(selectedItems.value)
    // Refresh store
    await favoritesStore.fetchFavorites()
    selectedItems.value = []
    selectAll.value = false
    showToast.success('Выбранные автомобили удалены из избранного')
  } catch (err: unknown) {
    logger.error('Error bulk removing favorites:', err)
    showToast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при удалении')
  }
}

const clearAll = async () => {
  if (!confirm('Вы уверены, что хотите очистить все избранное?')) return
  const result = await favoritesStore.clearFavorites()
  if (result.success) {
    selectedItems.value = []
    selectAll.value = false
    showToast.success('Избранное очищено')
  } else {
    showToast.error('Ошибка при очистке избранного')
  }
}

const compareVehicles = () => {
  showToast.info('Функция сравнения автомобилей находится в разработке')
}

onMounted(loadFavorites)

watch(() => favoritesStore.items, () => {
  // Update selection state
  selectAll.value = selectedItems.value.length > 0 &&
    selectedItems.value.length === filteredFavorites.value.length
}, { deep: true })

// Reset selection when filters change
watch([searchQuery, selectedBrand, sortBy], () => {
  selectedItems.value = []
  selectAll.value = false
})
</script>
