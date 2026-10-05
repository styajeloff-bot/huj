<template>
  <div class="storefront-builder-widget py-4" :style="containerStyle">
    <div
      class="prose storefront-builder-prose max-w-none storefront-builder-text"
      :class="maxWidthClass"
      v-html="sanitizedContent"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { widgetColorStyles } from '../utils/widgetStyles'
import { sanitizeHtml } from '../utils/sanitize'
import type { RichTextWidgetProps, WidgetStyles } from '../types'

const props = defineProps<{
  props?: RichTextWidgetProps
  styles?: WidgetStyles
}>()

const defaultHtml = `
  <h2>О компании Carcraft Multileasing</h2>
  <p>Мы предлагаем комплексное финансирование коммерческого автотранспорта и строительной техники для малого, среднего и крупного бизнеса. Наша платформа объединяет ведущие лизинговые компании страны.</p>
  <ul>
    <li>Индивидуальный график платежей с учетом сезонности вашего бизнеса</li>
    <li>Минимальный пакет документов и быстрое принятие решения</li>
    <li>Партнерские выгоды от официальных дилеров и производителей</li>
  </ul>
`

const config = computed<RichTextWidgetProps>(() => ({
  html_content: defaultHtml,
  max_width: 'wide',
  ...props.props,
}))

const sanitizedContent = computed(() => {
  return sanitizeHtml(config.value.html_content || defaultHtml)
})

const maxWidthClass = computed(() => {
  switch (config.value.max_width) {
    case 'narrow':
      return 'mx-auto max-w-3xl'
    case 'full':
      return 'w-full'
    case 'wide':
    default:
      return 'mx-auto max-w-5xl'
  }
})

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  if (props.styles?.border_radius !== undefined) s.borderRadius = `${props.styles.border_radius}px`
  return s
})
</script>
