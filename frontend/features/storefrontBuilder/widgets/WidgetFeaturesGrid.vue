<template>
  <div class="storefront-builder-widget py-6" :style="containerStyle">
    <div v-if="config.title || config.subtitle" class="mb-10 text-center">
      <h2 class="text-2xl font-bold tracking-tight storefront-builder-text sm:text-3xl">
        {{ config.title }}
      </h2>
      <p v-if="config.subtitle" class="mt-2 text-base storefront-builder-text-muted">
        {{ config.subtitle }}
      </p>
    </div>

    <div class="grid gap-6" :class="gridColsClass">
      <div
        v-for="(item, idx) in itemsList"
        :key="item.id || idx"
        class="flex flex-col rounded-xl border storefront-builder-border storefront-builder-surface p-6 shadow-sm transition hover:shadow-md"
      >
        <div class="mb-4 flex h-12 w-12 items-center justify-center rounded-lg storefront-builder-primary-soft storefront-builder-primary-text">
          <component :is="renderIcon(item.icon)" class="h-6 w-6" />
        </div>

        <h3 class="text-lg font-semibold storefront-builder-text">
          {{ item.title }}
        </h3>

        <p class="mt-2 text-sm leading-relaxed storefront-builder-text-muted">
          {{ item.description }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { widgetColorStyles } from '../utils/widgetStyles'
import { computed, h } from 'vue'
import type { FeaturesGridWidgetProps, FeaturesGridItem, WidgetStyles } from '../types'

const props = defineProps<{
  props?: FeaturesGridWidgetProps
  styles?: WidgetStyles
}>()

const defaultItems: FeaturesGridItem[] = [
  {
    icon: 'clock',
    title: 'Решение за 1 день',
    description: 'Быстрое рассмотрение заявки по 2 документам без долгого сбора финансовой отчетности',
  },
  {
    icon: 'percent',
    title: 'Аванс от 0%',
    description: 'Индивидуальные условия лизинга с минимальным изъятием средств из оборота компании',
  },
  {
    icon: 'shield',
    title: 'Надежные партнеры',
    description: 'Работаем с топ-15 аккредитованными лизинговыми компаниями России',
  },
  {
    icon: 'tax',
    title: 'Экономия до 40%',
    description: 'Полный зачет НДС и уменьшение налога на прибыль за счет включения платежей в расходы',
  },
]

const config = computed<FeaturesGridWidgetProps>(() => ({
  title: 'Преимущества работы с нами',
  subtitle: 'Почему более 1 500 компаний выбирают Carcraft для лизинга техники',
  columns: 4,
  items: defaultItems,
  ...props.props,
}))

const itemsList = computed(() => {
  if (config.value.items && config.value.items.length > 0) {
    return config.value.items
  }
  return defaultItems
})

const gridColsClass = computed(() => {
  const c = config.value.columns ?? 4
  switch (c) {
    case 2:
      return 'grid-cols-1 md:grid-cols-2'
    case 3:
      return 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3'
    case 4:
    default:
      return 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4'
  }
})

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})

const renderIcon = (iconName: string) => {
  switch (iconName) {
    case 'clock':
      return () =>
        h('svg', { fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor' }, [
          h('path', {
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
            'stroke-width': '2',
            d: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
          }),
        ])
    case 'percent':
    case 'tax':
      return () =>
        h('svg', { fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor' }, [
          h('path', {
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
            'stroke-width': '2',
            d: 'M9 14l6-6m-5.5.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm8 8a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z',
          }),
        ])
    case 'shield':
      return () =>
        h('svg', { fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor' }, [
          h('path', {
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
            'stroke-width': '2',
            d: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
          }),
        ])
    case 'truck':
      return () =>
        h('svg', { fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor' }, [
          h('path', {
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
            'stroke-width': '2',
            d: 'M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z',
          }),
          h('path', {
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
            'stroke-width': '2',
            d: 'M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1 1H9m4-1V8a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6-1a1 1 0 001 1h1M5 17a2 2 0 104 0m-4 0a2 2 0 114 0m6 0a2 2 0 104 0m-4 0a2 2 0 114 0',
          }),
        ])
    default:
      // check/star
      return () =>
        h('svg', { fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor' }, [
          h('path', {
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
            'stroke-width': '2',
            d: 'M5 13l4 4L19 7',
          }),
        ])
  }
}
</script>
