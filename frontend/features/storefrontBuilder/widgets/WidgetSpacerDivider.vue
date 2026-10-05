<template>
  <div
    class="storefront-builder-widget flex items-center justify-center w-full"
    :style="{ height: `${config.height_px}px`, ...containerStyle }"
  >
    <hr
      v-if="config.show_divider"
      class="border-0"
      :style="{
        width: `${config.divider_width_percent ?? 100}%`,
        borderTopWidth: '1px',
        borderTopStyle: config.divider_style || 'solid',
        borderTopColor: config.divider_color || 'var(--storefront-border, #e2e8f0)',
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { widgetColorStyles } from '../utils/widgetStyles'
import type { SpacerDividerWidgetProps, WidgetStyles } from '../types'

const props = defineProps<{
  props?: SpacerDividerWidgetProps
  styles?: WidgetStyles
}>()

const config = computed<SpacerDividerWidgetProps>(() => ({
  height_px: 32,
  show_divider: true,
  divider_style: 'solid',
  divider_width_percent: 100,
  ...props.props,
}))

const containerStyle = computed(() => {
  const s = widgetColorStyles(props.styles)
  if (props.styles?.margin_top) s.marginTop = `${props.styles.margin_top}px`
  if (props.styles?.margin_bottom) s.marginBottom = `${props.styles.margin_bottom}px`
  return s
})
</script>
