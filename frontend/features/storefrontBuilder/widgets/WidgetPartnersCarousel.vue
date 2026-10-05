<template>
  <div class="storefront-builder-widget py-8" :style="containerStyle">
    <div v-if="config.title || config.subtitle" class="mb-8 text-center">
      <h2 class="text-2xl font-bold tracking-tight storefront-builder-text sm:text-3xl">
        {{ config.title }}
      </h2>
      <p v-if="config.subtitle" class="mt-2 text-base storefront-builder-text-muted">
        {{ config.subtitle }}
      </p>
    </div>

    <!-- Partner logos grid / row -->
    <div class="flex flex-wrap items-center justify-center gap-8 sm:gap-12">
      <div
        v-for="(item, idx) in partnerItems"
        :key="item.id || idx"
        class="flex items-center justify-center p-2"
      >
        <component
          :is="item.link ? 'a' : 'div'"
          :href="item.link || undefined"
          :target="item.link ? '_blank' : undefined"
          :rel="item.link ? 'noopener noreferrer' : undefined"
          class="group flex flex-col items-center justify-center transition-all duration-200"
          :class="item.link ? 'hover:opacity-100' : ''"
        >
          <div
            class="flex h-16 w-36 items-center justify-center rounded-lg border storefront-builder-border storefront-builder-surface p-3 shadow-xs transition duration-200 storefront-builder-group-hover-border group-hover:shadow-sm"
          >
            <img
              v-if="item.logo_url"
              :src="item.logo_url"
              :alt="item.name"
              class="max-h-10 max-w-full object-contain transition duration-200"
              :class="config.grayscale ? 'grayscale opacity-70 group-hover:grayscale-0 group-hover:opacity-100' : ''"
            />
            <span
              v-else
              class="text-center text-xs font-semibold storefront-builder-text-muted storefront-builder-group-hover-primary-text"
            >
              {{ item.name }}
            </span>
          </div>
          <span
            v-if="item.name && item.logo_url"
            class="mt-1 text-xs storefront-builder-text-muted opacity-0 transition group-hover:opacity-100"
          >
            {{ item.name }}
          </span>
        </component>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { widgetColorStyles } from '../utils/widgetStyles'
import type { PartnersCarouselWidgetProps, PartnersCarouselItem, WidgetStyles } from '../types'

const props = defineProps<{
  props?: PartnersCarouselWidgetProps
  styles?: WidgetStyles
}>()

const defaultPartners: PartnersCarouselItem[] = [
  {
    name: 'СберЛизинг',
    logo_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=200&q=80',
  },
  {
    name: 'ВТБ Лизинг',
    logo_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=200&q=80',
  },
  {
    name: 'Альфа-Лизинг',
    logo_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=200&q=80',
  },
  {
    name: 'Газпромбанк Лизинг',
    logo_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=200&q=80',
  },
  {
    name: 'Европлан',
    logo_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=200&q=80',
  },
  {
    name: 'Балтийский Лизинг',
    logo_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=200&q=80',
  },
]

const config = computed<PartnersCarouselWidgetProps>(() => ({
  title: 'Наши партнеры',
  subtitle: 'Ведущие аккредитованные лизинговые компании России',
  items: defaultPartners,
  grayscale: true,
  ...props.props,
}))

const partnerItems = computed(() => {
  return config.value.items && config.value.items.length > 0
    ? config.value.items
    : defaultPartners
})

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})
</script>
