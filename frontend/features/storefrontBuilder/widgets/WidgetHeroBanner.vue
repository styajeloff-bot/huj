<template>
  <div
    class="storefront-builder-widget relative overflow-hidden rounded-xl storefront-builder-primary storefront-builder-primary-foreground"
    :style="containerStyle"
  >
    <!-- Background image -->
    <div
      v-if="config.background_image"
      class="absolute inset-0 bg-cover bg-center transition-all duration-300"
      :style="{ backgroundImage: `url(${config.background_image})` }"
    />

    <!-- Overlay -->
    <div
      v-if="config.background_image"
      class="absolute inset-0 bg-black"
      :style="{ opacity: (config.overlay_opacity ?? 40) / 100 }"
    />

    <!-- Decorative gradient if no image -->
    <div
      v-else-if="!normalizePageColor(styles?.background_color)"
      class="absolute inset-0 storefront-builder-gradient"
    />

    <!-- Content -->
    <div
      class="relative z-10 mx-auto max-w-5xl px-6 py-16 sm:px-8 lg:px-12 lg:py-24"
      :class="alignmentClass"
    >
      <!-- Badge -->
      <div v-if="config.badge_text" class="mb-4 inline-flex items-center">
        <span
          class="rounded-full storefront-builder-primary-soft px-3.5 py-1 text-xs font-semibold uppercase tracking-wider storefront-builder-primary-text ring-1 ring-inset storefront-builder-border"
        >
          {{ config.badge_text }}
        </span>
      </div>

      <!-- Title -->
      <h1
        class="text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl"
        :class="config.align === 'center' ? 'mx-auto' : ''"
      >
        {{ config.title || 'Мы — больше, чем лизинг' }}
      </h1>

      <!-- Subtitle -->
      <p
        v-if="config.subtitle"
        class="mt-4 max-w-2xl text-lg storefront-builder-primary-foreground opacity-80 sm:text-xl"
        :class="config.align === 'center' ? 'mx-auto' : ''"
      >
        {{ config.subtitle }}
      </p>

      <!-- CTA Buttons -->
      <div
        class="mt-8 flex flex-wrap gap-4"
        :class="config.align === 'center' ? 'justify-center' : config.align === 'right' ? 'justify-end' : 'justify-start'"
      >
        <button
          v-if="config.cta_text"
          type="button"
          class="inline-flex items-center justify-center rounded-lg storefront-builder-primary px-6 py-3 text-base font-semibold storefront-builder-primary-foreground shadow-sm transition storefront-builder-hover-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 storefront-builder-focus"
          @click="handleCtaClick"
        >
          {{ config.cta_text }}
        </button>

        <a
          v-if="config.secondary_cta_text && config.secondary_cta_link"
          :href="config.secondary_cta_link"
          class="inline-flex items-center justify-center rounded-lg border storefront-builder-border storefront-builder-surface px-6 py-3 text-base font-semibold storefront-builder-primary-text backdrop-blur-sm transition storefront-builder-hover-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 storefront-builder-focus"
        >
          {{ config.secondary_cta_text }}
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { widgetColorStyles } from '../utils/widgetStyles'
import { normalizePageColor } from '../utils/pageTheme'
import type { HeroBannerWidgetProps, WidgetStyles } from '../types'

const props = defineProps<{
  props?: HeroBannerWidgetProps
  styles?: WidgetStyles
}>()

const config = computed<HeroBannerWidgetProps>(() => ({
  title: 'Мы — больше, чем лизинг',
  subtitle: 'Подай одну заявку — получи несколько одобрений на особых условиях для юридических лиц',
  cta_text: 'Оформить заявку',
  cta_link: '/special-equipment',
  align: 'left',
  overlay_opacity: 40,
  ...props.props,
}))

const alignmentClass = computed(() => {
  switch (config.value.align) {
    case 'center':
      return 'text-center'
    case 'right':
      return 'text-right'
    default:
      return 'text-left'
  }
})

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})

const router = useRouter()

const handleCtaClick = () => {
  if (config.value.cta_anchor) {
    const el = document.querySelector(config.value.cta_anchor)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
      return
    }
  }
  if (config.value.cta_link) {
    router.push(config.value.cta_link)
  }
}
</script>
