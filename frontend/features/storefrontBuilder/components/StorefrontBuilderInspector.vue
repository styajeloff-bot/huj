<template>
  <aside
    v-if="builderStore.selectedElementId"
    class="flex w-80 shrink-0 flex-col border-l border-slate-200 bg-white select-none shadow-sm z-20"
  >
    <!-- Inspector Header -->
    <div class="flex h-14 items-center justify-between border-b border-slate-200 px-4 bg-slate-50/70">
      <div class="flex items-center gap-2 min-w-0">
        <span class="rounded bg-blue-100 p-1 text-blue-700">
          <AdjustmentsHorizontalIcon class="h-4 w-4" aria-hidden="true" />
        </span>
        <div class="min-w-0">
          <h3 class="truncate text-xs font-semibold text-slate-900">
            {{ headerTitle }}
          </h3>
          <p class="truncate text-[10px] text-slate-500 font-mono">
            {{ builderStore.selectedElementId.slice(0, 8) }}…
          </p>
        </div>
      </div>
      <button
        type="button"
        class="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
        title="Закрыть инспектор"
        @click="builderStore.clearSelection()"
      >
        <XMarkIcon class="h-4 w-4" aria-hidden="true" />
      </button>
    </div>

    <!-- Inspector Tabs -->
    <nav class="flex border-b border-slate-200 bg-slate-50 text-xs font-medium" aria-label="Свойства элемента">
      <button
        type="button"
        class="flex-1 py-2 text-center transition-colors border-b-2"
        :class="activeTab === 'content' ? 'border-blue-600 bg-white text-blue-700 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
        @click="activeTab = 'content'"
      >
        Контент
      </button>
      <button
        type="button"
        class="flex-1 py-2 text-center transition-colors border-b-2"
        :class="activeTab === 'style' ? 'border-blue-600 bg-white text-blue-700 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
        @click="activeTab = 'style'"
      >
        Стиль
      </button>
      <button
        type="button"
        class="flex-1 py-2 text-center transition-colors border-b-2"
        :class="activeTab === 'advanced' ? 'border-blue-600 bg-white text-blue-700 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
        @click="activeTab = 'advanced'"
      >
        Дополнительно
      </button>
    </nav>

    <!-- Content Panel -->
    <div class="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
      <!-- 1. TAB: CONTENT -->
      <div v-show="activeTab === 'content'" class="space-y-4">
        <!-- SECTION SETTINGS -->
        <template v-if="builderStore.selectedElementType === 'section' && builderStore.selectedSection">
          <div>
            <label class="block font-medium text-slate-700 mb-1">Название секции</label>
            <input
              v-model="builderStore.selectedSection.name"
              type="text"
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              placeholder="Например, Промо-блок"
            >
          </div>

          <div>
            <label class="block font-medium text-slate-700 mb-1">Тип контейнера</label>
            <select
              v-model="builderStore.selectedSection.layout_type"
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
            >
              <option value="container">Фиксированный контейнер (max-w-7xl)</option>
              <option value="full_width">На всю ширину экрана (full-width)</option>
            </select>
          </div>
        </template>

        <!-- WIDGET SETTINGS -->
        <template v-else-if="builderStore.selectedWidget">
          <!-- Common Title Field for Most Widgets -->
          <div v-if="'title' in currentProps">
            <label class="block font-medium text-slate-700 mb-1">Заголовок</label>
            <input
              v-model="currentProps.title"
              type="text"
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              placeholder="Заголовок блока"
            >
          </div>

          <!-- Hero Banner Specific -->
          <template v-if="builderStore.selectedWidget.type === 'hero_banner'">
            <div>
              <label class="block font-medium text-slate-700 mb-1">Подзаголовок</label>
              <textarea
                v-model="currentProps.subtitle"
                rows="2"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              />
            </div>
            <div>
              <label class="block font-medium text-slate-700 mb-1">Бейдж акции</label>
              <input
                v-model="currentProps.badge_text"
                type="text"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                placeholder="Специальное предложение"
              >
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block font-medium text-slate-700 mb-1">Текст кнопки CTA</label>
                <input
                  v-model="currentProps.cta_text"
                  type="text"
                  class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                >
              </div>
              <div>
                <label class="block font-medium text-slate-700 mb-1">Ссылка CTA</label>
                <input
                  v-model="currentProps.cta_url"
                  type="text"
                  class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                >
              </div>
            </div>
            <div>
              <label class="block font-medium text-slate-700 mb-1">Фоновое изображение (URL)</label>
              <input
                v-model="currentProps.background_image"
                type="text"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                placeholder="https://..."
              >
            </div>
          </template>

          <!-- Leasing Calculator Specific -->
          <template v-else-if="builderStore.selectedWidget.type === 'leasing_calculator'">
            <div>
              <label class="block font-medium text-slate-700 mb-1">Базовая стоимость (₽)</label>
              <input
                v-model.number="currentProps.default_price"
                type="number"
                step="50000"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              >
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block font-medium text-slate-700 mb-1">Мин. аванс (%)</label>
                <input
                  v-model.number="currentProps.min_advance"
                  type="number"
                  class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                >
              </div>
              <div>
                <label class="block font-medium text-slate-700 mb-1">Макс. срок (мес)</label>
                <input
                  v-model.number="currentProps.max_term"
                  type="number"
                  class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                >
              </div>
            </div>
            <label class="flex items-center gap-2 pt-2 cursor-pointer">
              <input v-model="currentProps.show_apply_button" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-blue-600">
              <span class="text-slate-700">Показывать кнопку подачи заявки</span>
            </label>
          </template>

          <!-- Product Showcase Specific -->
          <template v-else-if="builderStore.selectedWidget.type === 'product_showcase'">
            <div>
              <label class="block font-medium text-slate-700 mb-1">Количество карточек</label>
              <input
                v-model.number="currentProps.items_limit"
                type="number"
                min="2"
                max="24"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              >
            </div>
            <div>
              <label class="block font-medium text-slate-700 mb-1">Вид отображения</label>
              <select
                v-model="currentProps.layout"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              >
                <option value="grid">Сетка карточек (Grid)</option>
                <option value="carousel">Карусель / Слайдер</option>
              </select>
            </div>
          </template>

          <!-- Features Grid Specific -->
          <template v-else-if="builderStore.selectedWidget.type === 'features_grid'">
            <div>
              <label class="block font-medium text-slate-700 mb-1">Количество колонок</label>
              <select
                v-model.number="currentProps.columns_count"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              >
                <option :value="2">2 колонки</option>
                <option :value="3">3 колонки</option>
                <option :value="4">4 колонки</option>
              </select>
            </div>
          </template>

          <!-- Rich Text Specific -->
          <template v-else-if="builderStore.selectedWidget.type === 'rich_text'">
            <div>
              <label class="block font-medium text-slate-700 mb-1">HTML Содержимое</label>
              <textarea
                v-model="currentProps.content"
                rows="6"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs font-mono text-slate-900 focus:border-blue-600 focus:outline-none"
                placeholder="<p>Текст о компании…</p>"
              />
            </div>
          </template>

          <!-- CTA Strip Specific -->
          <template v-else-if="builderStore.selectedWidget.type === 'cta_strip'">
            <div>
              <label class="block font-medium text-slate-700 mb-1">Подзаголовок</label>
              <input
                v-model="currentProps.subtitle"
                type="text"
                class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              >
            </div>
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="block font-medium text-slate-700 mb-1">Текст кнопки</label>
                <input
                  v-model="currentProps.button_text"
                  type="text"
                  class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                >
              </div>
              <div>
                <label class="block font-medium text-slate-700 mb-1">Ссылка кнопки</label>
                <input
                  v-model="currentProps.button_url"
                  type="text"
                  class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                >
              </div>
            </div>
          </template>

          <!-- Spacer Specific -->
          <template v-else-if="builderStore.selectedWidget.type === 'spacer_divider'">
            <div>
              <label class="block font-medium text-slate-700 mb-1">Высота отступа (px): {{ currentProps.height }}px</label>
              <input
                v-model.number="currentProps.height"
                type="range"
                min="8"
                max="120"
                step="4"
                class="w-full accent-blue-600"
              >
            </div>
            <label class="flex items-center gap-2 pt-2 cursor-pointer">
              <input v-model="currentProps.show_divider" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-blue-600">
              <span class="text-slate-700">Отображать разделительную линию</span>
            </label>
          </template>
        </template>
      </div>

      <!-- 2. TAB: STYLE -->
      <div v-show="activeTab === 'style'" class="space-y-4">
        <div>
          <label class="block font-medium text-slate-700 mb-1">Цвет фона</label>
          <div class="flex items-center gap-2">
            <input
              v-model="currentStyles.background_color"
              type="color"
              class="h-7 w-7 rounded border border-slate-300 cursor-pointer p-0.5"
            >
            <input
              v-model="currentStyles.background_color"
              type="text"
              class="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-mono text-slate-900 uppercase focus:border-blue-600 focus:outline-none"
              placeholder="#FFFFFF"
            >
          </div>
        </div>

        <div>
          <label class="block font-medium text-slate-700 mb-1">Цвет текста</label>
          <div class="flex items-center gap-2">
            <input
              v-model="currentStyles.text_color"
              type="color"
              class="h-7 w-7 rounded border border-slate-300 cursor-pointer p-0.5"
            >
            <input
              v-model="currentStyles.text_color"
              type="text"
              class="flex-1 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-mono text-slate-900 uppercase focus:border-blue-600 focus:outline-none"
              placeholder="#111827"
            >
          </div>
        </div>

        <div>
          <label class="block font-medium text-slate-700 mb-1">Внутренний отступ (Padding)</label>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <span class="text-[10px] text-slate-500">Сверху</span>
              <input
                v-model="currentStyles.padding_top"
                type="text"
                class="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                placeholder="24px"
              >
            </div>
            <div>
              <span class="text-[10px] text-slate-500">Снизу</span>
              <input
                v-model="currentStyles.padding_bottom"
                type="text"
                class="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                placeholder="24px"
              >
            </div>
          </div>
        </div>
      </div>

      <!-- 3. TAB: ADVANCED -->
      <div v-show="activeTab === 'advanced'" class="space-y-4">
        <template v-if="builderStore.selectedWidget">
          <label class="flex items-center gap-2 cursor-pointer bg-slate-50 p-2.5 rounded-lg border border-slate-200">
            <input
              v-model="builderStore.selectedWidget.is_hidden"
              type="checkbox"
              class="h-4 w-4 rounded border-slate-300 text-blue-600"
            >
            <span class="font-medium text-slate-700">Скрыть блок на публичной витрине</span>
          </label>

          <div>
            <label class="block font-medium text-slate-700 mb-1">Якорный ID (#id)</label>
            <input
              v-model="currentStyles.anchor_id"
              type="text"
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              placeholder="calculator"
            >
            <span class="text-[10px] text-slate-500 mt-1 block">Для плавной прокрутки по ссылке вида #calculator</span>
          </div>

          <div>
            <label class="block font-medium text-slate-700 mb-1">Пользовательские CSS классы</label>
            <input
              v-model="currentStyles.custom_class"
              type="text"
              class="w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
              placeholder="my-custom-class shadow-lg"
            >
          </div>
        </template>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { AdjustmentsHorizontalIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { useStorefrontBuilderStore } from '../store/storefrontBuilder'

const builderStore = useStorefrontBuilderStore()
const activeTab = ref<'content' | 'style' | 'advanced'>('content')

const headerTitle = computed(() => {
  if (builderStore.selectedElementType === 'section') {
    return `Секция: ${builderStore.selectedSection?.name || 'Без названия'}`
  }
  if (builderStore.selectedWidget) {
    return `Виджет: ${builderStore.selectedWidget.type}`
  }
  return 'Элемент'
})

const currentProps = computed<Record<string, any>>({
  get: () => builderStore.selectedWidget?.props || {},
  set: (val) => {
    if (builderStore.selectedWidget) {
      builderStore.selectedWidget.props = val
      builderStore.isDirty = true
    }
  },
})

const currentStyles = computed<Record<string, any>>({
  get: () => {
    if (builderStore.selectedWidget) {
      return (builderStore.selectedWidget.styles = builderStore.selectedWidget.styles || {})
    }
    if (builderStore.selectedSection) {
      return (builderStore.selectedSection.styles = builderStore.selectedSection.styles || {})
    }
    return {}
  },
  set: (val) => {
    if (builderStore.selectedWidget) {
      builderStore.selectedWidget.styles = val
      builderStore.isDirty = true
    } else if (builderStore.selectedSection) {
      builderStore.selectedSection.styles = val
      builderStore.isDirty = true
    }
  },
})
</script>
