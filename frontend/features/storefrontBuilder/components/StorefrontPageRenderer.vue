<template>
  <div class="storefront-page-renderer min-w-0 w-full" :class="{ 'is-editable-canvas': isEditable }" :style="pageStyle">
    <!-- If no layout or empty sections, render fallback slot -->
    <template v-if="!hasSections">
      <slot name="fallback">
        <div v-if="isEditable" class="mx-auto max-w-4xl py-20 text-center">
          <div class="rounded-2xl border-2 border-dashed border-slate-300 p-12">
            <svg class="mx-auto h-12 w-12 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <h3 class="mt-4 text-lg font-semibold text-slate-900">Страница пока пуста</h3>
            <p class="mt-2 text-sm text-slate-500">
              Добавьте первую секцию или примените готовый шаблон из библиотеки.
            </p>
            <div class="mt-6 flex justify-center gap-3">
              <button
                type="button"
                class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-500"
                @click="$emit('add-section')"
              >
                + Добавить секцию
              </button>
            </div>
          </div>
        </div>
      </slot>
    </template>

    <!-- Sections Renderer -->
    <template v-else>
      <section
        v-for="(section, sIdx) in layout!.sections"
        :key="section.id"
        :data-section-id="section.id"
        class="storefront-section relative transition-all duration-150"
        :class="[
          isEditable ? 'group/section hover:outline-dashed hover:outline-2 hover:outline-blue-400' : '',
          isEditable && selectedId === section.id ? 'outline-2 outline-blue-600 outline' : '',
        ]"
        :style="resolveSectionStyles(section.styles)"
        @click.stop="isEditable && $emit('select-section', section.id)"
      >
        <!-- Editor Section Toolbar -->
        <div
          v-if="isEditable"
          class="absolute -top-3.5 left-4 z-30 hidden items-center space-x-1 rounded bg-blue-600 px-2.5 py-0.5 text-xs font-semibold text-white shadow group-hover/section:flex"
        >
          <span>{{ section.name || `Секция ${sIdx + 1}` }}</span>
          <span class="mx-1 text-blue-300">|</span>
          <button
            type="button"
            title="Удалить секцию"
            class="hover:text-red-200"
            @click.stop="$emit('delete-section', section.id)"
          >
            &times;
          </button>
        </div>

        <!-- Section Inner Container (full-width vs container) -->
        <div
          :class="section.layout_type === 'full_width' ? 'w-full' : 'mx-auto max-w-7xl px-4 sm:px-6 lg:px-8'"
        >
          <!-- Grid columns -->
          <div class="grid grid-cols-12 gap-6 items-start">
            <div
              v-for="col in section.columns"
              :key="col.id"
              :data-column-id="col.id"
              :class="[
                resolveColumnSpanClass(col.width),
                isEditable ? 'min-h-[60px] rounded border border-dashed border-transparent hover:border-slate-300 p-1' : '',
              ]"
              :style="resolveColumnStyles(col.styles)"
            >
              <!-- Widgets list -->
              <template v-if="col.widgets && col.widgets.length > 0">
                <div
                  v-for="widget in col.widgets"
                  :key="widget.id"
                  v-show="!widget.is_hidden || isEditable"
                  :data-widget-id="widget.id"
                  class="storefront-widget-wrapper relative my-2 transition-all duration-150"
                  :class="[
                    widget.is_hidden && isEditable ? 'opacity-40' : '',
                    isEditable ? 'group/widget hover:ring-2 hover:ring-blue-500 rounded-lg' : '',
                    isEditable && selectedId === widget.id ? 'ring-2 ring-blue-600 rounded-lg' : '',
                  ]"
                  @click.stop="isEditable && $emit('select-widget', widget.id, section.id, col.id)"
                >
                  <!-- Editor Widget Toolbar -->
                  <div
                    v-if="isEditable"
                    class="absolute -top-3 right-3 z-30 hidden items-center space-x-1.5 rounded-md bg-slate-900/90 px-2 py-0.5 text-xs text-white shadow backdrop-blur-sm group-hover/widget:flex"
                  >
                    <span class="font-medium text-slate-300">{{ getWidgetName(widget.type) }}</span>
                    <button
                      type="button"
                      title="Дублировать"
                      class="p-0.5 hover:text-blue-400"
                      @click.stop="$emit('duplicate-widget', widget.id, section.id, col.id)"
                    >
                      <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      title="Удалить"
                      class="p-0.5 hover:text-rose-400"
                      @click.stop="$emit('delete-widget', widget.id, section.id, col.id)"
                    >
                      <svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>

                  <!-- Dynamic Widget Component -->
                  <component
                    :is="resolveWidgetComponent(widget.type)"
                    :props="widget.props"
                    :styles="widget.styles"
                  />
                </div>
              </template>

              <!-- Empty Column Placeholder in Editable mode -->
              <div
                v-else-if="isEditable"
                class="flex h-32 items-center justify-center rounded-lg border-2 border-dashed border-slate-300 p-4 text-center hover:border-blue-400"
              >
                <button
                  type="button"
                  class="text-xs font-semibold text-slate-500 hover:text-blue-600"
                  @click.stop="$emit('add-widget', section.id, col.id)"
                >
                  + Добавить виджет
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Add Section Button at the bottom when in editable mode -->
      <div v-if="isEditable" class="py-6 text-center">
        <button
          type="button"
          class="inline-flex items-center rounded-lg border-2 border-dashed border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-600 hover:border-blue-500 hover:text-blue-600"
          @click="$emit('add-section')"
        >
          <svg class="mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          Добавить новую секцию
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import type { PageLayout, SectionStyles, ColumnStyles, WidgetType } from '../types'
import { WIDGET_REGISTRY } from '../types'
import { WIDGET_COMPONENTS } from '../widgets'
import { widgetColorStyles } from '../utils/widgetStyles'
import { useStorefrontStore } from '~/features/storefront/store/storefront'
import { buildStorefrontPageTheme, type StorefrontPageAppearance } from '../utils/pageTheme'

