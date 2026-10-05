<template>
  <div
    class="storefront-builder-widget overflow-hidden rounded-2xl p-8 sm:p-12 shadow-sm transition"
    :class="backgroundThemeClass"
    :style="containerStyle"
  >
    <div class="flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-center">
      <div class="max-w-2xl">
        <h2 class="text-2xl font-bold tracking-tight sm:text-3xl" :class="textColorClass">
          {{ config.title || 'Нужна консультация по лизингу?' }}
        </h2>
        <p v-if="config.subtitle" class="mt-2 text-base sm:text-lg" :class="subtitleColorClass">
          {{ config.subtitle }}
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-4 flex-shrink-0">
        <NuxtLink
          v-if="config.button_text"
          :to="config.button_link || '#lead-form'"
          class="rounded-lg px-6 py-3.5 text-base font-semibold shadow-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          :class="primaryButtonClass"
        >
          {{ config.button_text }}
        </NuxtLink>

        <NuxtLink
          v-if="config.secondary_button_text && config.secondary_button_link"
          :to="config.secondary_button_link"
          class="rounded-lg border px-6 py-3.5 text-base font-semibold transition"
          :class="secondaryButtonClass"
        >
          {{ config.secondary_button_text }}
        </NuxtLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { widgetColorStyles } from '../utils/widgetStyles'
import type { CtaStripWidgetProps, WidgetStyles } from '../types'

const props = defineProps<{
  props?: CtaStripWidgetProps
  styles?: WidgetStyles
}>()

const config = computed<CtaStripWidgetProps>(() => ({
  title: 'Нужна помощь в выборе техники или расчете лизинга?',
  subtitle: 'Оставьте заявку, и наш специалист свяжется с вами в течение 15 минут',
  button_text: 'Получить консультацию',
  button_link: '#lead-form',
  background_style: 'primary',
  ...props.props,
}))

const backgroundThemeClass = computed(() => {
  switch (config.value.background_style) {
    case 'dark':
      return 'storefront-builder-dark storefront-builder-primary-foreground'
    case 'gradient':
      return 'storefront-builder-gradient storefront-builder-primary-foreground'
    case 'light':
      return 'storefront-builder-surface-muted border storefront-builder-border storefront-builder-text'
    case 'primary':
    default:
      return 'storefront-builder-primary storefront-builder-primary-foreground'
  }
})

const textColorClass = computed(() => {
  return config.value.background_style === 'light' ? 'storefront-builder-text' : 'storefront-builder-primary-foreground'
})

const subtitleColorClass = computed(() => {
  return config.value.background_style === 'light' ? 'storefront-builder-text-muted' : 'storefront-builder-primary-foreground opacity-80'
})

const primaryButtonClass = computed(() => {
  if (config.value.background_style === 'light') {
    return 'storefront-builder-primary storefront-builder-primary-foreground storefront-builder-hover-primary storefront-builder-focus'
  }
  return 'storefront-builder-surface storefront-builder-primary-text storefront-builder-hover-surface storefront-builder-focus'
})

const secondaryButtonClass = computed(() => {
  if (config.value.background_style === 'light') {
    return 'storefront-builder-border storefront-builder-text storefront-builder-hover-surface'
  }
  return 'border-white/40 storefront-builder-primary-foreground storefront-builder-hover-surface'
})

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (config.value.background_style === 'dark' && !s['--storefront-widget-foreground']) {
    s['--storefront-widget-foreground'] = 'var(--storefront-surface, #fff)'
  }
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  if (s.backgroundColor) s.backgroundImage = 'none'
  return s
})
</script>
