<template>
  <main class="relative flex-1 min-h-0 w-full overflow-y-auto bg-slate-100 p-6 flex flex-col items-center">
    <!-- Viewport Container with responsive width simulation -->
    <div
      class="w-full transition-all duration-200 ease-in-out flex flex-col min-h-full bg-white shadow-xl rounded-xl overflow-hidden border border-slate-200 shrink-0"
      :class="canvasWidthClass"
      @click="handleCanvasClick"
      @dragover.prevent="handleDragOver"
      @drop="handleDropOnCanvas"
    >
      <!-- Top Canvas Controls: Add Section Bar -->
      <div
        v-if="!builderStore.previewMode"
        class="border-b border-dashed border-slate-200 bg-slate-50/70 py-2 px-4 flex justify-between items-center text-xs text-slate-500 shrink-0"
      >
        <span class="font-medium text-slate-600">
          {{ builderStore.previewDevice.toUpperCase() }} ({{ viewportWidthText }})
        </span>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-100 transition-colors"
          @click.stop="builderStore.addSection(0)"
        >
          <PlusIcon class="h-3.5 w-3.5" aria-hidden="true" />
          Добавить секцию в начало
        </button>
      </div>

      <!-- Live Page Renderer -->
      <StorefrontPageRenderer
        :layout="builderStore.layout"
        :appearance="builderStore.storefront?.appearance"
        class="flex-1"
        :is-editable="!builderStore.previewMode"
        :selected-id="builderStore.previewMode ? null : builderStore.selectedElementId"
        @select-widget="handleSelectWidget"
        @select-section="handleSelectSection"
        @duplicate-widget="handleDuplicateWidget"
        @delete-widget="handleDeleteWidget"
        @delete-section="handleDeleteSection"
        @add-section="builderStore.addSection()"
        @add-widget="handleAddWidget"
      >
        <template #fallback>
          <div v-if="!builderStore.previewMode" class="py-24 text-center px-4">
            <div class="mx-auto max-w-md rounded-2xl border-2 border-dashed border-slate-300 p-10 bg-slate-50/50">
              <SparklesIcon class="mx-auto h-12 w-12 text-blue-500" aria-hidden="true" />
              <h3 class="mt-4 text-base font-semibold text-slate-900">Страница пока не настроена</h3>
              <p class="mt-2 text-xs text-slate-500 leading-relaxed">
                Перетащите виджет из боковой панели, выберите готовый шаблон или добавьте пустую секцию для начала верстки.
              </p>
              <div class="mt-6 flex flex-wrap justify-center gap-3">
                <button
                  type="button"
                  class="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-500 transition-colors"
                  @click="builderStore.showTemplatesModal = true"
                >
                  Выбрать шаблон
                </button>
                <button
                  type="button"
                  class="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition-colors"
                  @click="builderStore.addSection()"
                >
                  + Пустая секция
                </button>
              </div>
            </div>
          </div>
          <div v-else class="py-24 text-center px-4 text-slate-400 text-sm">
            Пустая страница
          </div>
        </template>
      </StorefrontPageRenderer>

      <!-- Bottom Add Section Banner -->
      <div v-if="hasSections && !builderStore.previewMode" class="border-t border-dashed border-slate-200 bg-slate-50/70 py-4 text-center shrink-0">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-blue-400 bg-blue-50/50 px-4 py-2 text-xs font-semibold text-blue-700 hover:bg-blue-100 transition-colors"
          @click.stop="builderStore.addSection()"
        >
          <PlusIcon class="h-4 w-4" aria-hidden="true" />
          Добавить секцию в конец
        </button>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { PlusIcon, SparklesIcon } from '@heroicons/vue/24/outline'
import { useStorefrontBuilderStore } from '../store/storefrontBuilder'
import StorefrontPageRenderer from './StorefrontPageRenderer.vue'
import type { WidgetType } from '../types'

const builderStore = useStorefrontBuilderStore()

const hasSections = computed(() => (builderStore.layout?.sections?.length || 0) > 0)

const canvasWidthClass = computed(() => {
  switch (builderStore.previewDevice) {
    case 'laptop':
      return 'max-w-5xl' // 1024px
    case 'tablet':
      return 'max-w-3xl' // 768px (Desktop Compact per AGENTS.md rule)
    case 'desktop':
    default:
      return 'max-w-7xl' // 1440px
  }
})

const viewportWidthText = computed(() => {
  switch (builderStore.previewDevice) {
    case 'laptop':
      return '1024 px'
    case 'tablet':
      return '768 px'
    case 'desktop':
    default:
      return '1440 px'
  }
})

function handleCanvasClick() {
  if (builderStore.previewMode) return
  // If clicking on empty canvas area, clear active selection
  builderStore.clearSelection()
}

function handleSelectWidget(widgetId: string) {
  if (builderStore.previewMode) return
  builderStore.selectElement(widgetId)
}

function handleSelectSection(sectionId: string) {
  if (builderStore.previewMode) return
  builderStore.selectElement(sectionId)
}

function handleDuplicateWidget(widgetId: string) {
  if (builderStore.previewMode) return
  builderStore.duplicateWidget(widgetId)
}

function handleDeleteWidget(widgetId: string) {
  if (builderStore.previewMode) return
  builderStore.removeWidget(widgetId)
}

function handleDeleteSection(sectionId: string) {
  if (builderStore.previewMode) return
  builderStore.removeSection(sectionId)
}

function handleAddWidget(sectionId: string, columnId: string) {
  if (builderStore.previewMode) return
  builderStore.addWidget(sectionId, columnId, 'rich_text')
}

function handleDragOver(event: DragEvent) {
  if (builderStore.previewMode) return
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

function handleDropOnCanvas(event: DragEvent) {
  if (builderStore.previewMode) return
  event.preventDefault()
  const widgetType = event.dataTransfer?.getData('application/x-storefront-widget') as WidgetType
  if (!widgetType) return

  // If no sections exist, create one first
  if (!builderStore.layout.sections.length) {
    builderStore.addSection()
  }

  const firstSection = builderStore.layout.sections[builderStore.layout.sections.length - 1]
  const firstCol = firstSection?.columns[0]
  if (firstSection && firstCol) {
    builderStore.addWidget(firstSection.id, firstCol.id, widgetType)
  }
}
</script>
