<template>
  <div class="storefront-builder-widget py-6" :style="containerStyle">
    <!-- Header -->
    <div class="mb-8 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-end">
      <div>
        <h2 class="text-2xl font-bold tracking-tight storefront-builder-text sm:text-3xl">
          {{ config.title || 'Популярная спецтехника в лизинг' }}
        </h2>
        <p v-if="config.subtitle" class="mt-2 text-base storefront-builder-text-muted">
          {{ config.subtitle }}
        </p>
      </div>

      <NuxtLink
        v-if="config.view_all_link || true"
        :to="config.view_all_link || publicRoute('/special-equipment')"
        class="inline-flex items-center text-sm font-semibold storefront-builder-primary-text storefront-builder-hover-primary-text"
      >
        <span>Все предложения</span>
        <svg class="ml-1.5 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </NuxtLink>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="grid gap-6" :class="gridColumnsClass">
      <div
        v-for="i in (config.item_count ?? 4)"
        :key="i"
        class="h-80 animate-pulse rounded-xl storefront-builder-surface-muted"
      />
    </div>

    <!-- Product Grid -->
    <div v-else class="grid gap-6" :class="gridColumnsClass">
      <div
        v-for="item in displayProducts"
        :key="item.id"
        class="group flex flex-col overflow-hidden rounded-xl border storefront-builder-border storefront-builder-surface transition hover:shadow-lg"
      >
        <!-- Thumbnail -->
        <div class="relative h-48 w-full overflow-hidden storefront-builder-surface-muted">
          <img
            :src="item.image_url"
            :alt="item.title"
            class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
            loading="lazy"
          />
          <span
            v-if="item.availability_status"
            class="absolute top-3 left-3 rounded-full storefront-builder-surface px-2.5 py-0.5 text-xs font-semibold storefront-builder-text shadow-sm backdrop-blur-sm"
          >
            {{ item.availability_status }}
          </span>
        </div>

        <!-- Details -->
        <div class="flex flex-1 flex-col p-5">
          <div class="text-xs font-medium uppercase tracking-wider storefront-builder-text-muted">
            {{ item.category || 'Спецтехника' }}
          </div>
          <h3 class="mt-1 text-base font-semibold storefront-builder-text storefront-builder-group-hover-primary-text line-clamp-2">
            {{ item.title }}
          </h3>

          <div class="mt-4 flex items-baseline justify-between border-t storefront-builder-border pt-3">
            <div>
              <div v-if="config.show_price ?? true" class="text-lg font-bold storefront-builder-text">
                {{ formatRubles(item.price) }}
              </div>
              <div v-if="item.monthly_payment" class="text-xs storefront-builder-primary-text font-medium">
                от {{ formatRubles(item.monthly_payment) }}/мес
              </div>
            </div>

            <NuxtLink
              v-if="config.show_cta ?? true"
              :to="publicRoute(`/special-equipment/products/${item.id}`)"
              class="rounded-lg storefront-builder-surface-muted px-3 py-1.5 text-xs font-semibold storefront-builder-text transition storefront-builder-group-hover-primary storefront-builder-group-hover-primary-foreground"
            >
              {{ config.cta_text || 'Подробнее' }}
            </NuxtLink>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { widgetColorStyles } from '../utils/widgetStyles'
import { ref, computed, onMounted } from 'vue'
import { useStorefront } from '~/features/storefront'
import type { ProductShowcaseWidgetProps, WidgetStyles } from '../types'

interface ShowcaseProduct {
  id: string
  title: string
  category?: string
  price: number
  monthly_payment?: number
  image_url: string
  availability_status?: string
}

const props = defineProps<{
  props?: ProductShowcaseWidgetProps
  styles?: WidgetStyles
}>()

const { slug, publicRoute } = useStorefront()
const configRuntime = useRuntimeConfig()

const config = computed<ProductShowcaseWidgetProps>(() => ({
  title: 'Каталог спецтехники',
  subtitle: 'Техника в наличии с возможностью оформления в лизинг за 1 день',
  item_count: 4,
  mode: 'grid',
  columns_count: 4,
  show_price: true,
  show_cta: true,
  cta_text: 'В лизинг',
  ...props.props,
}))

const gridColumnsClass = computed(() => {
  const count = config.value.columns_count ?? 4
  switch (count) {
    case 2:
      return 'grid-cols-1 sm:grid-cols-2'
    case 3:
      return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
    case 4:
    default:
      return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4'
  }
})

const isLoading = ref(false)
const loadedProducts = ref<ShowcaseProduct[]>([])

const fallbackProducts: ShowcaseProduct[] = [
  {
    id: 'spec-prod-1',
    title: 'Гусеничный экскаватор SDLG E6210F',
    category: 'Экскаваторы',
    price: 9800000,
    monthly_payment: 195000,
    image_url: 'https://images.unsplash.com/photo-1578328819058-b69f3a3b0f6b?auto=format&fit=crop&w=600&q=80',
    availability_status: 'В наличии',
  },
  {
    id: 'spec-prod-2',
    title: 'Фронтальный погрузчик XCMG LW300FN',
    category: 'Погрузчики',
    price: 4950000,
    monthly_payment: 99000,
    image_url: 'https://images.unsplash.com/photo-1580983218765-f663bec07b37?auto=format&fit=crop&w=600&q=80',
    availability_status: 'В наличии',
  },
  {
    id: 'spec-prod-3',
    title: 'Самосвал Shacman X3000 6x4',
    category: 'Самосвалы',
    price: 8650000,
    monthly_payment: 172000,
    image_url: 'https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?auto=format&fit=crop&w=600&q=80',
    availability_status: 'В наличии',
  },
  {
    id: 'spec-prod-4',
    title: 'Автокран XCMG QY25K5D',
    category: 'Автокраны',
    price: 13500000,
    monthly_payment: 268000,
    image_url: 'https://images.unsplash.com/photo-1508873696983-2df5293cb32b?auto=format&fit=crop&w=600&q=80',
    availability_status: 'Под заказ',
  },
]

const displayProducts = computed(() => {
  const list = loadedProducts.value.length > 0 ? loadedProducts.value : fallbackProducts
  return list.slice(0, config.value.item_count ?? 4)
})

const formatRubles = (val: number) => {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(val)
}

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})

const fetchProducts = async () => {
  isLoading.value = true
  try {
    const url = slug.value
      ? `/api/v1/storefronts/${slug.value}/special-equipment/products`
      : '/api/v1/special-equipment/products'
    const res = await $fetch<{ items?: any[] }>(url, {
      baseURL: configRuntime.public.apiBase,
      params: {
        page_size: config.value.item_count ?? 4,
        sort: config.value.sort_by || 'newest',
      },
    })
    if (res?.items && Array.isArray(res.items) && res.items.length > 0) {
      loadedProducts.value = res.items.map((item: any) => ({
        id: item.id,
        title: item.title || `${item.mark_name || ''} ${item.model_name || ''}`.trim() || 'Спецтехника',
        category: item.category_name,
        price: item.price_rub || item.price || 0,
        monthly_payment: item.monthly_payment_rub || Math.round((item.price_rub || 5000000) * 0.02),
        image_url: item.primary_image_url || item.image_url || fallbackProducts[0].image_url,
        availability_status: item.in_stock ? 'В наличии' : 'Под заказ',
      }))
    }
  } catch (_e) {
    // Graceful fallback to fallbackProducts
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  fetchProducts()
})
</script>