const props = withDefaults(
  defineProps<{
    layout?: PageLayout | null
    appearance?: StorefrontPageAppearance | null
    isEditable?: boolean
    selectedId?: string | null
  }>(),
  {
    layout: null,
    appearance: null,
    isEditable: false,
    selectedId: null,
  },
)

defineEmits<{
  (e: 'select-section', sectionId: string): void
  (e: 'select-widget', widgetId: string, sectionId: string, columnId: string): void
  (e: 'delete-section', sectionId: string): void
  (e: 'delete-widget', widgetId: string, sectionId: string, columnId: string): void
  (e: 'duplicate-widget', widgetId: string, sectionId: string, columnId: string): void
  (e: 'add-section'): void
  (e: 'add-widget', sectionId: string, columnId: string): void
}>()

const storefrontStore = useStorefrontStore()
const pageStyle = computed(() => {
  if (!hasSections.value) return {}
  const variables = buildStorefrontPageTheme(props.layout?.settings, props.appearance ?? storefrontStore.appearance)
  return { ...variables, backgroundColor: 'var(--storefront-background)', color: 'var(--storefront-text)' }
})

const hasSections = computed(() => {
  return props.layout && Array.isArray(props.layout.sections) && props.layout.sections.length > 0
})

const resolveWidgetComponent = (type: WidgetType): Component | string => {
  return WIDGET_COMPONENTS[type] || 'div'
}

const getWidgetName = (type: WidgetType): string => {
  const meta = WIDGET_REGISTRY[type]
  return meta ? (meta.name || meta.title) : type
}

const resolveColumnSpanClass = (width: number): string => {
  const clamped = Math.max(1, Math.min(12, Math.round(width || 12)))
  switch (clamped) {
    case 1:
      return 'col-span-12 lg:col-span-1'
    case 2:
      return 'col-span-12 sm:col-span-6 lg:col-span-2'
    case 3:
      return 'col-span-12 sm:col-span-6 lg:col-span-3'
    case 4:
      return 'col-span-12 sm:col-span-6 lg:col-span-4'
    case 5:
      return 'col-span-12 sm:col-span-6 lg:col-span-5'
    case 6:
      return 'col-span-12 lg:col-span-6'
    case 7:
      return 'col-span-12 lg:col-span-7'
    case 8:
      return 'col-span-12 lg:col-span-8'
    case 9:
      return 'col-span-12 lg:col-span-9'
    case 10:
      return 'col-span-12 lg:col-span-10'
    case 11:
      return 'col-span-12 lg:col-span-11'
    case 12:
    default:
      return 'col-span-12'
  }
}

const resolveSectionStyles = (styles?: SectionStyles): Record<string, string> => {
  if (!styles) return {}
  const res = widgetColorStyles(styles)
  if (styles.padding_top !== undefined) res.paddingTop = `${styles.padding_top}px`
  if (styles.padding_bottom !== undefined) res.paddingBottom = `${styles.padding_bottom}px`
  if (styles.padding_left !== undefined) res.paddingLeft = `${styles.padding_left}px`
  if (styles.padding_right !== undefined) res.paddingRight = `${styles.padding_right}px`
  if (styles.margin_top !== undefined) res.marginTop = `${styles.margin_top}px`
  if (styles.margin_bottom !== undefined) res.marginBottom = `${styles.margin_bottom}px`
  if (styles.background_image) {
    res.backgroundImage = `url(${styles.background_image})`
    res.backgroundSize = styles.background_size || 'cover'
    res.backgroundPosition = styles.background_position || 'center'
  }
  if (styles.border_color) res.borderColor = styles.border_color
  if (styles.border_width !== undefined) res.borderWidth = `${styles.border_width}px`
  if (styles.border_radius !== undefined) res.borderRadius = `${styles.border_radius}px`
  return res
}

const resolveColumnStyles = (styles?: ColumnStyles): Record<string, string> => {
  if (!styles) return {}
  const res = widgetColorStyles(styles)
  if (styles.padding_top !== undefined) res.paddingTop = `${styles.padding_top}px`
  if (styles.padding_bottom !== undefined) res.paddingBottom = `${styles.padding_bottom}px`
  if (styles.padding_left !== undefined) res.paddingLeft = `${styles.padding_left}px`
  if (styles.padding_right !== undefined) res.paddingRight = `${styles.padding_right}px`
  if (styles.border_radius !== undefined) res.borderRadius = `${styles.border_radius}px`
  return res
}
</script>

<style scoped>
.is-editable-canvas {
  user-select: none;
}
</style>
